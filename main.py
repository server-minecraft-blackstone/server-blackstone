import os
import logging

import discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("blackstone")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


async def demarrer_serveur_web():
    """Render (Web Service) exige un port ouvert : on répond « OK » sur $PORT."""
    app = web.Application()
    app.router.add_get("/", lambda requete: web.Response(text="Bot en ligne"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ["PORT"])).start()


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        if os.getenv("PORT"):  # variable définie automatiquement par Render
            await demarrer_serveur_web()
            logger.info("Serveur web démarré sur le port %s", os.environ["PORT"])

        # Charge chaque module ; si l'un plante, les autres démarrent quand même
        for fichier in sorted(os.listdir("cogs")):
            if fichier.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{fichier[:-3]}")
                    logger.info("Cog chargé : %s", fichier)
                except Exception:
                    logger.exception("Échec du chargement du cog %s", fichier)

        try:
            commandes = await self.tree.sync()
            logger.info("%s commande(s) slash synchronisée(s)", len(commandes))
        except Exception:
            logger.exception("Échec de la synchronisation des commandes slash")
            raise

    async def on_ready(self):
        logger.info("Connecté en tant que %s (ID: %s)", self.user, self.user.id)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Ne pollue pas les salons pour les messages qui ne sont pas des commandes.
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Argument manquant : `{ctx.prefix}{ctx.command.qualified_name} {error.param.name}`")
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Tu n'as pas la permission d'utiliser cette commande.")
            return
        logger.error(
            "Erreur de commande !%s par %s dans le serveur %s",
            ctx.command, ctx.author, getattr(ctx.guild, "id", "DM"),
            exc_info=(type(error), error, error.__traceback__),
        )
        await ctx.send("Une erreur est survenue pendant l'exécution de la commande.")

    @commands.command(name="help", aliases=["aide"], help="Affiche les commandes principales.")
    async def help_prefix(self, ctx):
        embed = discord.Embed(
            title="Aide — Blackstone",
            description="Préfixe des commandes texte : `!`\nLes commandes slash restent disponibles avec `/`.",
            color=discord.Color.blurple(),
        )
        commandes_prefixe = sorted(
            (cmd for cmd in self.commands if not cmd.hidden and cmd.name not in ("help", "help-all")),
            key=lambda cmd: cmd.name,
        )
        if commandes_prefixe:
            embed.add_field(
                name="Commandes avec !",
                value="\n".join(f"`!{cmd.name}` — {cmd.help or 'Aucune description.'}" for cmd in commandes_prefixe),
                inline=False,
            )
        commandes_slash = sorted(self.tree.get_commands(), key=lambda cmd: cmd.name)
        if commandes_slash:
            embed.add_field(
                name="Commandes slash",
                value="\n".join(f"`/{cmd.name}` — {cmd.description or 'Aucune description.'}" for cmd in commandes_slash[:20]),
                inline=False,
            )
            if len(commandes_slash) > 20:
                embed.set_footer(text="Utilise !help-all pour afficher toutes les commandes.")
        await ctx.send(embed=embed)

    @commands.command(name="help-all", aliases=["aide-tout"], help="Affiche toutes les commandes, y compris les sous-commandes.")
    async def help_all(self, ctx):
        """Envoie la liste complète en plusieurs messages pour respecter les limites Discord."""
        lignes = []
        commandes_prefixe = sorted(
            (cmd for cmd in self.commands if not cmd.hidden and cmd.name not in ("help", "help-all")),
            key=lambda cmd: cmd.name,
        )
        lignes.extend(
            f"`!{cmd.name}` — {cmd.help or 'Aucune description.'}"
            for cmd in commandes_prefixe
        )

        commandes_slash = sorted(self.tree.walk_commands(), key=lambda cmd: cmd.qualified_name)
        lignes.extend(
            f"`/{cmd.qualified_name}` — {cmd.description or 'Aucune description.'}"
            for cmd in commandes_slash
        )

        if not lignes:
            await ctx.send("Aucune commande enregistrée.")
            return

        # Des lots de 15 lignes gardent les messages sous la limite d'un embed Discord.
        lots = [lignes[i:i + 15] for i in range(0, len(lignes), 15)]
        total = len(lots)
        for numero, lot in enumerate(lots, start=1):
            embed = discord.Embed(
                title=f"Toutes les commandes — Blackstone ({numero}/{total})",
                description="\n".join(lot),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=f"{len(lignes)} commande(s) au total • Préfixe texte : ! • Commandes slash : /")
            await ctx.send(embed=embed)


token = os.getenv("DISCORD_TOKEN")
if not token:
    raise SystemExit("DISCORD_TOKEN manquant : ajoute-le dans l'onglet Environment de Render.")

bot = Bot()
try:
    bot.run(token)
except discord.PrivilegedIntentsRequired:
    raise SystemExit(
        "Active « Message Content Intent » et « Server Members Intent » "
        "dans le Developer Portal (onglet Bot), puis redéploie."
    )
