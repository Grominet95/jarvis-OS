# BACKLOG — Refonte architecturale jarvis-OS

Réceptacle des problèmes hors-périmètre identifiés pendant la refonte (CDC `CDC_refonte_architecture.md` §0 règle 1 et règle 5). On note, on ne corrige PAS dans la phase courante.

Format d'entrée : `- [PHASE X] <description> — <fichier/zone> — <pourquoi pas maintenant>`.

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

- **Extraire les parsers Bluetooth de `interfaces/api/config/devices.py`** vers un service. Les fonctions `_parse_bt_macos` (~65 l.) et `_parse_bt_windows` (~55 l.) sont du pur data-transformer (sortie `system_profiler` / `Get-PnpDevice` → `list[dict]` UI-shaped), sans dépendance FastAPI. Elles vivent dans le router uniquement parce qu'elles sont nées là, mais tout autre call-site (initiative proactive "AirPods déconnectés", health-check, etc.) recopierait ou créerait un import remontant depuis interfaces/. Cible probable : `providers/hardware/bluetooth.py` (sibling de `providers/audio/`) ou `hardware/bluetooth_parsers.py` (sibling de `macropad_2k/`). À traiter en F dans la passe "hygiène / réorganisation", pas urgent.
- **GATE B9 (install à froid) BLOQUANT pour le merge final** — décalé de fin de B sur décision Barth, doit passer sur la lane CI complète avant le merge `refonte/architecture-couches` → `main`. Libellé verrouillé dans [gates_B8_B9.md](gates_B8_B9.md) : install Ubuntu propre + deps lourdes réelles + boot effectif via smoke_runtime --fake-llm.
- **ci.yml déclenche la lane lourde (dlib/portaudio/opencv) sur toutes branches** → split en F.1.2 : lane rapide partout, lane complète sur main + scheduled. Coût ~5-10 min par push branche jusque-là, accepté.
- **app.py doit logger au démarrage la SOURCE EFFECTIVE de `llm_provider`** (env var héritée du shell vs `.env` lu par pydantic) — diagnostic Phase C validation : un run a démarré en mode "local" parce qu'une env var `LLM_PROVIDER` héritée masquait le `.env` (pydantic priorise env > file). Le log actuel `Jarvis démarré` ne mentionne que la valeur résolue, pas sa provenance, donc l'incident n'a été identifiable qu'en relisant tout le trace. À résoudre en F (ou hors-refonte) : au boot, comparer `os.environ.get("LLM_PROVIDER")` et `dotenv_values(".env")["LLM_PROVIDER"]` et logger « llm_provider=X (source=env-var|.env|default) » avec un WARNING si l'un masque l'autre.

## Post-refonte (hors §9 « Hors périmètre »)

- Retrait des shims racine `main.py` / `voice_agent.py` — conservés une version pour les appelants externes (CDC §9).
- Réécriture front (ES modules `capabilities.js` / `macropad_2k.js`) — CDC ultérieur.
- mypy strict généralisé sur 46k lignes — chantier séparé, seul kernel + conformité Protocols couverts par F.1.3bis.
- Git LFS / réécriture historique pour gros binaires.
