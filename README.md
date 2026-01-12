<div align="center">

# Jarvis OS

**Assistant personnel intelligent multi-devices**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)
[![Node.js](https://img.shields.io/badge/node-%3E%3D22.13.1-brightgreen.svg)](https://nodejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5-blue.svg)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)

<a href="https://discord.gg/STEdPHu6Sx">
  <img src="src/images/gg.png" alt="Rejoindre le Discord officiel">
</a>

</div>

---

Jarvis est un assistant personnel intelligent conçu pour fonctionner sur plusieurs devices, des lunettes connectées aux ordinateurs, en passant par d'autres interfaces. L'objectif est de créer une plateforme d'assistant capable de comprendre la voix, la vision et le contexte, puis d'agir via des outils et des skills modulaires, tout en proposant une interface riche avec des widgets sur écran.

---

## Table des matières

- [Jarvis OS](#jarvis-os)
  - [Table des matières](#table-des-matières)
  - [Vision](#vision)
  - [Architecture](#architecture)
    - [1. Noyau intelligent (server/orchestrator)](#1-noyau-intelligent-serverorchestrator)
    - [2. Architecture multi-clients](#2-architecture-multi-clients)
    - [3. Plateforme ouverte](#3-plateforme-ouverte)
  - [Technologies](#technologies)
    - [Stack principale](#stack-principale)
  - [Installation](#installation)
    - [Prérequis](#prérequis)
    - [Setup](#setup)
    - [Configuration](#configuration)
    - [Démarrage](#démarrage)
  - [Skills](#skills)
    - [Skills disponibles](#skills-disponibles)
    - [Créer un skill](#créer-un-skill)
  - [Widgets](#widgets)
    - [Exemple d'utilisation](#exemple-dutilisation)
  - [Structure du projet](#structure-du-projet)
  - [Développement](#développement)
    - [Scripts disponibles](#scripts-disponibles)
    - [Architecture technique](#architecture-technique)
  - [Roadmap](#roadmap)
  - [Communauté](#communauté)
  - [Contribution](#contribution)
  - [Créateur](#créateur)
  - [Licence](#licence)
  - [Remerciements](#remerciements)

## Vision

> **Jarvis vise à devenir un véritable assistant personnel programmable, orienté produit et non simple démo technique.**

Le projet a une ambition de commercialisation tout en conservant une forte dimension communautaire et open-source.

**L'idée centrale** : construire une plateforme où les développeurs peuvent créer des "apps" (skills) pour étendre les capacités de Jarvis, avec un système de widgets déclaratifs pour afficher des interfaces dynamiques. À terme, Jarvis devrait être l'assistant personnel que vous pouvez personnaliser et programmer selon vos besoins.

## Architecture

Le projet repose sur **trois piliers fondamentaux** qui forment l'ossature de Jarvis :

### 1. Noyau intelligent (server/orchestrator)

**Le cerveau de Jarvis**

Le serveur central gère la voix (STT/TTS), la vision et la logique IA. Il orchestre les actions via des tools et des skills, conçu pour être rapide, extensible et commercialisable.

| Fonctionnalité | Description |
| -------------- | ----------- |
| **Traitement du langage naturel** | Classification d'intentions, extraction d'entités, gestion du contexte conversationnel |
| **Gestion de la voix** | Reconnaissance vocale (STT) et synthèse vocale (TTS) avec support de multiples providers |
| **Orchestration** | Routage des requêtes vers les skills appropriés, gestion des sessions multi-clients |
| **LLM** | Support pour modèles locaux et cloud (Groq, etc.) |

### 2. Architecture multi-clients

**Une session partagée, plusieurs interfaces**

Les différents devices se connectent au même serveur et partagent la même session :

| Device | Rôle |
| ------ | ---- |
| **Lunettes connectées** | Interface vocale et visuelle légère |
| **Ordinateur** | Cockpit avec interface graphique complète et widgets |
| **Autres devices** | Architecture extensible pour de nouveaux types d'interfaces |

> La communication se fait via **Socket.io** pour le temps réel et **HTTP** pour les API REST.

### 3. Plateforme ouverte

**Extensible par la communauté**

Système d'applications (skills) permettant aux développeurs de créer des extensions :

- **Skills modulaires** : Chaque skill est indépendant et peut être développé en Python ou TypeScript
- **Widgets déclaratifs** : Système de widgets basé sur Aurora pour afficher des interfaces dynamiques
- **Bridges** : SDK pour Node.js et Python facilitant le développement de nouveaux skills
- **Tools** : Système d'outils réutilisables pour les skills

## Technologies

### Stack principale

| Catégorie | Technologies |
| --------- | ----------- |
| **Backend** | ![Node.js](https://img.shields.io/badge/Node.js-22+-green) ![TypeScript](https://img.shields.io/badge/TypeScript-5.5-blue) |
| **Frontend** | ![React](https://img.shields.io/badge/React-18.3-61dafb) ![Vite](https://img.shields.io/badge/Vite-4.5-646cff) |
| **Python** | Serveur TCP pour STT/TTS/ASR, skills Python |
| **Communication** | ![Socket.io](https://img.shields.io/badge/Socket.io-4.7-010101) ![Fastify](https://img.shields.io/badge/Fastify-4.26-000000) |
| **NLP** | node-nlp, spaCy |
| **LLM** | Support local (node-llama-cpp) et cloud (Groq) |
| **Widgets** | Aurora component library |

## Installation

### Prérequis

Avant de commencer, assurez-vous d'avoir installé :

- **Node.js** >= 22.13.1
- **npm** >= 10.9.2
- **Python** 3.x avec Pipenv
- **FFmpeg** (pour le traitement audio)

### Setup

```bash
# Cloner le repository
git clone https://github.com/votre-username/jarvis-OS.git
cd jarvis-OS

# Installer les dépendances
npm install

# Le postinstall configurera automatiquement l'environnement Python
# Si besoin, configurer manuellement :
npm run setup:python-bridge
npm run setup:tcp-server

# Entraîner les modèles NLP
npm run train

# Générer les endpoints des skills
npm run generate:skills-endpoints
```

### Configuration

Créer un fichier `.env` à la racine avec vos configurations (voir `.env.example` si disponible).

### Démarrage

```bash
# Mode développement (serveur + app)
npm run dev:server
npm run dev:app

# Mode production
npm run build
npm start
```

## Skills

Les skills sont des modules indépendants qui étendent les capacités de Jarvis.

### Skills disponibles

| Skill | Description |
| ----- | ----------- |
| **Todo List** | Gestion de listes de tâches avec widgets interactifs |
| **Timer** | Minuteries et rappels |
| **News** | Actualités (GitHub Trends, Product Hunt, etc.) |
| **Weather** | Météo |
| **Translator** | Traduction de texte et vidéos |
| **Games** | Jeux interactifs (Akinator, etc.) |
| **Utilities** | Outils divers (date/time, speed test, etc.) |

### Créer un skill

Les skills peuvent être développés en Python ou TypeScript. Consultez la documentation des bridges pour plus d'informations :

- [Bridge Python](bridges/python/README.md)
- [Bridge Node.js](bridges/nodejs/README.md)

## Widgets

Le système de widgets permet aux skills d'afficher des interfaces riches et interactives. Les widgets sont déclaratifs et basés sur les composants Aurora.

### Exemple d'utilisation

**Dans un skill Python :**

```python
from leon import Leon
from leon.widgets import Widget, WidgetOptions

class MyWidget(Widget):
    def render(self):
        return WidgetComponent(...)
```

## Structure du projet

```text
jarvis-OS/
├── server/          # Serveur principal (TypeScript)
├── app/             # Application web (React)
├── tcp_server/      # Serveur TCP Python (STT/TTS/ASR)
├── bridges/          # SDK pour développer des skills
│   ├── nodejs/      # Bridge Node.js/TypeScript
│   └── python/      # Bridge Python
├── skills/          # Skills disponibles
├── core/            # Configuration et données
└── hotword/         # Détection de mot-clé
```

## Développement

### Scripts disponibles

| Commande | Description |
| -------- | ----------- |
| `npm run dev:server` | Démarrer le serveur en mode développement |
| `npm run dev:app` | Démarrer l'application web en mode développement |
| `npm run train` | Entraîner les modèles NLP |
| `npm run test` | Lancer les tests |
| `npm run lint` | Vérifier le code avec ESLint |

### Architecture technique

**Serveur principal** (`server/`)

- Communication avec les clients (Socket.io)
- Traitement NLP et classification d'intentions
- Orchestration des skills
- Gestion de la voix (via le serveur TCP Python)

**Serveur TCP Python** (`tcp_server/`)

- Reconnaissance vocale (ASR)
- Synthèse vocale (TTS)
- Extraction d'entités avec spaCy

## Roadmap

| Fonctionnalité | Statut |
| -------------- | ------ |
| Support complet de la vision (analyse d'images) | À venir |
| Amélioration du système de widgets | À venir |
| Marketplace de skills | À venir |
| Support de plus de devices (smartphones, etc.) | À venir |
| Amélioration de la gestion multi-langues | À venir |
| Optimisations de performance | À venir |

## Communauté

Rejoignez notre communauté Discord pour discuter, poser des questions et partager vos créations :

<div align="center">

<a href="https://discord.gg/STEdPHu6Sx">
  <img src="src/images/gg.png" alt="Rejoindre le Discord officiel">
</a>

</div>

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

- Ouvrir une [issue](https://github.com/votre-username/jarvis-OS/issues) pour signaler un bug
- Proposer une nouvelle fonctionnalité
- Soumettre une [pull request](https://github.com/votre-username/jarvis-OS/pulls)
- Rejoindre notre [Discord](https://discord.gg/STEdPHu6Sx) pour discuter du projet

---

## Créateur

Jarvis est créé et maintenu par **Barth**.

<div align="center" style="width: 100%;">

<a href="https://www.youtube.com/@BarthH95" style="text-decoration: none; display: inline-block; width: 100%;">
  <table style="width: 100%; margin: 0 auto;">
    <tr>
      <td style="width: 200px;">
        <img src="src/images/barth_yt_pdp.jpg" alt="Barth" width="200" height="200" style="border-radius: 50%; display: block;">
      </td>
      <td style="padding-left: 30px; vertical-align: middle;">
        <div style="font-size: 48px; font-weight: bold; margin: 0;">@barthH95</div>
        <div style="font-size: 24px; color: #666; margin-top: 10px;">Youtube</div>
      </td>
    </tr>
  </table>
</a>

</div>

---

## Licence

Ce projet est dérivé du projet open-source [Leon](https://github.com/leon-ai/leon).

Voir [LICENSE.md](LICENSE.md) pour plus d'informations.

---

## Remerciements

Jarvis OS est basé sur le travail de [Leon](https://github.com/leon-ai/leon) par Louis Grenard, avec des modifications significatives pour les objectifs du projet Jarvis.

---

<div align="center">

**Fait avec passion pour créer l'assistant personnel de demain**

</div>
