# BACKLOG — Refonte architecturale jarvis-OS

Réceptacle des problèmes hors-périmètre identifiés pendant la refonte (CDC `CDC_refonte_architecture.md` §0 règle 1 et règle 5). On note, on ne corrige PAS dans la phase courante.

Format d'entrée : `- [PHASE X] <description> — <fichier/zone> — <pourquoi pas maintenant>`.

## 🚨 PRIORITAIRE — au-dessus de F.7 (sécurité)

- **`Settings.__repr__` expose les secrets en clair — vulnérabilité, pas de la propreté.** Tous les champs API/token (anthropic_api_key, openai_api_key, mistral_api_key, deepgram_api_key, elevenlabs_api_key, notion_token, aisstream_key, mapbox_token, maptiler_key, spotify_client_secret, deezer_app_secret, api_token, …) sont déclarés `str` dans `src/jarvis/kernel/settings.py`. Toute `AttributeError` / `print(settings)` / log d'une stack trace contenant l'instance `Settings()` les imprime — dont en prod. Constaté F.7.5 le 2026-06-11 quand pytest a affiché le `repr` complet du singleton sur un test cassé : 9 clés réelles imprimées dans la trace, rotation forcée. **Fix obligatoire avant la prochaine release** : typer ces champs en `pydantic.SecretStr` — `repr` masqué (`SecretStr('**********')`), accès explicite via `.get_secret_value()`. Migration call-sites : pour chaque champ secret, tout endroit qui lit `settings.X` doit devenir `settings.X.get_secret_value()` (sauf si on utilise le masqué délibérément). Audit `grep -rn "settings\\.\\(anthropic_api_key\\|openai_api_key\\|…\\)" src/` pour la liste exhaustive. Cible : nouvelle phase G.0 « sécurité Settings », bloquante avant F-merge final si on considère que B9 doit prouver l'app sûre sur clone neuf, pas seulement qu'elle boote.

## Phase A

_(en cours)_

## Phase B

_(à venir)_

## Phase C

- **Bug PRÉ-EXISTANT dans `src/jarvis/app.py` lifespan shutdown** : `await telegram.stop()` (l.611) est appelé même quand l'updater Telegram n'a jamais démarré (cas typique : TELEGRAM_BOT_TOKEN défini mais polling non lancé en TestClient). Lève `RuntimeError("This Updater is not running!")`. À résoudre en C.1 (refactor du lifespan vers bootstrap.build()) : vérifier `_app.updater.running` avant de stop(), ou capturer proprement l'exception. Découvert par B7b qui est le 1er test à fermer proprement le lifespan via TestClient.

## Phase D

_(à venir)_

## Phase E

_(à venir)_

## Phase F

- **Fermer conformité Protocols stricte — variance Tool/Skill résiduelle (CDC §F.1.3bis, suite)** — 2 couples restants, PURE variance cosmétique (les 2 divergences sémantiques de `MemoryStore` ont été corrigées AVANT le merge F — cf. test de conformance qui inclut MemoryStore) :
  - `kernel.contracts.ToolRegistry` ↔ `capabilities.tools.registry.ToolRegistry` : variance `kernel.contracts.Tool` (Protocol) vs `capabilities.tools.base.Tool` (ABC). Structurellement IDENTIQUES (mêmes `name/description/input_schema`, mêmes `to_claude_schema/execute`). L'impl utilise le type local, le Protocol pointe sur lui-même → mismatch nominal mypy.
  - `kernel.contracts.SkillRegistry` ↔ `capabilities.skills.registry.SkillRegistry` : même motif (`Skill` Protocol vs `SkillBase` ABC).
  Test de conformité actuel scopé sur **12 couples passants** : LLM × 5 + Memory × 6 (MemoryStore inclus) + UsageTracker × 1. À reprendre en Phase G en alignant les annotations `*tools: Tool` → `kernel.contracts.Tool` côté impl — l'ABC l'implémente déjà structurellement, le changement est uniquement annotatif.
- **Fermer RÈGLE 2 strict — 4 résidus capabilities/engine et engine/capabilities annotés `ignore_imports`** dans `pyproject.toml::tool.importlinter` :
  - `capabilities.tools.subagent → engine.agent` (Agent type pour SpawnSubagentTool — passer en Protocol kernel.contracts.Agent)
  - `capabilities.tools.subagent → engine.mission.backends.rpc` (ScriptRPCRunner instanciation — injecter via constructeur ou descendre l'infrastructure RPC en kernel/providers)
  - `capabilities.skills.lab → engine.mission.docker_executor` (DockerExecutor instanciation pour sandbox testing — soit injecter, soit descendre l'executor générique en providers/docker)
  - `engine.mission.worker_agent → capabilities.tools.fusion` (plugin Fusion 360 importé lazy quand un step nomme `fusion_360` — pattern plugin-friendly, à formaliser via tool_registry quand on aura un dispatcher dynamique)
  Le contrat import-linter passe via 4 lignes `ignore_imports`, chacune notée ici. Cibles à reprendre en Phase G "hygiene profonde".
- **Extraire les parsers Bluetooth de `interfaces/api/config/devices.py`** vers un service. Les fonctions `_parse_bt_macos` (~65 l.) et `_parse_bt_windows` (~55 l.) sont du pur data-transformer (sortie `system_profiler` / `Get-PnpDevice` → `list[dict]` UI-shaped), sans dépendance FastAPI. Elles vivent dans le router uniquement parce qu'elles sont nées là, mais tout autre call-site (initiative proactive "AirPods déconnectés", health-check, etc.) recopierait ou créerait un import remontant depuis interfaces/. Cible probable : `providers/hardware/bluetooth.py` (sibling de `providers/audio/`) ou `hardware/bluetooth_parsers.py` (sibling de `macropad_2k/`). À traiter en F dans la passe "hygiène / réorganisation", pas urgent.
- **GATE B9 (install à froid) BLOQUANT pour le merge final** — décalé de fin de B sur décision Barth, doit passer sur la lane CI complète avant le merge `refonte/architecture-couches` → `main`. Libellé verrouillé dans [gates_B8_B9.md](gates_B8_B9.md) : install Ubuntu propre + deps lourdes réelles + boot effectif via smoke_runtime --fake-llm.
- **ci.yml déclenche la lane lourde (dlib/portaudio/opencv) sur toutes branches** → split en F.1.2 : lane rapide partout, lane complète sur main + scheduled. Coût ~5-10 min par push branche jusque-là, accepté.
- **app.py doit logger au démarrage la SOURCE EFFECTIVE de `llm_provider`** (env var héritée du shell vs `.env` lu par pydantic) — diagnostic Phase C validation : un run a démarré en mode "local" parce qu'une env var `LLM_PROVIDER` héritée masquait le `.env` (pydantic priorise env > file). Le log actuel `Jarvis démarré` ne mentionne que la valeur résolue, pas sa provenance, donc l'incident n'a été identifiable qu'en relisant tout le trace. À résoudre en F (ou hors-refonte) : au boot, comparer `os.environ.get("LLM_PROVIDER")` et `dotenv_values(".env")["LLM_PROVIDER"]` et logger « llm_provider=X (source=env-var|.env|default) » avec un WARNING si l'un masque l'autre.

## Phase G (post-merge — dettes connues, ne BLOQUE PAS v0.2.0)

- **`smoke_runtime.py --process=voice` est SKIP en F-merge** — le boot du SECOND process (voix) n'est PAS couvert par B9. Le scénario `--process=voice` court-circuite proprement avec `SKIP : --process=voice non implémenté en F MVP ; le voice loop dépend de LiveKit en runtime — à reprendre en G`. Dette connue, **pas un oubli** : le process voix construit son propre Container via `bootstrap.build()` (CDC §C.1 tâche 8), mais l'entrée runtime est `livekit-agents.cli_app.run_app(...)` qui exige une session WebRTC réelle — incompatible avec une smoke gate automatique. À reprendre en G : extraire un sous-test du voice loop qui passe `bootstrap.build()` ET au moins un cycle STT-stub → Gateway → TTS-stub sans LiveKit côté serveur. Cible : un 4e hot path "D. Voice graph" dans smoke_runtime, déclenché par `--process=voice`.

## Post-mortems de méthode (à intégrer dans le CDC v1.4)

- **GATE C8 cochée ✅ sur un artefact fantôme** (constat F-merge GO #2) — la grille de gates C8 invoquait `uv run python scripts/validation/smoke_runtime.py --fake-llm` et a été reportée verte en clôture de Phase C, mais le fichier `smoke_runtime.py` n'a jamais été écrit en C (idem `tests/fakes/llm.py::FakeLLMProvider`). Les 5 autres étapes manuelles de validation C passaient réellement, donc Phase C est solide ; mais l'artefact-preuve de cette gate spécifique était creux pendant les Phases C/D/E. Attrapé par B9 en début F-merge, à l'instant où il a fallu réellement déclencher le smoke en CI à froid. **Règle à graver dans CDC v1.4** : une gate ne se coche pas avant que l'artefact qu'elle invoque existe physiquement dans le repo ET ait été exécuté avec exit code 0 au moins une fois — la sortie console doit être visible dans la trace de validation, pas inférée. Et le mot « ✅ » dans un rapport humain n'engage rien si la commande qu'il décrit n'a pas tourné.

- **GATE B4a cochée ✅ alors qu'un namespace entier passait sous le radar — `config/` racine** (constat F.7, attrapé par B9 retrigger #1) — B4a était libellée « zéro import ancien namespace » et a été cochée verte en fin de Phase B. Les 54 imports `from config.X` (dont le module `app.py` lui-même) ont SURVÉCU à B4a, et à tous les gates suivants (B, C, D, E, F.1). Cause : **deux périmètres de garde qui se chevauchent pile sur le shim racine** :
  - `scripts/migration/audit_imports.py` (gardien B4a → C5) ne scanne QUE les imports lazy à l'intérieur de `FunctionDef` (cf. son docstring l.21-25). Les ~54 imports module-level `from config.X` sont hors-périmètre par construction.
  - `pyproject.toml::tool.importlinter` (gardien F.1.1) avait `root_package = "jarvis"` (singulier). Le shim racine `config/` n'étant dans aucune `source_modules` ni `forbidden_modules`, aucun contrat ne pouvait l'attraper — y compris la violation RÈGLE 1 réelle (`kernel/connectivity.py:3 → config.settings`) et un cycle RÈGLE 2 transitif (`capabilities.tools.subagent → config.backends → engine.mission.backends`).

  Détecté par B9 cold-install (1er artefact qui boote l'app sur un clone neuf où le wheel n'embarque que `src/jarvis/`) : `ModuleNotFoundError: No module named 'config'` sur `app.py:19`. **Règle à graver dans CDC v1.4** : tout audit "zéro import ancien namespace" doit (i) lister explicitement les namespaces audités dans sa documentation, (ii) couvrir AUSSI les imports module-level (pas seulement lazy), et (iii) être doublé par un contrat structural (import-linter) qui voit *tous* les top-level packages du repo, pas uniquement le package d'installation. Quand deux gardiens existent, le test de leur ensemble est qu'aucun fichier du repo ne passe à travers les deux — pas qu'aucun ne soit interdit par les deux. Closure en F.7 : 4e contrat `RÈGLE 4`, `root_packages = ["jarvis", "config"]`, loaders descendus dans `jarvis.kernel.{approvals,backends,settings}` + factory `jarvis.engine.mission.backend_factory`, shim racine `config/{__init__,approvals,backends,settings}.py` supprimé (les JSON/YAML restent racine, décision Q1).

## Post-refonte (hors §9 « Hors périmètre »)

- Retrait des shims racine `main.py` / `voice_agent.py` — conservés une version pour les appelants externes (CDC §9).
- Réécriture front (ES modules `capabilities.js` / `macropad_2k.js`) — CDC ultérieur.
- mypy strict généralisé sur 46k lignes — chantier séparé, seul kernel + conformité Protocols couverts par F.1.3bis.
- Git LFS / réécriture historique pour gros binaires.
