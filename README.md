<div align="center">

![Jarvis OS](Cover_Jarvis_Github.png)

# Jarvis OS

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LiveKit](https://img.shields.io/badge/LiveKit-voice-F5A623?style=flat-square)](https://livekit.io)
[![Claude](https://img.shields.io/badge/Claude-Anthropic-8B5CF6?style=flat-square)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)

Assistant personnel IA, texte & voix temps réel, self-hosted, stack open source.

</div>

---

## C'est quoi ?

Jarvis est un assistant personnel IA qui tourne en local. Il expose un serveur FastAPI qui gère à la fois une interface de chat texte et un pipeline vocal temps réel (via LiveKit). Il se connecte au LLM de ton choix, mémorise les conversations, utilise des outils (recherche web, Gmail, Google Calendar, Spotify, vision, exécution de code…) et fait tourner des tâches proactives en arrière-plan (alertes météo, digests d'actualités, etc.).

**Fonctionnalités principales :**

- Pipeline vocal temps réel : STT (Whisper/Deepgram) + LLM + TTS (Piper/ElevenLabs), bridgé via LiveKit
- Mémoire persistante : sessions, topics, auto-consolidation (passe "rêve" nocturne), recherche vectorielle
- Utilisation d'outils : navigateur, Gmail, Google Calendar, Notion, Spotify, runner CLI, filesystem, vision (YOLOv8), météo
- Système de skills : modules autonomes pluggables (ex : chercheur web)
- Moteur proactif : agent en arrière-plan qui envoie des notifications sur déclencheurs (météo, actualités…)
- Multi-LLM : Anthropic Claude, Mistral, Google Gemini, ou modèles Ollama en local
- UI d'administration : dashboard web, widget globe, panneau de contrôle

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Serveur FastAPI (main.py)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ /api/ws  │  │ /api/http│  │  /admin (UI)     │   │
│  └────┬─────┘  └────┬─────┘  └──────────────────┘   │
│       │              │                                │
│  ┌────▼──────────────▼──────────────────────────┐   │
│  │              Gateway  (core/gateway.py)        │   │
│  │   session ──► Agent ──► LLM ──► appels outils │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  Mémoire         Arrière-plan       Proactif         │
│  sessions/       scheduler/         engine/          │
│  topics/         worker/            collectors/      │
│  consolidation   notifications                       │
└──────────────────────────────────────────────────────┘

voice_agent.py  ──LiveKit──►  STT ──► Gateway ──► TTS
```

| Module | Rôle |
|---|---|
| `core/` | Agent, Gateway, SessionManager, Router |
| `llm/` | Abstraction providers (Anthropic, Mistral, Ollama, Gemini) |
| `memory/` | Sessions, topics, index vectoriel, auto-consolidation |
| `tools/` | Tous les outils appelables (navigateur, Gmail, Calendar, vision…) |
| `skills/` | Modules de haut niveau pluggables |
| `audio/` | STT, TTS, VAD, wake word, chunker audio |
| `proactive/` | Moteur proactif + collectors |
| `background/` | Scheduler, worker, file de notifications |
| `agent/` | Agent projet/code autonome (exécuteur Docker) |
| `api/` | Routeurs FastAPI (WS, HTTP, admin, voice, globe…) |
| `config/` | Settings (pydantic-settings), tools.yaml |
| `prompts/` | Prompt système (partie statique + contexte dynamique) |

---

## Prérequis

| Outil | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| [uv](https://docs.astral.sh/uv/) | latest | Gestionnaire de paquets |
| [LiveKit](https://livekit.io/) | cloud ou self-hosted | Pipeline vocal uniquement |
| Docker | optionnel | Requis par la fonctionnalité code-agent |

---

## Installation

```bash
git clone https://github.com/Grominet95/jarvis-OS.git
cd jarvis-OS
./jarvis eclosion
```

Le wizard interactif :
1. Vérifie Python 3.11+ et installe `uv` si absent
2. Installe toutes les dépendances Python (`pyproject.toml`)
3. Demande ta clé API Anthropic (seule clé obligatoire)
4. Demande ton prénom (affiché lors du scan biométrique)
5. Configure ta localisation pour le moteur proactif
6. Propose les modules optionnels (ElevenLabs, LiveKit, AISstream)
7. Télécharge les modèles ML (YOLOv8n, Piper TTS)
8. Génère le `.env` et installe la commande `jarvis` globalement

> La première fois, utilise `./jarvis eclosion`. Le wizard installe ensuite la commande globalement, tu peux utiliser `jarvis` depuis n'importe où.

---

## Démarrage

```bash
jarvis run      # serveur principal  →  localhost:8000/admin
jarvis voice    # pipeline vocal LiveKit (optionnel)
```

Les deux peuvent tourner simultanément : le voice agent délègue au gateway du serveur principal, donc ils partagent la même session, la même mémoire et les mêmes outils.

---

## Configuration

Tout est configuré pendant l'éclosion. Pour modifier une clé après coup, édite `.env` à la racine du projet.

**Intégrations Google (Gmail / Calendar) :** place ton `credentials.json` issu de Google Cloud Console dans `config/google_credentials.json`, puis démarre Jarvis — il ouvrira le flux d'authentification OAuth et sauvegardera les tokens en local (ils sont gitignorés).

**Reconnaissance faciale (séquence Wake Up) :** pour que le scan biométrique te reconnaisse, place une photo de toi (format JPG, visage bien visible, bonne luminosité) dans :

```
vision/faces/référence.jpg
```

Sans cette photo, la séquence de scan s'exécute mais retourne toujours "identité non reconnue". Le dossier `vision/faces/` est gitignorés, ta photo ne sera jamais commitée.

---

## Outils disponibles

| Outil | Description |
|---|---|
| `browser` | Recherche web + scraping de pages |
| `gmail` | Lister les emails récents |
| `calendar` | Lister / créer des événements Google Calendar |
| `spotify` | Contrôle de lecture |
| `notion` | Rechercher et lire des pages |
| `weather` | Météo actuelle (Open-Meteo, sans clé API) |
| `vision` | Capture d'écran + détection d'objets YOLOv8 |
| `filesystem` | Lire des fichiers, chercher par pattern |
| `cli` | Lancer des commandes shell whitelistées (configurées dans `config/tools.yaml`) |
| `memory` | Écrire des notes structurées dans le topic store |

---

## Système de mémoire

| Composant | Ce qu'il stocke |
|---|---|
| `sessions/` | Historique complet des conversations (jsonl par session) |
| `topics/` | Notes long-terme nommées (écrites par l'assistant) |
| `conso/` | Logs de consommation quotidiens (tokens, coût) |
| `initiatives/` | Log des événements proactifs |

Chaque nuit (ou à la demande), **AutoDream** + **ConsolidationAgent** passent sur les sessions récentes et fusionnent les informations pertinentes dans les topics, l'équivalent du sommeil pour consolider la mémoire.

Tous les fichiers mémoire vivent dans `memory_data/` qui est gitignorés, ils restent uniquement sur ta machine.

---

## Dashboard Monde (World Monitor)

L'onglet **Intel Monde** de l'interface Jarvis affiche [World Monitor](https://github.com/Grominet95/dashboard_monde), un tableau de bord géopolitique temps réel (globe 3D, flux d'actualités IA, radars financiers, suivi d'infrastructures).

**Prérequis :** Node.js 18+

```bash
git clone https://github.com/Grominet95/dashboard_monde.git
cd dashboard_monde
npm install
npm run dev -- --port 3000
```

Une fois lancé sur `http://localhost:3000`, l'onglet Intel Monde de Jarvis l'affiche automatiquement via iframe. Les deux serveurs peuvent tourner simultanément.

> World Monitor fonctionne sans aucune variable d'environnement pour un usage de base. Des clés API optionnelles (Groq, OpenRouter…) permettent d'activer les fonctionnalités IA avancées, voir le `.env.example` du repo.

---

## Moteur proactif

Le moteur proactif tourne en arrière-plan et pousse des notifications au client connecté via WebSocket. Collectors intégrés :

- **Météo** : briefing matinal + alertes météo sévères
- **Actualités** : digest RSS sur des topics configurés

Ajoute un collector dans `proactive/collectors/` pour l'étendre.

---

## Développement

```bash
# Lancer les tests
uv run pytest

# Lint + format
uv run ruff check .
uv run ruff format .

# Test LLM manuel
uv run python scripts/test_llm.py --stream
uv run python scripts/test_llm.py --provider mistral
```

---

## Stack technique

- **Python 3.11** : async / FastAPI / uvicorn
- **Anthropic Claude** (LLM principal) + Mistral / Gemini / Ollama en fallback
- **LiveKit Agents** : pipeline vocal temps réel
- **Deepgram** : STT cloud / **faster-whisper** : STT local
- **Piper** : TTS local / **ElevenLabs** : TTS cloud
- **YOLOv8** (ultralytics) : détection d'objets pour l'outil vision
- **pydantic-settings** : configuration typée
- **loguru** : logging structuré
- **uv** : gestion des dépendances

---

## Licence

MIT
