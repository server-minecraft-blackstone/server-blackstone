from __future__ import annotations

import logging
import os
from pathlib import Path

import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("blackstone")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


async def demarrer_serveur_web() -> web.AppRunner:
    """Render demande un port HTTP ouvert pour les Web Services."""
    async def health(_requete: web.Request) -> web.Response:
        return web.Response(text="Bot en ligne", content_type="text/plain")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ["PORT"])
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner


class BlackstoneBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        # Centralise les erreurs des commandes slash sans bloquer le bot.
        self.tree.error(self.on_app_command_error)
        self.web_runner: web.AppRunner | None = None

    async def setup_hook(self) -> None:
        if os.getenv("PORT"):
            self.web_runner = await demarrer_serveur_web()
            logger.info("Serveur web démarré sur le port %s", os.environ["PORT"])

        dossier_cogs = BASE_DIR / "cogs"
        if not dossier_cogs.is_dir():
            logger.error("Dossier des extensions introuvable : %s", dossier_cogs)
        else:
            fichiers = sorted(
                p for p in dossier_cogs.glob("*.py")
                if not p.name.startswith("_")
            )
            logger.info("%s extension(s) détectée(s) dans %s", len(fichiers), dossier_cogs)
            for fichier in fichiers:
                extension = f"cogs.{fichier.stem}"
                try:
                    await self.load_extension(extension)
                    logger.info("Cog chargé : %s", fichier.name)
                except Exception:
                    logger.exception("Échec du chargement du cog %s", fichier.name)

        # Une panne de synchronisation ne doit pas empêcher les événements du bot de démarrer.
        try:
            commandes = await self.tree.sync()
            logger.info("%s commande(s) slash synchronisée(s)", len(commandes))
        except Exception:
            logger.exception(
                "Échec de la synchronisation des commandes slash ; "
                "le bot reste en ligne mais les commandes slash peuvent être anciennes."
            )

    async def on_ready(self) -> None:
        logger.info("Connecté en tant que %s (ID: %s)", self.user, self.user.id if self.user else "?")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"Argument manquant : `{ctx.prefix}{ctx.command.qualified_name} "
                f"{error.param.name}`"
            )
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Tu n'as pas la permission d'utiliser cette commande.")
            return

        original = getattr(error, "original", error)
        logger.error(
            "Erreur de commande préfixée inattendue %s par %s dans le serveur %s",
            getattr(ctx.command, "qualified_name", "inconnue"),
            ctx.author,
            getattr(ctx.guild, "id", "DM"),
            exc_info=(type(original), original, original.__traceback__),
        )
        try:
            await ctx.send("Une erreur est survenue pendant l'exécution de la commande.")
        except discord.HTTPException:
            logger.debug("Impossible d'envoyer le message d'erreur de commande.", exc_info=True)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "Tu n'as pas la permission d'utiliser cette commande."
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"Patiente encore {max(1, int(error.retry_after))} s avant de réessayer."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Tu ne peux pas utiliser cette commande dans ce contexte."
        elif isinstance(error, app_commands.TransformerError):
            message = "Un des paramètres fournis est invalide."
        else:
            original = getattr(error, "original", error)
            logger.error(
                "Erreur slash /%s par %s",
                getattr(interaction.command, "qualified_name", "inconnue"),
                interaction.user,
                exc_info=(type(original), original, original.__traceback__),
            )
            message = "Une erreur est survenue pendant l'exécution de la commande."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.debug("Impossible de signaler l'erreur slash à l'utilisateur.", exc_info=True)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN manquant : ajoute-le dans l'environnement de Render.")

    bot = BlackstoneBot()
    try:
        bot.run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired as exc:
        raise SystemExit(
            "Active « Message Content Intent » et « Server Members Intent » "
            "dans le Developer Portal (onglet Bot), puis redéploie."
        ) from exc


if __name__ == "__main__":
    main()
