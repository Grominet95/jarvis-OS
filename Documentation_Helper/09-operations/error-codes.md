# Error codes reference

Auto-generated from `scripts/error_audit/error-codes.yaml`. Do not edit manually.

Terminal format: `[JRV-XXX-NNN] ERROR|WARN|IMPOSSIBLE: message`

| Code | Severity | Title | Resolution | Docs |
|------|----------|-------|------------|------|
| `JRV-AGT-001` | error | Échec boucle agent LLM | Relance la conversation ; consulte api.log pour le détail. | `05-engine/agent.md` |
| `JRV-API-001` | error | Erreur route HTTP | Note le code JRV et l'endpoint ; consulte api.log. | `06-interfaces/api/` |
| `JRV-API-002` | error | Authentification API refusée | Configure API_AUTH_TOKEN dans .env ou désactive API_AUTH_ENABLED pour usage local. | `05-engine/auth.md` |
| `JRV-API-003` | error | Ressource introuvable (404) | Vérifie l'identifiant (session, projet, fichier) et réessaie. | `06-interfaces/api/` |
| `JRV-API-004` | error | Requête invalide (400/422) | Corrige les champs envoyés selon la doc de l'endpoint. | `06-interfaces/api/` |
| `JRV-API-005` | error | Service indisponible (503) | Relance Jarvis ; vérifie que le sous-système concerné est câblé dans bootstrap. | `09-operations/troubleshooting.md` |
| `JRV-API-006` | error | Échec wizard setup | Corrige les champs du formulaire setup et relance .\\jarvis.ps1 setup. | `01-entry-points/setup-flow.md` |
| `JRV-AUD-001` | warning | Échec STT/TTS | Vérifie DEEPGRAM/ELEVENLABS dans .env et voice.log. | `06-interfaces/voice-livekit.md` |
| `JRV-BG-001` | warning | Échec tâche background | Consulte api.log ; relance Jarvis si récurrent. | `05-engine/background/overview.md` |
| `JRV-BGT-001` | error | BudgetGuard dépassé | Augmente le budget dans .env ou attends la reset ; voir budget.md. | `05-engine/budget.md` |
| `JRV-BTS-001` | error | Échec bootstrap container | Vérifie .env, bundle et logs api.log ; relance après correction. | `00-meta/bootstrap-wiring.md` |
| `JRV-ENG-000` | error | Erreur générique engine | Relance .\\jarvis.ps1 run ; si persistant, note le code JRV et les logs. | `09-operations/troubleshooting.md` |
| `JRV-ENG-999` | error | État impossible atteint | Signale un bug avec le code JRV et les étapes de reproduction. | `09-operations/troubleshooting.md` |
| `JRV-GWY-001` | error | Échec gateway chat | Vérifie les logs api.log et la config LLM. | `05-engine/gateway.md` |
| `JRV-GWY-002` | warning | Cross-session recall dégradé | Non bloquant ; vérifie memory si récurrent. | `03-providers/memory/retrieval.md` |
| `JRV-HW-001` | warning | Périphérique hardware dégradé (générique) | Vérifie USB/drivers ; non bloquant pour le chat. | `hardware/` |
| `JRV-HW-002` | warning | Échec flash macropad | Vérifie le câble USB, arduino-cli et les logs flasher. | `hardware/macropad_2k/flasher.md` |
| `JRV-KRN-001` | error | Chemin OneDrive ou sync cloud | Déplace le clone hors dossier cloud ou désactive la sync sur jarvis-OS. | `playbooks/install-windows.md`, `02-kernel/paths-and-layout.md` |
| `JRV-KRN-002` | error | Bundle offline absent | Relance .\\jarvis.ps1 setup pour télécharger le bundle. | `playbooks/install-windows.md`, `02-kernel/bundle-offline.md` |
| `JRV-KRN-003` | error | Version Python trop ancienne | Installe Python 3.11+ puis relance setup. | `01-entry-points/setup-flow.md` |
| `JRV-KRN-004` | error | Dépendances manquantes ou cassées | Dans le dossier projet, lance uv sync --extra vision ; supprime .venv si besoin. | `01-entry-points/setup-flow.md` |
| `JRV-KRN-005` | warning | Fichier .env absent | Copie .env.example vers .env et remplis les clés API minimales. | `07-config/env-reference.md`, `playbooks/api-keys.md` |
| `JRV-KRN-006` | warning | Configuration .env suspecte | Corrige .env : une clé par ligne, valeur brute sans commande PowerShell. | `07-config/env-reference.md` |
| `JRV-KRN-007` | warning | Clé LLM manquante ou placeholder | Remplis la variable API correspondante dans .env puis redémarre. | `playbooks/api-keys.md` |
| `JRV-KRN-008` | warning | Clé LLM refusée par le fournisseur | Régénère la clé sur le dashboard du provider et mets à jour .env. | `playbooks/api-keys.md` |
| `JRV-KRN-009` | warning | Quota LLM preflight (429) | Vérifie le solde ou change de provider temporairement. | `playbooks/api-keys.md`, `05-engine/budget.md` |
| `JRV-KRN-010` | error | Port API déjà utilisé | Ferme l'instance précédente ou change PORT dans .env. | `01-entry-points/run-flow.md` |
| `JRV-KRN-011` | error | Échec vérification preflight | Relance jarvis.ps1 ; consulte le message et les logs. | `09-operations/logs-and-doctor.md` |
| `JRV-KRN-012` | error | Garde OneDrive au runtime | Déplace jarvis-OS hors OneDrive ou exclue le dossier de la sync. | `02-kernel/paths-and-layout.md`, `playbooks/install-windows.md` |
| `JRV-LLM-001` | error | Quota API dépassé (429) | Attends, change de tier, ou bascule sur Ollama local. | `playbooks/api-keys.md`, `05-engine/budget.md` |
| `JRV-LLM-002` | error | Timeout provider LLM | Vérifie la connexion, la clé API et le backend configuré. | `05-engine/gateway.md`, `playbooks/api-keys.md` |
| `JRV-LLM-003` | error | Clé ou config LLM invalide | Corrige LLM_PROVIDER, API_BACKEND et les clés dans .env. | `playbooks/api-keys.md`, `07-config/env-reference.md` |
| `JRV-LLM-004` | warning | Ollama local indisponible | Lance ollama serve ou bascule sur un provider API. | `03-providers/llm/local.md` |
| `JRV-MEM-001` | warning | Échec ingest mémoire | Vérifie memory_data/ et les permissions disque. | `03-providers/memory/ingest.md` |
| `JRV-MEM-002` | warning | Échec consolidation mémoire | Consulte les logs ; relance si nécessaire. | `03-providers/memory/consolidation.md` |
| `JRV-MEM-003` | warning | Échec recherche FTS | Relance Jarvis pour rebuild FTS ; vérifie memory_data/sessions/. | `03-providers/memory/search.md` |
| `JRV-MEM-004` | warning | Échec store sessions | Vérifie memory_data/sessions/ et les permissions. | `03-providers/memory/sessions.md` |
| `JRV-MEM-005` | warning | Échec index vectoriel | Vérifie l'espace disque et relance le reindex depuis l'admin. | `03-providers/memory/index.md` |
| `JRV-MEM-006` | warning | Échec AutoDream | Vérifie ingest_deep_enabled et les logs nocturnes. | `03-providers/memory/auto_dream.md` |
| `JRV-MSG-001` | warning | Canal messaging dégradé (générique) | Vérifie les tokens bot dans .env. | `06-interfaces/channels/` |
| `JRV-MSG-002` | warning | Bot Telegram offline | Vérifie TELEGRAM_BOT_TOKEN et que le webhook/polling tourne. | `06-interfaces/channels/telegram.md` |
| `JRV-MSG-003` | warning | Bot Discord offline | Vérifie DISCORD_BOT_TOKEN et les intents activés. | `06-interfaces/channels/discord.md` |
| `JRV-MSN-001` | error | Échec mission worker | Consulte mission control et les logs projet. | `05-engine/mission/overview.md` |
| `JRV-MSN-002` | warning | Store projet corrompu | Vérifie le JSON projet ou recrée le projet. | `05-engine/mission/project_store.md` |
| `JRV-OPS-001` | warning | Widget analytics dégradé | Normal si service externe absent. | `analytics/` |
| `JRV-PRM-001` | error | Permission refusée | Vérifie les règles dans settings permissions ou approvals. | `02-kernel/permissions-approvals.md` |
| `JRV-PRO-001` | warning | Collecteur proactive dégradé (générique) | Normal si service externe indisponible ; vérifie credentials si récurrent. | `05-engine/proactive/overview.md` |
| `JRV-PRO-002` | warning | Échec store proactive | Vérifie les fichiers data proactive. | `05-engine/proactive/store.md` |
| `JRV-PRO-003` | warning | Collecteur email offline | Vérifie OAuth Gmail et les credentials IMAP si configuré. | `05-engine/proactive/collectors/email.md` |
| `JRV-PRO-004` | warning | Collecteur news offline | Vérifie les URLs RSS et la connectivité réseau. | `05-engine/proactive/collectors/news.md` |
| `JRV-SET-001` | error | Wizard setup inaccessible | Relance .\jarvis.ps1 setup et ouvre http://127.0.0.1:8765/setup | `playbooks/install-windows.md`, `01-entry-points/setup-flow.md` |
| `JRV-SKL-001` | error | Échec chargement skill (générique) | Vérifie skills_data/installed et les logs skill. | `04-capabilities/skills/lifecycle.md` |
| `JRV-SKL-002` | error | ABI skill incompatible | Réinstalle ou recompile le skill pour la version courante. | `04-capabilities/skills/abi.md` |
| `JRV-SKL-003` | error | Échec installation skill | Vérifie skills_data/installed, les droits disque et installer.py logs. | `04-capabilities/skills/installer.md` |
| `JRV-SKL-004` | warning | Échec sandbox skill lab | Consulte les logs lab ; vérifie le code du skill en sandbox. | `04-capabilities/skills/lab.md` |
| `JRV-SKL-005` | warning | Échec synthèse skill | Vérifie le LLM backend et les quotas ; réessaie avec un prompt plus court. | `04-capabilities/skills/synthesizer.md` |
| `JRV-TOL-001` | error | Échec exécution outil (générique) | Vérifie les credentials et la doc de l'outil concerné. | `04-capabilities/tools-overview.md` |
| `JRV-TOL-002` | error | Échec outil Spotify | Vérifie SPOTIFY_CLIENT_ID/SECRET dans .env et reconnecte via Réglages. | `04-capabilities/tools/spotify.md` |
| `JRV-TOL-003` | error | Échec outil Gmail | Vérifie OAuth Google et les scopes Gmail dans .env. | `04-capabilities/tools/gmail.md` |
| `JRV-TOL-004` | error | Échec outil navigateur | Vérifie playwright/chromium et la connectivité réseau. | `04-capabilities/tools/browser.md` |
| `JRV-TOL-005` | error | Échec outil Notion | Vérifie NOTION_TOKEN et les permissions de la base. | `04-capabilities/tools/notion.md` |
| `JRV-TOL-006` | error | Échec outil calendrier | Vérifie OAuth Google Calendar et les scopes. | `04-capabilities/tools/calendar.md` |
| `JRV-TOL-007` | error | Échec outil CLI | Vérifie tools.yaml, le binaire et les permissions sandbox. | `04-capabilities/tools/cli.md` |
| `JRV-TOL-008` | error | Échec outil filesystem | Vérifie le chemin, les permissions et les règles sandbox. | `04-capabilities/tools/filesystem.md` |
| `JRV-TOL-009` | error | Échec outil vision | Vérifie la caméra, opencv et vision.log. | `04-capabilities/tools/vision.md` |
| `JRV-TOL-010` | error | Échec outil Fusion 360 | Vérifie que Fusion tourne et que le bridge local écoute. | `04-capabilities/tools/fusion.md` |
| `JRV-TOL-011` | warning | Échec outil mémoire (tool) | Vérifie memory_data/ et les permissions disque. | `capabilities/tools/memory.md` |
| `JRV-TOL-012` | warning | Échec outil météo | Vérifie OPENWEATHER_API_KEY ou la connectivité réseau. | `04-capabilities/tools/weather.md` |
| `JRV-TOL-013` | error | Échec sous-agent | Consulte api.log pour la mission enfant et le tool parent. | `04-capabilities/tools/subagent.md` |
| `JRV-TOL-014` | warning | Échec contrôle carte | Vérifie que l'UI globe est ouverte et que l'API map répond. | `04-capabilities/tools/map_control.md` |
| `JRV-UNK-001` | error | Exception non gérée | Consulte les logs %TEMP%\\jarvis\\api.log et le traceback complet en mode debug. | `09-operations/logs-and-doctor.md` |
| `JRV-VIS-001` | warning | Échec daemon vision | Vérifie les deps vision et vision.log. | `03-providers/vision/daemon.md` |
| `JRV-VOI-001` | error | LiveKit indisponible (7880) | Relance .\\jarvis.ps1 run ; vérifie livekit.log. | `06-interfaces/voice-livekit.md` |
| `JRV-VOI-002` | error | Timeout publication piste audio | Vérifie permissions micro et voice.log. | `06-interfaces/voice-livekit.md` |
| `JRV-WS-001` | error | Erreur WebSocket chat | Reconnecte le client ; consulte api.log. | `06-interfaces/api/websocket.md` |

## Related docs

- [troubleshooting.md](troubleshooting.md)
- [logs-and-doctor.md](logs-and-doctor.md)
- [error-collector-guide.md](../00-meta/error-collector-guide.md)

