import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("blackstone.general")


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Affiche la latence du bot")
    async def ping(self, interaction: discord.Interaction) -> None:
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! {ms} ms")

    @app_commands.command(name="aide", description="Liste les commandes disponibles")
    async def aide(self, interaction: discord.Interaction) -> None:
        commandes = sorted(
            self.bot.tree.walk_commands(),
            key=lambda commande: commande.qualified_name,
        )
        lignes = [
            f"`/{commande.qualified_name}` — "
            f"{commande.description or 'Aucune description.'}"
            for commande in commandes
        ]
        lignes.insert(0, "`!help` — Aide rapide")
        lignes.insert(1, "`!help-all` — Liste complète des commandes")
        if not lignes:
            lignes = ["Aucune commande enregistrée pour le moment."]

        # Descriptions de taille maîtrisée : aucun embed ne dépasse les limites Discord.
        pages: list[discord.Embed] = []
        lot: list[str] = []
        taille = 0
        for ligne in lignes:
            ligne = ligne[:180]
            if lot and (len(lot) >= 18 or taille + len(ligne) + 1 > 3500):
                pages.append(self._creer_embed(lot, len(pages) + 1))
                lot, taille = [], 0
            lot.append(ligne)
            taille += len(ligne) + 1
        if lot:
            pages.append(self._creer_embed(lot, len(pages) + 1, total=len(lignes)))

        await interaction.response.send_message(embed=pages[0], ephemeral=True)
        for page in pages[1:]:
            await interaction.followup.send(embed=page, ephemeral=True)

    @staticmethod
    def _creer_embed(lignes: list[str], numero: int, total: int | None = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"Aide — Blackstone ({numero})",
            description="\n".join(lignes),
            color=discord.Color.blurple(),
        )
        if total is not None:
            embed.set_footer(text=f"{total} entrée(s) • Préfixe texte : ! • Commandes slash : /")
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        salon = member.guild.system_channel
        if not salon:
            return
        try:
            await salon.send(f"Bienvenue {member.mention} !")
        except discord.HTTPException:
            logger.exception(
                "Impossible d'envoyer le message de bienvenue dans le serveur %s",
                member.guild.id,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
