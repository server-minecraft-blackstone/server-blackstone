import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Charge automatiquement tous les fichiers du dossier cogs/
        for fichier in os.listdir("cogs"):
            if fichier.endswith(".py"):
                await self.load_extension(f"cogs.{fichier[:-3]}")
        await self.tree.sync()  # enregistre les commandes slash

    async def on_ready(self):
        print(f"Connecté en tant que {self.user}")


bot = Bot()
bot.run(os.getenv("DISCORD_TOKEN"))
