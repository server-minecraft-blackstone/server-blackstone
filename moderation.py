from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Expulse un membre")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membre: discord.Member,
                   raison: str = "Aucune raison"):
        await membre.kick(reason=raison)
        await interaction.response.send_message(f"{membre} a été expulsé. ({raison})")

    @app_commands.command(name="ban", description="Bannit un membre")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, membre: discord.Member,
                  raison: str = "Aucune raison"):
        await membre.ban(reason=raison)
        await interaction.response.send_message(f"{membre} a été banni. ({raison})")

    @app_commands.command(name="timeout", description="Met un membre en sourdine")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, membre: discord.Member,
                      minutes: app_commands.Range[int, 1, 40320]):
        await membre.timeout(timedelta(minutes=minutes))
        await interaction.response.send_message(
            f"{membre} est en sourdine pour {minutes} min."
        )

    @app_commands.command(name="clear", description="Supprime des messages")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction,
                    nombre: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        supprimes = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"{len(supprimes)} messages supprimés.")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
