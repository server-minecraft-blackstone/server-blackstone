from __future__ import annotations

"""Pont de compatibilité : les anciennes commandes slash deviennent des commandes !."""

import inspect
from typing import Any

import discord
from discord.ext import commands


async def _ctx_send(ctx: commands.Context, content=None, *, embed=None, embeds=None, view=None,
                    delete_after=None, **kwargs):
    options = dict(view=view, delete_after=delete_after, **kwargs)
    if embed is not None:
        options["embed"] = embed
    if embeds is not None:
        options["embeds"] = embeds
    message = await ctx.send(content, **options)
    return message


class _Response:
    def __init__(self, interaction: "_ContextInteraction"):
        self.i = interaction
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content=None, *, embed=None, embeds=None, view=None,
                           ephemeral=False, delete_after=None, **kwargs):
        self._done = True
        message = await _ctx_send(self.i.ctx, content, embed=embed, embeds=embeds,
                                  view=view, delete_after=delete_after, **kwargs)
        self.i.last_message = message
        return message

    async def defer(self, *, ephemeral=False, thinking=False, **kwargs):
        self._done = True
        return None

    async def edit_message(self, *, content=None, embed=None, embeds=None, view=None, **kwargs):
        self._done = True
        message = await _ctx_send(self.i.ctx, content, embed=embed, embeds=embeds, view=view, **kwargs)
        self.i.last_message = message
        return message


class _Followup:
    def __init__(self, interaction: "_ContextInteraction"):
        self.i = interaction

    async def send(self, content=None, *, embed=None, embeds=None, view=None,
                   ephemeral=False, wait=False, **kwargs):
        return await self.i.ctx.send(content, embed=embed, embeds=embeds, view=view, **kwargs)


class _ContextInteraction:
    """Expose the subset of discord.Interaction used by the existing command handlers."""
    def __init__(self, ctx: commands.Context):
        self.ctx = ctx
        self.user = ctx.author
        self.guild = ctx.guild
        self.guild_id = ctx.guild.id if ctx.guild else None
        self.channel = ctx.channel
        self.client = ctx.bot
        self.response = _Response(self)
        self.followup = _Followup(self)
        self.command = None
        self.last_message = None

    async def original_response(self):
        return self.last_message or self.ctx.message

    async def edit_original_response(self, *, content=None, embed=None, view=None, **kwargs):
        message = await _ctx_send(self.ctx, content, embed=embed, view=view, **kwargs)
        self.last_message = message
        return message


async def _member(ctx: commands.Context, value: str) -> discord.Member:
    return await commands.MemberConverter().convert(ctx, value)


async def _text_channel(ctx: commands.Context, value: str) -> discord.TextChannel:
    return await commands.TextChannelConverter().convert(ctx, value)


class PrefixCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None

    async def _call(self, ctx: commands.Context, cog_name: str, method: str, *args):
        cog = self.bot.get_cog(cog_name)
        if cog is None:
            return await ctx.send(f"Le module {cog_name} n'est pas chargé.")
        handler = getattr(cog, method)
        return await handler(_ContextInteraction(ctx), *args)

    # Général
    @commands.command(name="ping", help="Affiche la latence du bot.")
    async def ping(self, ctx):
        await ctx.send(f"Pong ! {round(self.bot.latency * 1000)} ms")

    # Automodération
    @commands.command(name="interdire", help="!interdire insultes #salon ou !interdire liens #salon")
    @commands.has_guild_permissions(manage_guild=True)
    async def interdire(self, ctx, regle: str, salon: str):
        regle = regle.lower()
        if regle not in ("insultes", "liens"):
            return await ctx.send("Règle invalide. Choisis : insultes ou liens.")
        cible = await _text_channel(ctx, salon)
        await self._call(ctx, "Automod", "interdire", 
                         __import__("discord").app_commands.Choice(name=regle.capitalize(), value=regle), cible)

    @commands.command(name="autoriser", help="!autoriser insultes #salon ou !autoriser liens #salon")
    @commands.has_guild_permissions(manage_guild=True)
    async def autoriser(self, ctx, regle: str, salon: str):
        regle = regle.lower()
        if regle not in ("insultes", "liens"):
            return await ctx.send("Règle invalide. Choisis : insultes ou liens.")
        cible = await _text_channel(ctx, salon)
        await self._call(ctx, "Automod", "autoriser",
                         __import__("discord").app_commands.Choice(name=regle.capitalize(), value=regle), cible)

    @commands.command(name="regles", help="Affiche les règles de filtrage configurées.")
    async def regles(self, ctx):
        await self._call(ctx, "Automod", "regles_cmd")

    @commands.command(name="mot_ajouter", help="!mot_ajouter <mot> (permission Gérer le serveur)")
    @commands.has_guild_permissions(manage_guild=True)
    async def mot_ajouter(self, ctx, *, mot: str):
        await self._call(ctx, "Automod", "mot_ajouter", mot)

    @commands.command(name="mot_retirer", help="!mot_retirer <mot> (permission Gérer le serveur)")
    @commands.has_guild_permissions(manage_guild=True)
    async def mot_retirer(self, ctx, *, mot: str):
        await self._call(ctx, "Automod", "mot_retirer", mot)

    # Modération
    @commands.command(name="kick", help="!kick @membre [raison]")
    @commands.has_guild_permissions(kick_members=True)
    async def kick(self, ctx, membre: str, *, raison="Aucune raison"):
        await self._call(ctx, "Moderation", "kick", await _member(ctx, membre), raison)

    @commands.command(name="ban", help="!ban @membre [raison]")
    @commands.has_guild_permissions(ban_members=True)
    async def ban(self, ctx, membre: str, *, raison="Aucune raison"):
        await self._call(ctx, "Moderation", "ban", await _member(ctx, membre), raison)

    @commands.command(name="timeout", help="!timeout @membre <minutes>")
    @commands.has_guild_permissions(moderate_members=True)
    async def timeout(self, ctx, membre: str, minutes: int):
        if not 1 <= minutes <= 40320:
            return await ctx.send("La durée doit être comprise entre 1 et 40320 minutes.")
        await self._call(ctx, "Moderation", "timeout", await _member(ctx, membre), minutes)

    @commands.command(name="clear", help="!clear <nombre de messages, entre 1 et 100>")
    @commands.has_guild_permissions(manage_messages=True)
    async def clear(self, ctx, nombre: int):
        if not 1 <= nombre <= 100:
            return await ctx.send("Le nombre doit être compris entre 1 et 100.")
        await self._call(ctx, "Moderation", "clear", nombre)

    # Musique
    @commands.command(name="rejoindre", help="Fait rejoindre au bot ton salon vocal.")
    async def rejoindre(self, ctx):
        await self._call(ctx, "Musique", "rejoindre")

    @commands.command(name="jouer", help="!jouer <nom de fichier audio ou URL directe>")
    async def jouer(self, ctx, *, source: str):
        await self._call(ctx, "Musique", "jouer", source)

    @commands.command(name="pause", help="Met la musique en pause.")
    async def pause(self, ctx):
        await self._call(ctx, "Musique", "pause")

    @commands.command(name="reprendre", help="Reprend la musique.")
    async def reprendre(self, ctx):
        await self._call(ctx, "Musique", "reprendre")

    @commands.command(name="passer", help="Passe au morceau suivant.")
    async def passer(self, ctx):
        await self._call(ctx, "Musique", "passer")

    @commands.command(name="stop", help="Arrête la musique et vide la file.")
    async def stop(self, ctx):
        await self._call(ctx, "Musique", "stop")

    @commands.command(name="quitter", help="Déconnecte le bot du salon vocal.")
    async def quitter(self, ctx):
        await self._call(ctx, "Musique", "quitter")

    @commands.command(name="volume", help="!volume <1-100>")
    async def volume(self, ctx, valeur: int):
        if not 1 <= valeur <= 100:
            return await ctx.send("Le volume doit être compris entre 1 et 100.")
        await self._call(ctx, "Musique", "volume", valeur)

    @commands.command(name="file", help="Affiche la lecture et la file d'attente.")
    async def file_attente(self, ctx):
        await self._call(ctx, "Musique", "file_attente")

    # Protection
    @commands.command(name="protection_config", help="!protection_config <on|off> [#salon-logs]")
    @commands.has_guild_permissions(manage_guild=True)
    async def protection_config(self, ctx, actif: str = None, salon_logs: str = None):
        if actif is not None and actif.lower() not in ("on", "off", "oui", "non", "true", "false"):
            return await ctx.send("Utilise on ou off.")
        valeur = None if actif is None else actif.lower() in ("on", "oui", "true")
        salon = await _text_channel(ctx, salon_logs) if salon_logs else None
        await self._call(ctx, "Protection", "protection_config", valeur, salon)

    @commands.command(name="avertissements", help="!avertissements @membre")
    @commands.has_guild_permissions(moderate_members=True)
    async def avertissements(self, ctx, membre: str):
        await self._call(ctx, "Protection", "avertissements", await _member(ctx, membre))

    @commands.command(name="avertissements_reset", help="!avertissements_reset @membre")
    @commands.has_guild_permissions(moderate_members=True)
    async def avertissements_reset(self, ctx, membre: str):
        await self._call(ctx, "Protection", "avertissements_reset", await _member(ctx, membre))

    # Générateur
    @commands.command(name="serveur_modeles", help="Liste les modèles de serveurs disponibles.")
    async def serveur_modeles(self, ctx):
        await self._call(ctx, "Generateur", "serveur_modeles")

    @commands.command(name="serveur_modele", help="!serveur_modele <nom du modèle>")
    @commands.has_guild_permissions(administrator=True)
    async def serveur_modele(self, ctx, *, modele: str):
        from cogs.generateur import MODELES
        cle = next((k for k, v in MODELES.items()
                    if k.lower() == modele.lower() or v["nom"].lower() == modele.lower()), None)
        if cle is None:
            noms = ", ".join(v["nom"] for v in MODELES.values())
            return await ctx.send(f"Modèle inconnu. Choix disponibles : {noms}")
        await self._call(ctx, "Generateur", "serveur_modele",
                         __import__("discord").app_commands.Choice(name=MODELES[cle]["nom"], value=cle))

    @commands.command(name="serveur_demande", help="!serveur_demande <description du serveur voulu>")
    @commands.has_guild_permissions(administrator=True)
    async def serveur_demande(self, ctx, *, demande: str):
        if len(demande) < 10 or len(demande) > 1500:
            return await ctx.send("La description doit contenir entre 10 et 1500 caractères.")
        await self._call(ctx, "Generateur", "serveur_demande", demande)

    @commands.command(name="serveur_annuler", help="Annule la dernière génération du serveur.")
    @commands.has_guild_permissions(administrator=True)
    async def serveur_annuler(self, ctx):
        await self._call(ctx, "Generateur", "serveur_annuler")


async def setup(bot: commands.Bot):
    await bot.add_cog(PrefixCommands(bot))
