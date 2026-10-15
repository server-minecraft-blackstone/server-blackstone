import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Affiche la latence du bot")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! {ms} ms")

    @app_commands.command(name="aide", description="Liste des commandes")
    async def aide(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Aide",
            description="Commandes disponibles :",
            color=discord.Color.blurple(),
        )
        for cmd in self.bot.tree.get_commands():
            embed.add_field(name=f"/{cmd.name}", value=cmd.description, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        salon = member.guild.system_channel
        if salon:
            await salon.send(f"Bienvenue {member.mention} !")


async def setup(bot):
    await bot.add_cog(General(bot))
