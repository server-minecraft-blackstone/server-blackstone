import re
import unicodedata

import aiosqlite
import discord

from app_paths import get_database_path
from discord import app_commands
from discord.ext import commands

# Listes prédéfinies : de la plus permissive à la plus stricte.
LISTES_GROS_MOTS = {
    "leger": {"connard", "connasse", "salope", "pute", "encule", "fdp", "ntm"},
    "modere": {"con", "conne", "connard", "connasse", "salope", "pute", "encule",
               "enfoire", "fdp", "ntm", "merdeux", "raclure"},
    "strict": {"abruti", "idiot", "idiote", "debile", "imbecile", "cretin", "cretine",
               "con", "conne", "connard", "connasse", "salope", "pute", "encule",
               "enfoire", "ordure", "minable", "degenere", "attarde", "merdeux",
               "raclure", "fdp", "ntm", "merde", "bordel"},
    "tres_strict": {"abruti", "idiot", "idiote", "debile", "imbecile", "cretin", "cretine",
                    "con", "conne", "connard", "connasse", "salope", "pute", "encule",
                    "enfoire", "ordure", "minable", "degenere", "attarde", "merdeux",
                    "raclure", "fdp", "ntm", "merde", "bordel", "putain", "chier",
                    "chiant", "foutre", "ta gueule"},
}
NIVEAUX_GROS_MOTS = [
    app_commands.Choice(name="Léger — insultes graves uniquement", value="leger"),
    app_commands.Choice(name="Modéré — insultes courantes", value="modere"),
    app_commands.Choice(name="Strict — insultes et vulgarités", value="strict"),
    app_commands.Choice(name="Très strict — liste la plus large", value="tres_strict"),
]
NIVEAU_PAR_DEFAUT = "modere"
MOTS_DEFAUT = LISTES_GROS_MOTS[NIVEAU_PAR_DEFAUT]

LIEN = re.compile(r"https?://|www\.|discord\.gg/", re.IGNORECASE)

REGLES = [
    app_commands.Choice(name="Insultes", value="insultes"),
    app_commands.Choice(name="Liens", value="liens"),
]
MESSAGES = {
    "insultes": "les insultes sont interdites dans ce salon.",
    "liens": "les liens sont interdits dans ce salon.",
}


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, et remplace 0/4/1/3/5/@/$ par des lettres."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return texte.translate(str.maketrans("04135@$", "oaiesas"))


class Automod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.regles: dict[int, set[str]] = {}  # salon_id -> règles interdites
        self.mots: dict[int, set[str]] = {}    # guild_id -> mots perso
        self.niveaux: dict[int, str] = {}   # guild_id -> niveau de filtrage

    async def cog_load(self):
        self.db = await aiosqlite.connect(get_database_path())
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS regles "
            "(salon_id INTEGER, regle TEXT, PRIMARY KEY (salon_id, regle))"
        )
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS mots "
            "(guild_id INTEGER, mot TEXT, PRIMARY KEY (guild_id, mot))"
        )
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS niveaux_gros_mots "
            "(guild_id INTEGER PRIMARY KEY, niveau TEXT NOT NULL)"
        )
        await self.db.commit()
        async with self.db.execute("SELECT salon_id, regle FROM regles") as cur:
            async for salon_id, regle in cur:
                self.regles.setdefault(salon_id, set()).add(regle)
        async with self.db.execute("SELECT guild_id, mot FROM mots") as cur:
            async for guild_id, mot in cur:
                self.mots.setdefault(guild_id, set()).add(mot)
        async with self.db.execute("SELECT guild_id, niveau FROM niveaux_gros_mots") as cur:
            async for guild_id, niveau in cur:
                if niveau in LISTES_GROS_MOTS:
                    self.niveaux[guild_id] = niveau

    async def cog_unload(self):
        await self.db.close()

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
        else:
            raise error

    # ---------- Détection ----------

    def liste_active(self, guild_id: int) -> set[str]:
        niveau = self.niveaux.get(guild_id, NIVEAU_PAR_DEFAUT)
        return set(LISTES_GROS_MOTS[niveau]) | self.mots.get(guild_id, set())

    def contient_insulte(self, guild_id: int, texte: str) -> bool:
        mots = self.liste_active(guild_id)
        texte = normaliser(texte)
        return any(re.search(rf"\b{re.escape(m)}\b", texte) for m in mots)

    async def verifier(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return  # l'équipe de modération n'est pas filtrée
        # Dans un fil de discussion, on utilise les règles du salon parent
        salon_id = getattr(message.channel, "parent_id", None) or message.channel.id
        regles = self.regles.get(salon_id)
        if not regles:
            return  # rien d'interdit ici

        violation = None
        if "liens" in regles and LIEN.search(message.content):
            violation = "liens"
        elif "insultes" in regles and self.contient_insulte(message.guild.id, message.content):
            violation = "insultes"

        if violation:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, {MESSAGES[violation]}", delete_after=6
                )
            except discord.Forbidden:
                pass  # le bot n'a pas la permission « Gérer les messages »

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.verifier(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        await self.verifier(after)

    # ---------- Configuration par salon ----------

    @app_commands.command(name="filtre_on", description="Interdit quelque chose dans un salon")
    @app_commands.describe(regle="Ce qui est interdit", salon="Le salon concerné")
    @app_commands.choices(regle=REGLES)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def interdire(self, interaction: discord.Interaction,
                        regle: app_commands.Choice[str], salon: discord.TextChannel):
        await self.db.execute(
            "INSERT OR IGNORE INTO regles (salon_id, regle) VALUES (?, ?)",
            (salon.id, regle.value),
        )
        await self.db.commit()
        self.regles.setdefault(salon.id, set()).add(regle.value)
        await interaction.response.send_message(f"🚫 {regle.name} interdites dans {salon.mention}.")

    @app_commands.command(name="filtre_off", description="Autorise quelque chose dans un salon")
    @app_commands.describe(regle="Ce qui est autorisé", salon="Le salon concerné")
    @app_commands.choices(regle=REGLES)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autoriser(self, interaction: discord.Interaction,
                        regle: app_commands.Choice[str], salon: discord.TextChannel):
        await self.db.execute(
            "DELETE FROM regles WHERE salon_id = ? AND regle = ?", (salon.id, regle.value)
        )
        await self.db.commit()
        self.regles.get(salon.id, set()).discard(regle.value)
        await interaction.response.send_message(f"✅ {regle.name} autorisées dans {salon.mention}.")

    @app_commands.command(name="filtres", description="Affiche les règles de chaque salon")
    @app_commands.guild_only()
    async def regles_cmd(self, interaction: discord.Interaction):
        lignes = []
        for salon in interaction.guild.text_channels:
            interdits = self.regles.get(salon.id)
            if interdits:
                lignes.append(f"{salon.mention} : interdit → {', '.join(sorted(interdits))}")
        texte = "\n".join(lignes) or "Tout est autorisé partout pour l'instant."
        await interaction.response.send_message(texte, ephemeral=True)

    # ---------- Configuration de la liste de gros mots ----------

    @app_commands.command(
        name="gros_mots",
        description="Choisit la sévérité de la liste de gros mots du serveur",
    )
    @app_commands.describe(niveau="Liste à appliquer à la modération et à l'automodération")
    @app_commands.choices(niveau=NIVEAUX_GROS_MOTS)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gros_mots_niveau(
        self, interaction: discord.Interaction, niveau: app_commands.Choice[str]
    ):
        await self.db.execute(
            "INSERT INTO niveaux_gros_mots (guild_id, niveau) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET niveau = excluded.niveau",
            (interaction.guild_id, niveau.value),
        )
        await self.db.commit()
        self.niveaux[interaction.guild_id] = niveau.value
        await interaction.response.send_message(
            f"Liste de gros mots réglée sur **{niveau.name}**. "
            "Ce choix s'applique à l'automodération et à la détection d'insultes ciblées.",
            ephemeral=True,
        )

    @app_commands.command(name="gros_mots_aide", description="Affiche les niveaux de filtrage disponibles")
    @app_commands.guild_only()
    async def gros_mots_liste(self, interaction: discord.Interaction):
        niveau = self.niveaux.get(interaction.guild_id, NIVEAU_PAR_DEFAUT)
        descriptions = [
            "• **Léger** : insultes graves uniquement",
            "• **Modéré** : insultes courantes (niveau par défaut)",
            "• **Strict** : insultes et vulgarités",
            "• **Très strict** : liste la plus large",
        ]
        await interaction.response.send_message(
            f"Niveau actuel : **{niveau.replace('_', ' ').capitalize()}**\n"
            + "\n".join(descriptions)
            + "\nChange avec /gros_mots.",
            ephemeral=True,
        )

    # ---------- Liste de mots ----------

    @app_commands.command(name="mot_add", description="Ajoute un mot à la liste d'insultes")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mot_ajouter(self, interaction: discord.Interaction, mot: str):
        mot = normaliser(mot.strip())
        await self.db.execute(
            "INSERT OR IGNORE INTO mots (guild_id, mot) VALUES (?, ?)", (interaction.guild_id, mot)
        )
        await self.db.commit()
        self.mots.setdefault(interaction.guild_id, set()).add(mot)
        await interaction.response.send_message("Mot ajouté.", ephemeral=True)

    @app_commands.command(name="mot_del", description="Retire un mot ajouté à la liste")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def mot_retirer(self, interaction: discord.Interaction, mot: str):
        mot = normaliser(mot.strip())
        await self.db.execute(
            "DELETE FROM mots WHERE guild_id = ? AND mot = ?", (interaction.guild_id, mot)
        )
        await self.db.commit()
        self.mots.get(interaction.guild_id, set()).discard(mot)
        await interaction.response.send_message("Mot retiré.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Automod(bot))
