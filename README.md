# Jarvis OS

Assistant vocal personnel : application Electron avec interface graphique, propulsée par Pipecat (WebRTC), OpenAI, Deepgram et Cartesia.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen.svg)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

---

## Vision

Jarvis est un **assistant vocal desktop** : tu parles, il répond par la voix. L’app embarque un bot Pipecat (STT, LLM, TTS) et une interface moderne pour te connecter, configurer les clés API et les paramètres (audio, voix, langue). On peut construire une version installable (Windows, Linux, macOS) : au premier lancement, l’app installe elle-même Python, uv et les dépendances, et affiche les étapes dans l’écran de chargement.

---

## Table des matières

- [Technologies](#technologies)
- [Prérequis](#prérequis)
- [Installation et build](#installation-et-build)
  - [Utilisateurs : installer l’app](#utilisateurs--installer-lapp)
  - [Développeurs : lancer en dev](#développeurs--lancer-en-dev)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Structure du projet](#structure-du-projet)
- [Build multi-plateformes](#build-multi-plateformes)
- [Dépannage](#dépannage)
- [Contribution](#contribution)
- [Créateur](#créateur)
- [Licence](#licence)

---

## Technologies

| Rôle | Stack |
|------|--------|
| **Desktop** | Electron |
| **Voix (STT)** | Deepgram |
| **LLM** | OpenAI (GPT-4o-mini) |
| **Voix (TTS)** | Cartesia |
| **Pipeline vocal** | Pipecat (WebRTC) |
| **Python** | uv, pyproject.toml |

L’UI est en HTML/CSS/JS (vanilla) dans `webapp/statics/`. Données locales (profil, clés API, paramètres) en SQLite via `better-sqlite3`.

---

## Prérequis

**Pour utiliser l’app buildée :** aucun. L’installer, la lancer : au premier démarrage, elle installe Python, uv et `uv sync` et affiche les étapes.

**Pour développer :**

- **Node.js** >= 18 (avec npm)
- **Python** 3.10+
- **uv** – [Installation](https://docs.astral.sh/uv/getting-started/installation)

**Clés API (obligatoires pour le bot) :**

- **OpenAI** – [Clé](https://platform.openai.com/api-keys)
- **Deepgram** – [Clé](https://console.deepgram.com/signup)
- **Cartesia** – [Clé](https://play.cartesia.ai/sign-up)

Elles se configurent dans **Paramètres > Général > Clés API** (stockées en base).

---

## Installation et build

Tout se fait depuis le dossier **`webapp/`**.

### Utilisateurs : installer l’app

1. Cloner le dépôt, aller dans `webapp` :
   ```bash
   git clone https://github.com/votre-username/jarvis-OS.git
   cd jarvis-OS/webapp
   ```

2. Construire selon ta plateforme :
   ```bash
   npm install
   npm run build:win    # Windows
   npm run build:linux  # Linux
   npm run build:mac    # macOS
   ```

3. Installer et lancer :
   - **Windows** : `dist/Jarvis Setup 1.0.0.exe` (NSIS) ou `dist/Jarvis 1.0.0.exe` (portable)
   - **Linux** : `dist/*.AppImage` ou `dist/*.deb`
   - **macOS** : `dist/*.dmg`

Au **premier lancement**, l’app va :

1. Vérifier / installer **uv**
2. Installer **Python** (via uv)
3. Lancer **uv sync** (dépendances du bot)

Tu vois ces étapes dans l’écran de chargement. Ensuite, onboarding (profil) puis interface principale.

### Développeurs : lancer en dev

1. Dans `webapp/` :
   ```bash
   npm install
   ```

2. Préparer le bot Python (uv, venv, deps) :
   ```bash
   uv sync
   ```
   Depuis la racine de `webapp` (où se trouve `pyproject.toml`).

3. Lancer l’app Electron :
   ```bash
   npm run dev
   ```

En dev, pas d’étape “setup” (Python/uv) : on suppose que uv et le venv sont déjà prêts. Le bot est lancé via `python start_bot.py` (qui fait `uv run bot.py`).

---

## Configuration

- **Clés API** : Paramètres > Général > Clés API. Enregistrer OpenAI, Deepgram, Cartesia.
- **Audio** : Paramètres > Audio. Choix du micro et des haut-parleurs.
- **Jarvis** : Paramètres > Général > Jarvis. Voix (ex. Femme) et langue (ex. Anglais) pour l’assistant.

Le fichier `.env` est généré automatiquement à partir des clés stockées en base (ne pas éditer à la main). Profil, clés et paramètres sont stockés dans une SQLite locale (userData Electron : `%APPDATA%\jarvis-electron\` sur Windows, `~/.config/jarvis-electron/` sur Linux, `~/Library/Application Support/jarvis-electron/` sur macOS).

---

## Utilisation

1. Lancer l’app (installée ou `npm run dev`).
2. Attendre la fin du chargement (et du setup au premier lancement).
3. Configurer les clés API si ce n’est pas déjà fait.
4. Cliquer sur **Connexion** pour établir la session WebRTC avec le bot.
5. Parler : l’assistant répond par la voix. Les échanges apparaissent dans le chat “Système”.

Boutons utiles : connexion/déconnexion, mute micro.

---

## Structure du projet

```
jarvis-OS/
├── webapp/                    # Application Jarvis (Electron + Pipecat)
│   ├── electron/              # Process main, preload, DB
│   │   ├── main.js
│   │   ├── preload.js
│   │   └── database.js
│   ├── statics/src/           # UI (HTML, CSS, JS)
│   │   ├── index.html
│   │   ├── css/
│   │   └── js/                # voice, loading, onboarding, settings, etc.
│   ├── scripts/               # Build
│   │   ├── prepare-build.js   # Copie bot + pyproject, uv lock
│   │   └── download-uv.js     # Télécharge uv par plateforme
│   ├── bot.py                 # Bot Pipecat (STT/LLM/TTS)
│   ├── start_bot.py           # Lance uv run bot.py
│   ├── pyproject.toml
│   ├── package.json
│   └── README.md
├── README.md                  # Ce fichier
└── LICENSE.md
```

Le reste du dépôt (ex. `server/`, `skills/`, `bridges/`) peut exister pour d’anciens usages ; l’app actuelle tourne entièrement dans **`webapp/`**.

---

## Build multi-plateformes

| Commande | Rôle |
|----------|------|
| `npm run build:win` | Build Windows (NSIS + portable) |
| `npm run build:linux` | Build Linux (AppImage, deb) |
| `npm run build:mac` | Build macOS (dmg) |
| `npm run build:all` | Download uv pour toutes les plateformes puis build Win + Linux + Mac |

En pratique, construire Windows sous Windows, Linux sous Linux, macOS sous macOS. `build:all` est utile en CI.

---

## Dépannage

**Le bot ne démarre pas**

- Vérifier que le port **7860** est libre (`netstat -ano | findstr :7860` sur Windows, `lsof -i :7860` sur Linux/macOS).
- Vérifier les clés API dans Paramètres > Général.

**Erreur `better-sqlite3`**

- `npx electron-rebuild` ou `npm install` dans `webapp/`.

**Pas de son / TTS**

- Vérifier la clé **Cartesia** et le périphérique de sortie dans Paramètres > Audio.

**Micro inopérant**

- Autoriser le micro dans l’OS, choisir le bon périphérique dans Paramètres > Audio.

---

## Contribution

Issues et pull requests bienvenues. Voir [CONTRIBUTING](.github/CONTRIBUTING.md).  
Discord : [Rejoindre le serveur](https://discord.gg/STEdPHu6Sx).

---

## Créateur

**Barth** – [YouTube @barthH95](https://www.youtube.com/@BarthH95)

---

## Licence

MIT. Voir [LICENSE.md](LICENSE.md).
