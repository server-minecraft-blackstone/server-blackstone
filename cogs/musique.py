import asyncio
import ipaddress
import os
import shutil
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from app_paths import ROOT_DIR

import discord
from discord import app_commands
from discord.ext import commands

DOSSIER = Path(os.getenv("MUSIC_DIR", str(ROOT_DIR / "musique"))).expanduser()
if not DOSSIER.is_absolute():
    DOSSIER = ROOT_DIR / DOSSIER
EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus"}

# Les flux distants : reconnexion auto + seuls les protocoles web sont autorisés
OPTIONS_URL = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-protocol_whitelist http,https,tcp,tls,crypto"
    ),
    "options": "-vn",
}
OPTIONS_FICHIER = {"options": "-vn"}


@dataclass
class Etat:
    file: deque = field(default_factory=deque)  # (titre, source, est_url)
    actuel: Optional[str] = None
    volume: float = 0.5


def fichier_local(nom: str) -> Optional[Path]:
    """Renvoie le chemin du fichier SEULEMENT s'il est bien dans le dossier musique."""
    chemin = (DOSSIER / nom).resolve()
    if (
        DOSSIER.resolve() in chemin.parents
        and chemin.is_file()
        and chemin.suffix.lower() in EXTENSIONS
    ):
        return chemin
    return None


async def url_publique(url: str) -> bool:
    """Accepte uniquement http(s) vers une adresse publique (pas localhost / réseau local)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(p.hostname, None)
    except OSError:
        return False
    return all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)


class Musique(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.etats: dict[int, Etat] = {}

    async def cog_load(self):
        DOSSIER.mkdir(exist_ok=True)
        if not shutil.which("ffmpeg"):
            print("⚠️  FFmpeg introuvable : installe-le pour utiliser la musique.")

    def etat(self, guild_id: int) -> Etat:
        return self.etats.setdefault(guild_id, Etat())

    # ---------- Lecture ----------

    async def lancer(self, guild: discord.Guild):
        etat = self.etat(guild.id)
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
        if vc.is_playing() or vc.is_paused():
            return
        if not etat.file:
            etat.actuel = None
            return
        titre, source, est_url = etat.file.popleft()
        etat.actuel = titre
        options = OPTIONS_URL if est_url else OPTIONS_FICHIER
        audio = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(source, **options), volume=etat.volume
        )
        vc.play(audio, after=lambda erreur: self.suivante(guild, erreur))

    def suivante(self, guild: discord.Guild, erreur=None):
        if erreur:
            print(f"Erreur de lecture : {erreur}")
        asyncio.run_coroutine_threadsafe(self.lancer(guild), self.bot.loop)

    async def vider_et_quitter(self, guild: discord.Guild):
        etat = self.etat(guild.id)
        etat.file.clear()
        etat.actuel = None
        if guild.voice_client:
            await guild.voice_client.disconnect()

    async def vc_commun(self, interaction: discord.Interaction):
        """Le bot doit être connecté et l'utilisateur dans le même salon vocal."""
        vc = interaction.guild.voice_client
        voix = interaction.user.voice
        if not vc or not voix or voix.channel != vc.channel:
            await interaction.response.send_message(
                "Tu dois être dans le même salon vocal que moi.", ephemeral=True
            )
            return None
        return vc

    @commands.Cog.listener()
    async def on_voice_state_update(self, membre, avant, apres):
        # Le bot quitte tout seul quand il ne reste que des bots dans le salon
        vc = membre.guild.voice_client
        if vc and vc.channel and all(m.bot for m in vc.channel.members):
            await self.vider_et_quitter(membre.guild)

    # ---------- Commandes ----------

    @app_commands.command(name="rejoindre", description="Le bot rejoint ton salon vocal")
    @app_commands.guild_only()
    async def rejoindre(self, interaction: discord.Interaction):
        voix = interaction.user.voice
        if not voix or not voix.channel:
            return await interaction.response.send_message(
                "Rejoins d'abord un salon vocal.", ephemeral=True
            )
        vc = interaction.guild.voice_client
        await interaction.response.defer()
        try:
            if vc is None:
                await voix.channel.connect()
            elif vc.is_playing() or vc.is_paused():
                return await interaction.followup.send("Je suis en train de jouer ailleurs.")
            else:
                await vc.move_to(voix.channel)
        except (discord.Forbidden, discord.ClientException, asyncio.TimeoutError):
            return await interaction.followup.send("Impossible de rejoindre ce salon (permissions ?).")
        await interaction.followup.send(f"🔊 Connecté à **{voix.channel.name}**.")

    @app_commands.command(name="jouer", description="Joue un fichier du dossier musique ou une URL de flux audio")
    @app_commands.describe(source="Nom d'un fichier, ou URL directe d'un flux audio")
    @app_commands.guild_only()
    async def jouer(self, interaction: discord.Interaction, source: str):
        voix = interaction.user.voice
        if not voix or not voix.channel:
            return await interaction.response.send_message(
                "Rejoins d'abord un salon vocal.", ephemeral=True
            )
        await interaction.response.defer()

        source = source.strip()
        if source.lower().startswith(("http://", "https://")):
            if not await url_publique(source):
                return await interaction.followup.send(
                    "URL refusée : donne l'adresse directe d'un flux audio public."
                )
            morceau = (urlparse(source).hostname, source, True)
        else:
            chemin = fichier_local(source)
            if not chemin:
                return await interaction.followup.send("Fichier introuvable dans le dossier musique.")
            morceau = (chemin.stem, str(chemin), False)

        vc = interaction.guild.voice_client
        if vc is None:
            try:
                vc = await voix.channel.connect()
            except (discord.Forbidden, discord.ClientException, asyncio.TimeoutError):
                return await interaction.followup.send("Impossible de rejoindre ce salon (permissions ?).")
        elif vc.channel != voix.channel:
            return await interaction.followup.send("Je suis déjà dans un autre salon vocal.")

        self.etat(interaction.guild_id).file.append(morceau)
        if vc.is_playing() or vc.is_paused():
            await interaction.followup.send(f"➕ Ajouté à la file : **{morceau[0]}**")
        else:
            await self.lancer(interaction.guild)
            await interaction.followup.send(f"▶️ Lecture : **{morceau[0]}**")

    @jouer.autocomplete("source")
    async def source_autocomplete(self, interaction: discord.Interaction, current: str):
        if not DOSSIER.exists():
            return []
        noms = [f.name for f in sorted(DOSSIER.iterdir()) if f.suffix.lower() in EXTENSIONS]
        return [
            app_commands.Choice(name=n[:100], value=n[:100])
            for n in noms
            if current.lower() in n.lower()
        ][:25]

    @app_commands.command(name="pause", description="Met la musique en pause")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        vc = await self.vc_commun(interaction)
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Pause.")
        elif vc:
            await interaction.response.send_message("Rien n'est en cours de lecture.", ephemeral=True)

    @app_commands.command(name="reprendre", description="Reprend la musique")
    @app_commands.guild_only()
    async def reprendre(self, interaction: discord.Interaction):
        vc = await self.vc_commun(interaction)
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ C'est reparti.")
        elif vc:
            await interaction.response.send_message("La musique n'est pas en pause.", ephemeral=True)

    @app_commands.command(name="passer", description="Passe au morceau suivant")
    @app_commands.guild_only()
    async def passer(self, interaction: discord.Interaction):
        vc = await self.vc_commun(interaction)
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # déclenche automatiquement le morceau suivant
            await interaction.response.send_message("⏭️ Morceau passé.")
        elif vc:
            await interaction.response.send_message("Rien à passer.", ephemeral=True)

    @app_commands.command(name="stop", description="Arrête la musique et vide la file")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        vc = await self.vc_commun(interaction)
        if vc:
            self.etat(interaction.guild_id).file.clear()
            vc.stop()
            await interaction.response.send_message("⏹️ Musique arrêtée, file vidée.")

    @app_commands.command(name="quitter", description="Le bot quitte le salon vocal")
    @app_commands.guild_only()
    async def quitter(self, interaction: discord.Interaction):
        vc = await self.vc_commun(interaction)
        if vc:
            await self.vider_et_quitter(interaction.guild)
            await interaction.response.send_message("👋 À plus !")

    @app_commands.command(name="volume", description="Règle le volume (1 à 100)")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, valeur: app_commands.Range[int, 1, 100]):
        vc = await self.vc_commun(interaction)
        if not vc:
            return
        self.etat(interaction.guild_id).volume = valeur / 100
        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = valeur / 100
        await interaction.response.send_message(f"🔉 Volume : {valeur} %")

    @app_commands.command(name="file", description="Affiche la musique en cours et la file d'attente")
    @app_commands.guild_only()
    async def file_attente(self, interaction: discord.Interaction):
        etat = self.etat(interaction.guild_id)
        vc = interaction.guild.voice_client
        en_cours = etat.actuel if vc and (vc.is_playing() or vc.is_paused()) else None
        lignes = [f"▶️ **{en_cours}**" if en_cours else "Rien en cours."]
        for i, (titre, _, _) in enumerate(list(etat.file)[:10], start=1):
            lignes.append(f"{i}. {titre}")
        if len(etat.file) > 10:
            lignes.append(f"… et {len(etat.file) - 10} autres")
        await interaction.response.send_message("\n".join(lignes), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Musique(bot))
