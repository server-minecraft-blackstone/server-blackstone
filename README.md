# Blackstone — bot Discord

Bot Discord en Python utilisant exclusivement des commandes slash, avec modération, protection, musique et génération de structures de serveurs.

## Commandes Discord

Toutes les fonctionnalités du bot sont accessibles avec des commandes slash (`/`). La commande `/aide` affiche la liste des commandes disponibles. Aucune commande textuelle avec préfixe `!` n'est prévue.

## Configuration

Variables à définir dans **Render → Environment** ou dans un fichier local `.env` :

- `DISCORD_TOKEN` : jeton du bot Discord, obligatoire.
- `ANTHROPIC_API_KEY` : facultative ; nécessaire uniquement pour `/serveur_demande`.
- `CLAUDE_MODEL` : modèle Anthropic à utiliser, par défaut `claude-sonnet-5`.
- `DATA_DIR` : facultative ; dossier de stockage SQLite. Pour conserver les réglages après un redéploiement, configure un disque persistant et indique son point de montage.
- `LOG_LEVEL` : facultative, par défaut `INFO`.

Ne partage jamais le jeton Discord ni la clé API et ne les committe pas dans GitHub.

Dans le [Discord Developer Portal](https://discord.com/developers/applications), active **Message Content Intent** et **Server Members Intent** dans la section Bot. Le bot doit aussi recevoir les permissions Discord correspondant aux fonctions utilisées : voir les salons, envoyer des messages, gérer les messages, modérer les membres et gérer les salons/rôles pour le générateur.

## Lancement local

Python 3.12 est recommandé :

```bash
python -m venv .venv
# Windows : .venv\\Scripts\\activate
# Linux/macOS : source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

La musique nécessite FFmpeg et l'accès aux salons vocaux. Le `Dockerfile` installe FFmpeg et libopus pour un déploiement Docker.

## Déploiement Render

Le bot ouvre une route HTTP sur le port `PORT` lorsque Render fournit cette variable. Pour les commandes vocales, déploie avec le `Dockerfile` afin d'avoir FFmpeg et libopus. Renseigne les variables d'environnement dans Render ; ne les écris pas en dur dans le code.

## Vérifications

Les tests d'intégration légers importent chaque extension et valident les modèles de serveur :

```bash
python -m compileall -q main.py cogs tests
python -m unittest discover -s tests -v
```

Les tests ne se connectent pas à Discord et n'ont pas besoin de jeton.
