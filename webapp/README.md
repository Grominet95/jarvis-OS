# Jarvis - Assistant Vocal Personnel

Application Electron avec interface graphique pour un assistant vocal basé sur Pipecat, utilisant OpenAI, Deepgram et Cartesia.

## Prérequis

### Toutes les plateformes

- **Python 3.10 ou supérieur**
- **Node.js 18 ou supérieur** (avec npm)
- **uv** (gestionnaire de paquets Python) - [Installation](https://docs.astral.sh/uv/getting-started/installation)

### Clés API requises

Vous aurez besoin de clés API pour les services suivants :

- **OpenAI** (obligatoire) - [Obtenir une clé](https://platform.openai.com/api-keys)
- **Deepgram** (optionnel, pour STT) - [Obtenir une clé](https://console.deepgram.com/signup)
- **Cartesia** (optionnel, pour TTS) - [Obtenir une clé](https://play.cartesia.ai/sign-up)

> **Note** : L'application peut démarrer sans Deepgram et Cartesia, mais OpenAI est obligatoire pour le fonctionnement du bot.

## Installation

### Installation automatique (recommandé)

Les scripts de démarrage gèrent automatiquement l'installation et la configuration. Il suffit de :

1. **Cloner ou télécharger le projet** :
   ```powershell
   # Windows
   cd C:\Users\VotreNom\Documents
   git clone https://github.com/Grominet95/jarvis-OS.git
   cd webapp
   ```
   ```bash
   # Linux/macOS
   cd ~/Documents
   git clone <url-du-repo>
   cd webapp
   ```

2. **Lancer le script de démarrage** :
   ```powershell
   # Windows
   .\start.bat
   ```
   ```bash
   # Linux/macOS
   ./start.sh
   ```

Le script vérifiera automatiquement :
- La présence de Python 3.10+
- La présence de Node.js et npm
- La présence de uv
- L'installation des dépendances Python (`uv sync`)
- L'installation des dépendances Node.js (`npm install`)

Si quelque chose manque, le script vous indiquera comment l'installer.

### Installation manuelle (optionnel)

Si vous préférez installer manuellement :

#### Windows

1. **Installer les prérequis** :
   ```powershell
   # Vérifier Python
   python --version
   
   # Vérifier Node.js
   node --version
   npm --version
   
   # Installer uv
   pip install uv
   # ou avec PowerShell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Configurer le projet** :
   ```powershell
   # Lancer le script de configuration
   .\setup.bat
   ```

3. **Lancer l'application** :
   ```powershell
   .\start.bat
   ```

#### Linux/macOS

1. **Installer les prérequis** :
   ```bash
   # Vérifier Python
   python3 --version
   
   # Vérifier Node.js
   node --version
   npm --version
   
   # Installer uv
   pip3 install uv
   # ou avec curl
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Configurer le projet** :
   ```bash
   # Rendre les scripts exécutables
   chmod +x start.sh setup.sh
   
   # Lancer le script de configuration
   ./setup.sh
   ```

3. **Lancer l'application** :
   ```bash
   ./start.sh
   ```

## Configuration

### Première utilisation de l'application

Lors du premier lancement, l'application affichera un assistant de configuration (onboarding) qui vous permettra de :

1. Entrer votre prénom
2. Entrer votre email
3. Entrer votre date de naissance
4. Entrer votre pays et ville

### Configuration des clés API

Les clés API peuvent être configurées de deux manières :

#### Méthode 1 : Via l'interface graphique (recommandé)

1. Lancez l'application
2. Allez dans **Paramètres** (icône en haut à droite)
3. Cliquez sur **Général** dans le menu latéral
4. Remplissez les champs dans la section **Clés API** :
   - **OpenAI API Key** (obligatoire)
   - **Deepgram API Key** (optionnel)
   - **Cartesia API Key** (optionnel)
5. Cliquez sur **Enregistrer les clés API**

#### Méthode 2 : Via le fichier .env (déprécié)

> **Note** : Cette méthode est dépréciée. L'application crée automatiquement le fichier `.env` à partir de la base de données SQLite. Modifier directement le `.env` ne persistera pas.

Si vous préférez utiliser le fichier `.env` :

1. Créez un fichier `.env` à la racine du projet
2. Ajoutez vos clés API :
   ```env
   OPENAI_API_KEY=votre_clé_openai
   DEEPGRAM_API_KEY=votre_clé_deepgram
   CARTESIA_API_KEY=votre_clé_cartesia
   ```

## Stockage des données

Toutes les données sont stockées dans une base de données SQLite :

- **Windows** : `%APPDATA%\jarvis-electron\jarvis.db`
- **Linux** : `~/.config/jarvis-electron/jarvis.db`
- **macOS** : `~/Library/Application Support/jarvis-electron/jarvis.db`

Les données stockées incluent :
- Profil utilisateur (prénom, date de naissance, pays, ville)
- Clés API (chiffrées dans la base de données)
- Paramètres audio (microphone, haut-parleurs)
- Autres paramètres de l'application

## Utilisation

### Démarrage

1. Lancez l'application avec `npm start` ou le script de démarrage approprié
2. Attendez que le bot démarre (environ 20 secondes au premier lancement)
3. L'interface affichera "Backend ready" une fois le bot prêt

### Connexion

1. Cliquez sur le bouton **Connexion** dans l'interface
2. Autorisez l'accès au microphone si demandé
3. Le statut passera à "Connecté" une fois la connexion WebRTC établie

### Conversation

- Parlez normalement dans le microphone
- L'assistant répondra vocalement
- Les transcriptions apparaîtront dans le chat "Système"
- Utilisez le bouton microphone pour couper/rétablir le son

### Paramètres

Accédez aux paramètres via l'icône en bas à droite :

- **Audio** : Sélection des périphériques audio (microphone, haut-parleurs)
- **Général** : Profil utilisateur et clés API
- **Avancé** : Paramètres avancés (à venir)

## Dépannage

### Le bot ne démarre pas

1. Vérifiez que le port 7860 n'est pas utilisé :
   ```bash
   # Linux/macOS
   lsof -i :7860
   
   # Windows
   netstat -ano | findstr :7860
   ```

2. Vérifiez que les clés API sont correctement configurées dans les paramètres

3. Vérifiez les logs dans la console où vous avez lancé l'application

### Erreur "better-sqlite3" sur Windows

Si vous obtenez une erreur de version Node.js avec `better-sqlite3` :

```powershell
npx electron-rebuild
```

Ou réinstallez les dépendances :

```powershell
npm install
```

### Le microphone ne fonctionne pas

1. Vérifiez les permissions du microphone dans les paramètres système
2. Sélectionnez le bon périphérique dans Paramètres > Audio
3. Vérifiez que le microphone n'est pas utilisé par une autre application

### Pas de son

1. Vérifiez le volume système
2. Sélectionnez le bon périphérique de sortie dans Paramètres > Audio
3. Vérifiez que la clé API Cartesia est configurée (pour la synthèse vocale)

### L'assistant ne répond pas

1. Vérifiez que la clé API OpenAI est configurée et valide
2. Vérifiez votre connexion internet
3. Consultez les logs dans la console pour voir les erreurs éventuelles

## Structure du projet

```
pipecat-quickstart/
├── bot.py                 # Script principal du bot Pipecat
├── start_bot.py          # Script de démarrage du bot
├── electron/             # Code Electron (application desktop)
│   ├── main.js          # Processus principal Electron
│   ├── preload.js       # Script de préchargement
│   └── database.js      # Gestion de la base de données SQLite
├── statics/              # Interface utilisateur
│   └── src/
│       ├── index.html   # Page principale
│       ├── js/          # Scripts JavaScript
│       └── css/         # Styles CSS
├── package.json         # Dépendances Node.js
├── pyproject.toml       # Dépendances Python
└── README.md            # Ce fichier
```

## Développement

### Mode développement

```bash
npm run dev
```

### Recompiler les modules natifs

Si vous modifiez des modules natifs (comme `better-sqlite3`) :

```bash
npx electron-rebuild
```

### Logs

Les logs du bot Python sont affichés dans la console où vous avez lancé l'application.

Les logs Electron sont visibles dans la console de développement (F12 dans l'application).

## Notes importantes

- **Premier lancement** : Le premier démarrage peut prendre 20-30 secondes car Pipecat télécharge les modèles nécessaires
- **Clés API** : Les clés API sont stockées localement dans SQLite. Ne partagez jamais votre fichier `jarvis.db`
- **Port 7860** : Le bot utilise le port 7860 par défaut. Assurez-vous qu'il est disponible
- **Windows** : Sur Windows, certains caractères Unicode peuvent ne pas s'afficher correctement dans la console. C'est normal

## Support

Pour toute question ou problème :

1. Vérifiez les logs dans la console
2. Consultez la section Dépannage ci-dessus
3. Vérifiez que tous les prérequis sont installés correctement

## Licence

MIT
