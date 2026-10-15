import os

import discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

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
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        if os.getenv("PORT"):  # variable définie automatiquement par Render
            await demarrer_serveur_web()
            print("Serveur web démarré sur le port", os.environ["PORT"])
        # Charge chaque module ; si l'un plante, les autres démarrent quand même
        for fichier in sorted(os.listdir("cogs")):
            if fichier.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{fichier[:-3]}")
                    print(f"✅ {fichier} chargé")
                except Exception as e:
                    print(f"❌ {fichier} : {e!r}")
        await self.tree.sync()  # enregistre les commandes slash
        print("Commandes synchronisées")

    async def on_ready(self):
        print(f"Connecté en tant que {self.user}")


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
