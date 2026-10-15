import re
import unicodedata
from datetime import timedelta
from typing import Optional

import aiosqlite
import discord

from app_paths import get_database_path
from discord import app_commands
from discord.ext import commands

# ---------- Réglages (à ajuster) ----------
SEUIL_AVERTISSEMENTS = 3   # après X insultes ciblées -> sourdine
TIMEOUT_REPETITION = 30    # minutes
TIMEOUT_MENACE = 60        # minutes (sourdine immédiate pour une menace)

# ---------- Détection ----------
INSULTES = {
    "abruti", "idiot", "idiote", "debile", "imbecile", "cretin", "cretine",
    "con", "conne", "connard", "connasse", "salope", "pute", "encule", "enfoire",
    "ordure", "minable", "degenere", "attarde", "merdeux", "raclure", "fdp", "ntm",
}

# Formules qui visent toujours quelqu'un
PHRASES_CIBLEES = re.compile(
    r"\b(ferme (ta|la) gueule|ta gueule|va te faire (foutre|enculer|voir)|nique ta mere|pauvre (con|type))\b"
)
# Marqueurs de 2e personne : "tu es un ...", "t'es un ...", "espèce de ..."
DEUXIEME_PERSONNE = re.compile(r"\b(tu es|t es|tu etais|toi|espece d(?:e)?|vous etes|ferme ta)\b")

_V = (r"(?:tue|tuer|bute|buter|defonce|defoncer|fracasse|fracasser|egorge|egorger|"
      r"massacre|massacrer|decoupe|decouper|eclate|eclater|tabasse|tabasser|frappe|frapper|"
      r"agresse|agresser|viole|violer|brule|bruler|etrangle|etrangler|creve|crever)")
_SUJET = r"(?:je|j|jvais|jv|on)"
_AUX = r"(?:(?:vais|v|va|vas) )?"

MENACES = [re.compile(p) for p in [
    rf"\b{_SUJET} {_AUX}(?:te|t|vous) {_V}\b",
    r"\bje sais ou tu (?:habites|vis|dors|travailles)\b",
    r"\btu vas (?:mourir|crever|le regretter|payer cher|y passer)\b",
    r"\b(?:tu es|t es) (?:mort|morte)\b",
    r"(?<!il )(?<!elle )(?<!ca )\bva te (?:suicider|pendre|tuer|crever)\b",
    r"\bkys\b",
    r"\bcreve (?:sale|espece|connard|connasse|salope|enfoire|abruti)\b",
    r"\bsi je te croise\b",
    r"\bfais gaffe a toi\b",
    r"\bje vais (?:te )?(?:faire (?:du mal|payer|regretter)|venir chez toi)\b",
    # Cyberharcèlement
    r"\b(?:je|j) (?:vais )?(?:te )?(?:dox|doxx|doxxer|pirater|hacker|ddos|ddosser)\b",
    r"\b(?:je|j) (?:vais )?(?:balancer|leak|leaker|publier|poster|donner|divulguer) (?:ton|ta|tes) "
    r"(?:adresse|ip|numero|nom|photos?|infos|identite)\b",
    r"\bje (?:connais|vois|ai) ton (?:ip|adresse)\b",
]]


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, remplace 0/4/1/3/5/@/$ par des lettres."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return texte.translate(str.maketrans("04135@$", "oaiesas"))


def nettoyer(contenu: str) -> str:
    """Prépare le texte pour l'analyse (retire mentions, ponctuation, accents...)."""
    contenu = re.sub(r"<[^>\s]+>", " ", contenu)       # <@123>, <#123>, emojis perso
    contenu = re.sub(r"(?<!\S)@\S+", " ", contenu)     # "@pseudo" tapé à la main
    texte = normaliser(contenu)
    texte = re.sub(r"[^a-z0-9 ]", " ", texte)          # j'vais -> j vais
    return re.sub(r"\s+", " ", texte).strip()


def mention_texte(contenu: str) -> bool:
    """Détecte un '@pseudo' écrit à la main (même sans ping réel)."""
    return bool(re.search(r"(?<!\S)@(?!everyone\b|here\b)\w+", contenu))


def detecte_menace(texte: str) -> bool:
    return any(p.search(texte) for p in MENACES)


def insulte_ciblee(texte: str, cible: bool, extra: frozenset = frozenset()) -> bool:
    """Insulte dirigée vers quelqu'un : mention, réponse, ou formulation en 'tu'."""
    if PHRASES_CIBLEES.search(texte):
        return True
    mots = "|".join(map(re.escape, INSULTES | set(extra)))
    if not re.search(rf"\b(?:{mots})s?\b", texte):
        return False
    return cible or bool(DEUXIEME_PERSONNE.search(texte))


class Protection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.config: dict[int, dict] = {}  # guild_id -> {"actif": bool, "logs": int|None}

    async def cog_load(self):
        self.db = await aiosqlite.connect(get_database_path())
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS protection "
            "(guild_id INTEGER PRIMARY KEY, actif INTEGER DEFAULT 1, logs_id INTEGER)"
        )
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS avertissements "
            "(guild_id INTEGER, user_id INTEGER, nb INTEGER DEFAULT 0, "
            "PRIMARY KEY (guild_id, user_id))"
        )
        await self.db.commit()
        async with self.db.execute("SELECT guild_id, actif, logs_id FROM protection") as cur:
            async for guild_id, actif, logs_id in cur:
                self.config[guild_id] = {"actif": bool(actif), "logs": logs_id}

    async def cog_unload(self):
        await self.db.close()

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
        else:
            raise error

    # ---------- Analyse des messages ----------

    def a_une_cible(self, message: discord.Message) -> bool:
        if any(not m.bot and m.id != message.author.id for m in message.mentions):
            return True
        ref = message.reference.resolved if message.reference else None
        if isinstance(ref, discord.Message) and not ref.author.bot and ref.author.id != message.author.id:
            return True
        return mention_texte(message.content)

    async def verifier(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        if not self.config.get(message.guild.id, {}).get("actif", True):
            return
        if message.author.guild_permissions.manage_messages:
            return  # l'équipe de modération n'est pas filtrée

        texte = nettoyer(message.content)
        automod = self.bot.get_cog("Automod")  # mots perso ajoutés avec /mot_ajouter
        extra = frozenset(automod.mots.get(message.guild.id, set())) if automod else frozenset()

        if detecte_menace(texte):
            await self.sanctionner(message, "menace")
        elif insulte_ciblee(texte, self.a_une_cible(message), extra):
            await self.sanctionner(message, "insulte")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.verifier(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        await self.verifier(after)

    # ---------- Sanctions ----------

    async def ajouter_avertissement(self, guild_id: int, user_id: int) -> int:
        await self.db.execute(
            "INSERT INTO avertissements (guild_id, user_id, nb) VALUES (?, ?, 1) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nb = nb + 1",
            (guild_id, user_id),
        )
        await self.db.commit()
        return await self.nb_avertissements(guild_id, user_id)

    async def nb_avertissements(self, guild_id: int, user_id: int) -> int:
        async with self.db.execute(
            "SELECT nb FROM avertissements WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        ) as cur:
            ligne = await cur.fetchone()
        return ligne[0] if ligne else 0

    async def reinitialiser(self, guild_id: int, user_id: int):
        await self.db.execute(
            "UPDATE avertissements SET nb = 0 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.db.commit()

    async def sanctionner(self, message: discord.Message, type_: str):
        guild, auteur = message.guild, message.author
        actions = []
        try:
            await message.delete()
            actions.append("message supprimé")
        except discord.HTTPException:
            pass  # déjà supprimé, ou permission manquante

        nb = await self.ajouter_avertissement(guild.id, auteur.id)
        minutes = None
        if type_ == "menace":
            minutes = TIMEOUT_MENACE
        elif nb >= SEUIL_AVERTISSEMENTS:
            minutes = TIMEOUT_REPETITION

        mis_en_sourdine = False
        if minutes:
            try:
                await auteur.timeout(timedelta(minutes=minutes), reason=f"Protection : {type_}")
                actions.append(f"sourdine {minutes} min")
                mis_en_sourdine = True
                if type_ == "insulte":
                    await self.reinitialiser(guild.id, auteur.id)
            except discord.HTTPException:
                actions.append("sourdine impossible (rôle trop élevé ?)")

        if type_ == "menace":
            texte = f"{auteur.mention}, les menaces et le harcèlement sont interdits ici."
            if mis_en_sourdine:
                texte += f" Tu es mis en sourdine {minutes} min."
        elif mis_en_sourdine:
            texte = f"{auteur.mention}, trop d'insultes : sourdine de {minutes} min."
        else:
            texte = (f"{auteur.mention}, on n'insulte pas les autres membres. "
                     f"Avertissement {nb}/{SEUIL_AVERTISSEMENTS}.")
        try:
            await message.channel.send(texte, delete_after=8)
        except discord.HTTPException:
            pass

        await self.log(message, type_, actions)

    async def log(self, message: discord.Message, type_: str, actions: list):
        logs_id = self.config.get(message.guild.id, {}).get("logs")
        salon = message.guild.get_channel(logs_id) if logs_id else None
        if not salon:
            return
        menace = type_ == "menace"
        embed = discord.Embed(
            title="🚨 Menace détectée" if menace else "⚠️ Insulte ciblée",
            color=discord.Color.red() if menace else discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Auteur", value=f"{message.author.mention} ({message.author.id})")
        embed.add_field(name="Salon", value=message.channel.mention)
        embed.add_field(name="Actions", value=", ".join(actions) or "aucune (permissions ?)", inline=False)
        contenu = message.content.replace("```", "'''")[:500]
        embed.add_field(name="Message", value=f"```{contenu}```", inline=False)
        try:
            await salon.send(embed=embed)
        except discord.HTTPException:
            pass

    # ---------- Commandes ----------

    @app_commands.command(name="protection_config", description="Active/désactive la protection et choisis le salon de logs")
    @app_commands.describe(actif="Activer ou désactiver la protection", salon_logs="Salon où les alertes sont envoyées")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def protection_config(self, interaction: discord.Interaction,
                                actif: Optional[bool] = None,
                                salon_logs: Optional[discord.TextChannel] = None):
        cfg = self.config.setdefault(interaction.guild_id, {"actif": True, "logs": None})
        if actif is not None:
            cfg["actif"] = actif
        if salon_logs is not None:
            cfg["logs"] = salon_logs.id
        await self.db.execute(
            "INSERT INTO protection (guild_id, actif, logs_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET actif = excluded.actif, logs_id = excluded.logs_id",
            (interaction.guild_id, int(cfg["actif"]), cfg["logs"]),
        )
        await self.db.commit()
        logs = f"<#{cfg['logs']}>" if cfg["logs"] else "aucun"
        await interaction.response.send_message(
            f"Protection : **{'activée' if cfg['actif'] else 'désactivée'}**\nSalon de logs : {logs}",
            ephemeral=True,
        )

    @app_commands.command(name="avertissements", description="Affiche le nombre d'avertissements d'un membre")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def avertissements(self, interaction: discord.Interaction, membre: discord.Member):
        nb = await self.nb_avertissements(interaction.guild_id, membre.id)
        await interaction.response.send_message(
            f"{membre.mention} : {nb}/{SEUIL_AVERTISSEMENTS} avertissement(s).", ephemeral=True
        )

    @app_commands.command(name="avertissements_reset", description="Remet à zéro les avertissements d'un membre")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def avertissements_reset(self, interaction: discord.Interaction, membre: discord.Member):
        await self.reinitialiser(interaction.guild_id, membre.id)
        await interaction.response.send_message(
            f"Avertissements de {membre.mention} remis à zéro.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Protection(bot))
