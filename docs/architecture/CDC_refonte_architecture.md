# CDC — Refonte architecturale jarvis-OS
## « Opération Squelette » — Migration vers une architecture en couches strictes

**Version :** 1.3 — 10 juin 2026
**Changelog 1.3 :** revue croisée round 3 (couche non-Python) — étiquetage [CI]/[LOCAL] de tous les gates + deux lanes CI (§0.5, F.1.2), audit des chemins étendu à la couche shell (`setup.sh`, `install.sh`, `Makefile`, `jarvis`) avec GATE B9 « install à froid », CLI découplé des shims racine via entry points module (incl. patterns `pkill` l.55), alias skills documenté comme ABI public avec exclusion nommée du GATE C9, PRAGMA `busy_timeout` joint au mode WAL.
**Changelog 1.2 :** revue croisée round 2 — process voix traité comme second composition root (C.1.8, GATE C10), imports dynamiques couverts par l'audit et les gates (`__import__` + `import_module`), alias de compatibilité pour les skills installés (découverte : les 8 skills installés importent `skills.base` — namespace racine), continuité des données sur disque (baseline A, GATE B8, migration de `vision/faces/`), marqueurs `integration` avancés en Phase A pour un gate par-commit rapide en B/C.
**Changelog 1.1 :** intégration des 6 amendements de la revue croisée Opus 4.8 — précondition de séquencement produit (§0.4), snapshot mécanique des routes (A/B/C/E), gate chemins B7, smoke runtime C8, gate ré-exports C9, type-check de conformité des Protocols (F).
**Auteur :** Barthélemy Houot
**Exécutant :** Claude Code, en mode stop-and-validate strict
**Référence amont :** `CDC_jarvis_evolution.md`

---

## 0. Protocole d'exécution (À LIRE EN PREMIER, Claude Code)

Ce document est découpé en **6 phases (A → F)**. Les règles suivantes sont **non négociables** :

1. **Une phase = un périmètre fermé.** Tu n'anticipes JAMAIS sur la phase suivante, même si une modification semble « évidente ». Si tu identifies un problème hors périmètre, tu le notes dans `docs/migration/BACKLOG.md` et tu continues.
2. **STOP obligatoire en fin de phase.** Tu termines chaque phase par : (a) l'exécution complète de la section « Auto-vérifications », (b) un rapport de fin de phase (format en §0.3), (c) un arrêt total en attente de validation humaine. Tu ne commences PAS la phase suivante sans un « GO PHASE X » explicite de Barth.
3. **Commits granulaires, messages en français.** Format : `[PHASE X] <verbe à l'infinitif> <objet>` (ex : `[PHASE A] Créer kernel/contracts.py avec les Protocols LLM et Memory`). Un commit = une unité logique. Jamais de commit fourre-tout.
4. **Tests verts en permanence.** Après CHAQUE commit : `uv run pytest -m "not integration" -q` (suite rapide, < 30 s — marqueurs posés dès la Phase A). La suite COMPLÈTE (`uv run pytest`) est exigée aux gates de fin de phase. Si un commit casse les tests, tu corriges avant de continuer — pas de « je réparerai plus tard ».
5. **Aucune réécriture opportuniste.** Tu déplaces et tu recâbles, tu ne réécris pas la logique métier. Si du code te semble améliorable, → `BACKLOG.md`.
6. **Compatibilité ascendante pendant la migration.** Les commandes `jarvis run`, `jarvis voice`, `jarvis eclosion`, `make start` doivent fonctionner à la fin de chaque phase.
7. **En cas de doute : STOP et question.** Une question coûte 2 minutes, un mauvais choix architectural coûte une semaine.
8. **Précondition de séquencement produit.** La refonte démarre depuis un commit où la feature produit en cours (Phase 6 — Capability Engine, cf. `CDC_jarvis_evolution.md`) est **stable, mergée et taggée `pre-reorg`**. On ne gèle JAMAIS en milieu de feature : du code à moitié intégré sous une migration de cette ampleur est ingérable. Si la feature en cours n'est pas stabilisable rapidement, la refonte attend.

### 0.1 Branche et stratégie Git

- Branche de travail : `refonte/architecture-couches`, créée depuis `main`.
- Une **tag Git** en fin de chaque phase validée : `migration-phase-A`, `migration-phase-B`, etc. → ce sont les points de rollback.
- Rollback d'une phase = `git reset --hard migration-phase-<précédente>`.
- Merge dans `main` uniquement après validation de la PHASE F complète.

### 0.2 Définition de « tests verts »

```bash
uv run pytest -x -q                  # 0 failure, 0 error
uv run ruff check .                  # 0 erreur
uv run python -c "import main"       # le serveur s'importe sans crash (jusqu'en phase B)
uv run python -c "import jarvis"     # à partir de la phase B
```

### 0.3 Format du rapport de fin de phase

```markdown
## RAPPORT PHASE X — <nom>
- Commits : <liste des hashes + messages>
- Fichiers créés / déplacés / supprimés : <compte + liste si < 20>
- Auto-vérifications : <chaque gate avec ✅/❌ et la sortie de commande>
- Écarts vs CDC : <aucun | liste justifiée>
- Ajouts au BACKLOG : <liste>
- Risques identifiés pour la phase suivante : <liste>
STATUT : EN ATTENTE DE VALIDATION — « GO PHASE <X+1> » requis.
```

### 0.5 Étiquetage des gates : [CI] vs [LOCAL]

Chaque gate s'exécute dans UN des deux contextes — les confondre rend certains gates vides de sens (ex : comparer l'état des données sur un checkout CI neuf qui n'a aucun `memory_data/`).

| Contexte | Gates | Pourquoi |
|---|---|---|
| **[CI]** (checkout neuf, reproductible) | ruff, lint-imports, mypy-conformité (F1bis), suites pytest, snapshot-routes (A6/B5b/C7b/E2b), imports ancien namespace (B4a/B4b), smoke_runtime `--fake-llm` (C8/C10), install à froid (B9) | Aucune dépendance à un état préexistant |
| **[LOCAL]** (ta machine, vraies données) | continuité des données (A8/B8 : faits, tokens, 8 skills, faces), smoke `--real` (clé Anthropic), tests manuels de fin de phase, `jarvis voice` réel | Dépend de TON état runtime, irreproductible en CI |

Claude Code précise le contexte de chaque gate dans ses rapports. Un gate [LOCAL] n'est JAMAIS reporté en CI ni réputé couvert par elle.

---

## 1. État des lieux mesuré (baseline du 09/06/2026)

Ces chiffres sont la **baseline**. Plusieurs gates de validation y font référence.

| Métrique | Valeur | Commande de mesure |
|---|---|---|
| Fichiers Python | 258 | `find . -name "*.py" -not -path "./.git/*" \| wc -l` |
| Lignes Python | ~46 500 | `find . -name "*.py" -not -path "./.git/*" \| xargs wc -l \| tail -1` |
| Imports indentés (différés) hors tests | 251 | cf. §A1 du script `scripts/migration/audit_imports.sh` (créé en Phase A) |
| Fichiers avec imports différés inter-packages | 58 | idem |
| Packages top-level à la racine | 20 dossiers | `ls -d */` |
| Plus gros fichier | `api/http_config.py` (942 l.) | `wc -l` |
| Fichiers de tests | 47 (à plat) | `ls tests/ \| wc -l` |

### 1.1 Cycles de dépendances confirmés (à éliminer)

```
CYCLE 1 : core ↔ llm           (llm/api.py importe core ; core importe llm)
CYCLE 2 : core ↔ memory        (masqué par imports différés, ex: core/session.py L53)
CYCLE 3 : skills ↔ agent       (cycle direct)
CYCLE 4 : core → background → memory → core   (transitif)
ANOMALIE : tools → api         (inversion de couche — un outil importe la couche API)
```

### 1.2 Graphe de dépendances actuel (imports top-level)

```
core       -> background, config, llm
memory     -> core, llm
tools      -> api(!), config, memory
skills     -> agent, memory
agent      -> config, core, llm, memory, skills
proactive  -> background, config, core, llm, memory, skills
api        -> audio, background, channels, config, core, memory, tools, vision
background -> config, llm, memory, tools
audio      -> config, core
llm        -> config, core(!)
vision     -> config
analytics  -> (autonome)
channels   -> (autonome)
```

---

## 2. Architecture cible

### 2.1 Arborescence

```
jarvis-OS/
├── src/jarvis/
│   ├── kernel/              # L0 — ne dépend de RIEN du projet
│   │   ├── __init__.py          (exports publics explicites)
│   │   ├── schemas.py           (modèles Pydantic partagés inter-couches)
│   │   ├── contracts.py         (Protocols : LLMProvider, MemoryStore, ToolRegistry…)
│   │   ├── events.py            (bus d'événements asyncio pub/sub)
│   │   ├── errors.py            (hiérarchie d'exceptions Jarvis)
│   │   └── settings.py          (pydantic-settings, ex config/settings.py)
│   │
│   ├── providers/           # L1 — implémente les contrats ; dépend de kernel uniquement
│   │   ├── llm/                 (ex llm/ : anthropic, mistral, gemini, ollama, factory)
│   │   ├── memory/              (ex memory/ : kernel SQLite+FTS5, sessions, topics, index…)
│   │   ├── audio/               (ex audio/ : STT, TTS, VAD, chunker, clap)
│   │   └── vision/              (ex vision/)
│   │
│   ├── capabilities/        # L1 — dépend de kernel uniquement
│   │   ├── tools/               (ex tools/)
│   │   └── skills/              (ex skills/, y compris installed/)
│   │
│   ├── engine/              # L2 — orchestration ; dépend de kernel + injection
│   │   ├── agent.py, gateway.py, router.py, session.py   (ex core/)
│   │   ├── budget.py, tracking.py, audit.py, auth.py,
│   │   │   permissions.py, approval_checker.py, connectivity.py, vocab.py
│   │   ├── mission/             (ex agent/ : orchestrator, verifier, reflexion,
│   │   │                         capability_engine, governance, worker_agent, backends/)
│   │   ├── proactive/           (ex proactive/)
│   │   └── background/          (ex background/)
│   │
│   ├── interfaces/          # L3 — points d'entrée ; peut importer tout en dessous
│   │   ├── api/                 (ex api/)
│   │   ├── channels/            (ex channels/)
│   │   ├── voice/               (ex voice_agent.py → voice/agent.py)
│   │   └── ui/                  (ex ui/)
│   │
│   ├── analytics/           # L1 (autonome)
│   ├── hardware/            # L1 (autonome — macropad_2k)
│   ├── bootstrap.py         # Composition root — SEUL fichier autorisé à tout importer
│   └── app.py               # Factory FastAPI minimale (ex main.py dégraissé)
│
├── prompts/                 # inchangé (assets, pas du code)
├── notices/                 # inchangé
├── scripts/
│   ├── validation/              (ex phase*_real_*.py)
│   └── migration/               (scripts d'audit créés par ce CDC)
├── tests/
│   ├── unit/                    (miroir de src/jarvis/)
│   └── integration/
├── docs/
│   ├── CDC_jarvis_evolution.md      (déplacé depuis la racine)
│   ├── CDC_refonte_architecture.md  (ce document)
│   ├── INTEGRATION-DONE.md          (déplacé)
│   └── migration/BACKLOG.md
├── main.py                  # shim de compat : `from jarvis.app import main; main()`
├── voice_agent.py           # shim de compat équivalent
├── jarvis                   # CLI inchangée (chemins mis à jour)
├── pyproject.toml           # package `jarvis-os`, src-layout
└── …
```

### 2.2 Les trois règles d'or (invariants permanents)

```
RÈGLE 1 — kernel n'importe RIEN de jarvis.* (stdlib + pydantic uniquement).
RÈGLE 2 — providers/ et capabilities/ n'importent QUE jarvis.kernel.
RÈGLE 3 — engine/ n'importe QUE jarvis.kernel ; il reçoit providers,
          tools et skills PAR INJECTION (constructeurs).
          interfaces/ et bootstrap.py peuvent importer toutes les couches.
```

Corollaires :
- **Aucun import différé** pour contourner un cycle (autorisé uniquement : sous `TYPE_CHECKING`, ou pour du lazy-loading de dépendances lourdes optionnelles type `ultralytics` — chaque cas doit être commenté `# lazy: <raison>`).
- **Toute communication « vers le haut »** (un module bas qui doit notifier un module haut) passe par le bus d'événements `kernel/events.py`.
- Ces règles seront **rendues exécutables** par import-linter en Phase F.

---

## 3. PHASE A — Kernel & contrats (fondations, zéro déplacement)

**Objectif :** créer la couche L0 (`kernel`) et l'outillage d'audit, sans déplacer aucun package existant. À la fin de cette phase, le code actuel fonctionne à l'identique, mais les types partagés ont un foyer unique.

**Durée estimée :** 1 session.

### A.0 Préconditions
- **Tag `pre-reorg` posé** sur `main`, tests verts sur ce tag (règle §0.8). Vérifier : `git tag -l pre-reorg` non vide et `git status` propre.
- Branche `refonte/architecture-couches` créée depuis ce tag.
- Baseline verte : `uv run pytest -x -q` passe AVANT toute modification. Si la suite est rouge au départ, STOP immédiat et rapport.

### A.1 Tâches

1. **Créer `scripts/migration/audit_imports.sh`** — le thermomètre de toute la migration :
   ```bash
   #!/usr/bin/env bash
   # Audit des imports différés inter-packages (hors tests, hors TYPE_CHECKING)
   PKGS="core|memory|tools|skills|agent|api|proactive|channels|background|llm|config|audio|vision|kernel|jarvis"
   echo "== Imports différés inter-packages =="
   grep -rn "^\s\+from \($PKGS\)" --include="*.py" . \
     --exclude-dir=.git --exclude-dir=tests --exclude-dir=.venv \
     | grep -v "TYPE_CHECKING" | grep -v "# lazy:" | tee /tmp/lazy_imports.txt | wc -l
   echo "== Fichiers concernés =="
   cut -d: -f1 /tmp/lazy_imports.txt | sort -u | wc -l
   echo "== Imports DYNAMIQUES (échappent aux greps ^from — à réécrire aussi en Phase B) =="
   grep -rnE "import_module\(|__import__\(" --include="*.py" . \
     --exclude-dir=.git --exclude-dir=tests --exclude-dir=.venv \
     | grep -E "core|llm|memory|tools|skills|agent|api|proactive|background|channels|audio|vision"
   ```
   Baseline connue des imports dynamiques : **14+ `__import__("tools.X")` dans `voice_agent.py`** (l.144-197). Attention : le pattern réel du repo est `__import__`, pas `import_module` — les deux sont couverts.
   Committer, puis exécuter et **consigner la baseline exacte dans le rapport de phase** (attendu ≈ 251 imports / 58 fichiers).

2. **Créer `scripts/migration/snapshot_routes.py`** — preuve mécanique de l'identité des routes HTTP à travers toute la migration :
   ```python
   #!/usr/bin/env python3
   """Snapshot trié de toutes les routes FastAPI (méthode + path).
   Usage : uv run python scripts/migration/snapshot_routes.py > routes.txt"""
   try:
       from jarvis.app import app          # à partir de la Phase B
   except ImportError:
       from main import app                # Phase A
   rows = []
   for r in app.routes:
       m = getattr(r, "methods", None)
       rows += [f"{x:7} {r.path}" for x in sorted(m)] if m else [f"{type(r).__name__:7} {r.path}"]
   print("\n".join(sorted(set(rows))))
   ```
   Capturer la **baseline** : `uv run python scripts/migration/snapshot_routes.py > scripts/migration/routes.baseline.txt` et la committer. Tout gate de routes ultérieur (B5, C7, E2) est un `diff` contre ce fichier — sortie vide exigée.

3. **Créer `kernel/`** (à la racine pour l'instant — il migrera dans `src/jarvis/` en Phase B) :
   - `kernel/errors.py` : hiérarchie `JarvisError` → `LLMError`, `MemoryError_`, `ToolError`, `SkillError`, `BudgetExceeded`, `PermissionDenied`. Recenser les exceptions ad hoc existantes (`grep -rn "class.*Error" --include="*.py" core/ llm/ memory/ tools/`) et les faire hériter de cette hiérarchie **sans changer leur comportement**.
   - `kernel/schemas.py` : y déplacer les modèles Pydantic **partagés entre ≥ 2 packages**. Candidats identifiés : contenus de `agent/schemas.py`, `proactive/schemas.py`, `memory/schemas.py` utilisés ailleurs, types de messages LLM. Méthode : pour chaque modèle, `grep -rn "from <pkg>.schemas import <Nom>"` → s'il apparaît dans un autre package, il monte dans kernel. Sinon il reste local. Laisser dans les fichiers d'origine des **ré-exports** (`from kernel.schemas import X  # noqa: F401`) pour ne casser aucun import existant.
   - `kernel/contracts.py` : définir les Protocols (signatures calquées sur les implémentations EXISTANTES — ne rien inventer) :
     - `LLMProvider` (calqué sur `llm/base.py`)
     - `MemoryStore`, `SessionStore`, `TopicStore`, `MemoryIndex` (calqués sur `memory/`)
     - `ToolRegistry`, `Tool` (calqués sur `tools/registry.py`, `tools/base.py`)
     - `SkillRegistry`, `Skill` (calqués sur `skills/`)
     - `Channel` (calqué sur `channels/base.py`)
     - `NotificationSink`, `Collector` (calqués sur `background/notifications.py`, `proactive/collectors/base.py`)
   - `kernel/events.py` : bus pub/sub asyncio minimaliste (~60-80 lignes) : `class EventBus` avec `subscribe(event_type, handler)`, `publish(event)` (gather des handlers async, isolation des exceptions par handler + log loguru), `bus = EventBus()` singleton module. Définir les premiers événements en dataclasses : `MissionCompleted`, `MemoryIngested`, `NotificationRequested`, `BudgetThresholdReached`. **Ne brancher personne dessus pour l'instant** (Phase D).
   - `kernel/settings.py` : ré-export de `config/settings.py` (le vrai déménagement attend la Phase B).

4. **Créer `scripts/migration/snapshot_data_state.py`** — baseline de l'état runtime sur disque (gitignoré, donc invisible à git, aux tests et à tous les autres gates) :
   - compte de faits du store mémoire (SQLite de `memory_data/`),
   - inventaire des fichiers tokens présents dans `config/` (`google_token.json`, `google_gmail_token.json`, `spotify_token.json`, `deezer_token.json` — présence + taille, JAMAIS le contenu),
   - compte de skills dans `skills/installed/` (attendu : 8) + leur chargement effectif via le loader,
   - compte de fichiers dans `vision/faces/`.
   Sortie dans `scripts/migration/data_state.baseline.txt` (comptes uniquement → committable). Le GATE B8 comparera contre cette baseline.

5. **Marqueurs de tests `integration` (version minimale)** : taguer `@pytest.mark.integration` les tests qui touchent Docker, le réseau, un LLM réel ou le disque lourd (≈ 13 fichiers identifiés : `grep -rln "docker\|anthropic\|httpx\|sqlite3.connect" tests/`). Config pytest (`markers`, et `addopts` ne filtrant PAS par défaut). Objectif : `pytest -m "not integration" -q` < 30 s dès la fin de A — c'est le gate par-commit de B et C (règle §0.4). La réorganisation complète des tests reste en Phase F.

6. **Tests unitaires du kernel** : `tests/test_kernel_events.py` (publish/subscribe, handler en erreur n'empêche pas les autres, événements typés), `tests/test_kernel_errors.py` (hiérarchie).

### A.2 Auto-vérifications (à exécuter et coller dans le rapport)

```bash
# GATE A1 — kernel n'importe rien du projet
grep -rn "^from \(core\|memory\|tools\|skills\|agent\|api\|proactive\|channels\|background\|llm\|config\|audio\|vision\)" kernel/ ; test $? -eq 1 && echo "GATE A1 ✅"

# GATE A2 — tests verts, lint propre
uv run pytest -x -q && uv run ruff check . && echo "GATE A2 ✅"

# GATE A3 — le serveur démarre toujours
timeout 15 uv run python -c "import main" && echo "GATE A3 ✅"

# GATE A4 — baseline d'audit consignée
bash scripts/migration/audit_imports.sh

# GATE A5 — aucun import existant cassé (les ré-exports fonctionnent)
uv run python -c "from agent.schemas import *; from proactive.schemas import *" && echo "GATE A5 ✅"

# GATE A6 — baseline des routes capturée et committée
test -s scripts/migration/routes.baseline.txt && echo "GATE A6 ✅"

# GATE A7 — suite rapide opérationnelle (gate par-commit de B/C)
time uv run pytest -m "not integration" -q   # < 30 s, verte

# GATE A8 — baseline de l'état des données capturée
uv run python scripts/migration/snapshot_data_state.py && test -s scripts/migration/data_state.baseline.txt && echo "GATE A8 ✅"
```

### A.3 Critères de validation humaine (STOP)
- Relecture de `kernel/contracts.py` : les Protocols reflètent-ils fidèlement les signatures réelles ? (C'est LE document d'architecture du projet — il mérite 20 minutes de lecture attentive.)
- Relecture de `kernel/events.py`.
- Rapport de phase conforme au §0.3. Tag `migration-phase-A` après GO.

---

## 4. PHASE B — Migration vers le layout `src/jarvis/`

**Objectif :** déplacer tout le code applicatif dans `src/jarvis/` selon l'arborescence cible (§2.1), réécrire tous les imports, rendre le package installable. **Aucun changement de logique — uniquement des déplacements et des renommages d'imports.**

**Durée estimée :** 2-3 sessions. C'est la phase la plus massive mais la plus mécanique.

### B.0 Préconditions
- Tag `migration-phase-A` posé. GO reçu.

### B.1 Table de migration (exhaustive et impérative)

| Source (racine) | Destination (`src/jarvis/`) |
|---|---|
| `kernel/` | `kernel/` |
| `llm/` | `providers/llm/` |
| `memory/` | `providers/memory/` |
| `audio/` | `providers/audio/` |
| `vision/` | `providers/vision/` |
| `tools/` | `capabilities/tools/` |
| `skills/` | `capabilities/skills/` |
| `core/` | `engine/` (fichiers à plat : agent, gateway, router, session, budget, tracking, audit, auth, permissions, approval_checker, connectivity, vocab) |
| `agent/` | `engine/mission/` |
| `proactive/` | `engine/proactive/` |
| `background/` | `engine/background/` |
| `api/` | `interfaces/api/` |
| `channels/` | `interfaces/channels/` |
| `voice_agent.py` | `interfaces/voice/agent.py` |
| `ui/` | `interfaces/ui/` |
| `analytics/` | `analytics/` |
| `hardware/` | `hardware/` |
| `config/settings.py` | `kernel/settings.py` (fusion réelle, fin du ré-export) |
| `config/*.yaml`, `*.json`, `approvals.py`, `backends.py` | `kernel/config/` ou rester en `config/` racine comme **données** — DÉCISION REQUISE, voir B.4 Q1 |
| `main.py` | `src/jarvis/app.py` + shim `main.py` racine |

Restent à la racine : `prompts/`, `notices/`, `scripts/`, `tests/`, `jarvis` (CLI), `Makefile`, `docs/`.

### B.2 Tâches

1. **Déplacer avec `git mv`** (préservation de l'historique — JAMAIS de copier-coller).
2. **Réécrire les imports** par passes successives de find/replace, package par package, dans cet ordre : kernel → providers → capabilities → engine → interfaces. Après CHAQUE package migré : `uv run python -c "import jarvis.<package>"` + commit.
   Mapping : `from core.X import` → `from jarvis.engine.X import` ; `from llm.` → `from jarvis.providers.llm.` ; etc.
   **Imports dynamiques inclus** : les namespaces sous forme de chaîne (`__import__("tools.weather")`, `import_module("...")`) échappent aux greps `^from` — les réécrire aussi (`__import__("jarvis.capabilities.tools.weather")`). Source de vérité : la section « imports dynamiques » d'`audit_imports.sh`. Baseline : 14+ occurrences dans `voice_agent.py`.

2bis. **Alias de compatibilité pour les skills installés (code-as-data).** Les 8 skills de `skills/installed/` (astronomy, clock, fusion360, bambulab-printer, globe-view, mode-streameur, system-monitor, weather) contiennent `from skills.base import SkillBase/PresetSkill` — du code utilisateur sur disque, hors de portée du find/replace sur `src/`, qui casserait silencieusement au chargement après la migration. Solution retenue : le loader de skills injecte un **alias de namespace** avant tout chargement :
   ```python
   # capabilities/skills/_loader.py — avant le premier import de skill
   import sys, jarvis.capabilities.skills as _skills_pkg
   sys.modules.setdefault("skills", _skills_pkg)   # compat : skills installés et partagés
   ```
   Justification : les skills sont des artefacts portables (Skill Lab, catalogue jarvis-skills, partage communautaire) — leur namespace d'import est une **API publique stable**, on ne demande pas aux utilisateurs de réécrire leurs skills. Statut : ce n'est PAS un shim de migration mais un **ABI d'import supporté**, documenté dans `docs/architecture/skills-abi.md` (symboles garantis : `skills.base.SkillBase`, `skills.base.PresetSkill` ; politique de dépréciation : jamais sans version majeure + outil de migration). Le GATE C9 l'exclut par une règle nommée — un nettoyage futur « zéro shim » ne doit pas pouvoir l'arracher par zèle.
3. **`pyproject.toml`** : `name = "jarvis-os"`, configuration src-layout (`[tool.hatch.build.targets.wheel] packages = ["src/jarvis"]` ou équivalent uv/setuptools), supprimer le nom `jarvis-v3`.
4. **Shims de compatibilité racine + découplage du CLI** : `main.py` → `from jarvis.app import main; main()` ; `voice_agent.py` → idem vers `jarvis.interfaces.voice.agent`. MAIS le CLI `jarvis` ne doit PAS dépendre de la survie de ces shims (couplage caché — il les référence à 4+ endroits) :
   - définir des entry points module : `__main__.py`/`main()` dans `jarvis.app` et `jarvis.interfaces.voice.agent` ;
   - repointer `jarvis` et le `Makefile` : `uv run python -m jarvis.app`, `uv run python -m jarvis.interfaces.voice.agent dev` ;
   - **mettre à jour les patterns de gestion de process** : `jarvis` l.55 fait `pkill -f "voice_agent.py"` — avec l'entry point module ce pattern ne matche plus rien et `jarvis stop` laisserait un process voix zombie. Nouveau pattern : `pkill -f "jarvis.interfaces.voice.agent"` (idem pour tout pattern sur `main.py`) ;
   - les shims racine restent UNE version pour les appelants externes (interface utilisateur inchangée : `jarvis run` etc.), leur retrait → BACKLOG.
5. **Chemins runtime — RISQUE SILENCIEUX N°1 de la migration.** Baseline mesurée : **23 occurrences de `Path(__file__)` et 76 chaînes de chemins en dur** hors tests (`memory_data/…`, `prompts/…`, `config/…`, `ui/…`, `skills/…` — notamment dans `proactive/store.py`, `proactive/curator.py`, `api/analytics.py`, `api/http_system.py`, `config/settings.py`). Le passage en `src/` change la profondeur de `__file__` : tout casse **à l'exécution**, rien à l'import ni en test. Méthode impérative : (a) grep exhaustif consigné dans le rapport — la liste COMPLÈTE, pas un échantillon ; (b) créer `kernel/paths.py` avec `PROJECT_ROOT` (résolu une fois, robuste au déplacement) et des constantes dérivées (`MEMORY_DATA_DIR`, `PROMPTS_DIR`, `UI_STATIC_DIR`, `CONFIG_DIR`, `SKILLS_DIR`) ; (c) remplacer chaque occurrence par ces constantes — aucun `Path("memory_data/...")` littéral ne doit survivre ; (d) **migrer `vision/faces/`** : ce sont des données utilisateur stockées DANS le dossier du package `vision/` — après migration elles se retrouveraient dans le package installable. Les déplacer vers un répertoire de données (`vision_data/faces/` à la racine, résolu via `kernel/paths.py::FACES_DIR`), avec déplacement des fichiers réels existants, pas seulement du chemin ; (e) **étendre l'audit à la couche SHELL** — l'audit `--include="*.py"` ne voit ni `setup.sh` (l.394-396 : `mkdir -p memory_data/* workspace/projects vision/faces` ; l.381 : `models/piper/`), ni `install.sh` (duplication, l.64-94), ni le `Makefile`, ni le CLI `jarvis`. Chaque chemin de données de ces fichiers est réconcilié avec la disposition de `kernel/paths.py` — en particulier le `mkdir vision/faces` de setup.sh doit suivre le déplacement vers `FACES_DIR`, sinon les **installs à froid** créent l'ancienne disposition et cassent en silence (les installs existants survivent : leurs dossiers préexistent — c'est précisément pourquoi tu ne le verrais pas, mais un membre du Labo qui clone, oui).
6. **Tests** : adapter les imports des 47 fichiers de tests (réorganisation en miroir reportée à la Phase F — ici on ne touche que les imports).

### B.3 Auto-vérifications

```bash
# GATE B1 — plus aucun package applicatif à la racine
ls -d core llm memory tools skills agent proactive background api channels audio vision 2>/dev/null ; test $? -ne 0 && echo "GATE B1 ✅"

# GATE B2 — le package s'installe et s'importe
uv pip install -e . && uv run python -c "import jarvis; import jarvis.app" && echo "GATE B2 ✅"

# GATE B3 — tests verts, lint propre
uv run pytest -x -q && uv run ruff check . && echo "GATE B3 ✅"

# GATE B4 — plus AUCUN import de l'ancien namespace (statique ET dynamique)
grep -rn "^from \(core\|llm\|memory\|tools\|skills\|agent\|proactive\|background\|api\|channels\|audio\|vision\)\b" --include="*.py" src/ tests/ scripts/ main.py voice_agent.py ; test $? -eq 1 && echo "GATE B4a ✅"
grep -rnE "import_module\(|__import__\(" --include="*.py" src/ main.py voice_agent.py | grep -E '"(core|llm|memory|tools|skills|agent|api|proactive|background|channels|audio|vision)' ; test $? -eq 1 && echo "GATE B4b ✅ (zéro import dynamique de l'ancien namespace)"

# GATE B5 — démarrage réel du serveur + smoke test HTTP + IDENTITÉ DES ROUTES
(uv run python main.py &) && sleep 8 && curl -sf http://localhost:8000/admin > /dev/null && echo "GATE B5a ✅" ; pkill -f "python main.py"
uv run python scripts/migration/snapshot_routes.py > /tmp/routes.now.txt
diff scripts/migration/routes.baseline.txt /tmp/routes.now.txt && echo "GATE B5b ✅ (routes identiques)"

# GATE B6 — l'historique Git est préservé (échantillon)
git log --follow --oneline src/jarvis/engine/gateway.py | wc -l   # doit être > 1

# GATE B7 — résolution des chemins runtime (le test ne suffit pas, exécution réelle exigée)
grep -rn 'Path(__file__)\|"\(ui\|prompts\|config\|memory_data\|skills\)/' --include="*.py" src/ | grep -v "kernel/paths.py" ; test $? -eq 1 && echo "GATE B7a ✅ (zéro chemin en dur hors paths.py)"
# B7b — check runtime : un script qui via le code réel (pas de réimplémentation) :
#   1. charge un prompt depuis PROMPTS_DIR, 2. écrit puis relit un fichier dans MEMORY_DATA_DIR,
#   3. sert un asset statique via l'app (TestClient sur /static/…), 4. charge un skill installé.
uv run python scripts/migration/check_paths_runtime.py && echo "GATE B7b ✅"
```

### B.4 Questions à trancher AVANT exécution (Claude Code : poser ces questions au démarrage de la phase)
- **Q1 :** `config/tools.yaml`, `permissions.yaml`, `approvals.json`, `backends.json` — données utilisateur (restent à la racine dans `config/`) ou code (migrent dans le package) ? Recommandation : données à la racine, loaders dans `kernel/`.
- **Q2 :** `skills/installed/` contient des skills installés par l'utilisateur — doivent-ils vivre DANS le package ou dans un répertoire de données utilisateur hors package (comme `memory_data/`) ? Recommandation : hors package (`skills_data/installed/`), chargés dynamiquement. Si retenu : **migrer les 8 skills réels existants** (déplacement des fichiers, pas seulement du loader), et le GATE B8 vérifie leur chargement post-migration. L'alias de namespace (B.2bis) est requis dans les deux cas.

### B.5 Critères de validation humaine (STOP)
- Barth lance lui-même `jarvis run`, ouvre `/admin`, fait un échange de chat, vérifie un outil (météo) et la mémoire.
- Barth lance `jarvis voice` si LiveKit est dispo.
- Rapport de phase + tag `migration-phase-B`.

---

## 5. PHASE C — Inversion de dépendance & composition root

**Objectif :** éliminer les cycles 1 à 3 (§1.1) en faisant dépendre `engine/` des **Protocols** plutôt que des implémentations. Créer `bootstrap.py`. Réduire les imports différés inter-couches à ~0 dans `engine/` et `providers/`.

**Durée estimée :** 2-3 sessions. C'est la phase la plus délicate — la seule qui touche aux constructeurs.

### C.0 Préconditions
- Tag `migration-phase-B`. GO reçu.
- Relire `kernel/contracts.py` validé en Phase A.

### C.1 Tâches

1. **Créer `src/jarvis/bootstrap.py`** — l'unique composition root :
   ```python
   @dataclass
   class Container:
       settings: Settings
       bus: EventBus
       llm: LLMProvider
       memory: MemoryStore
       sessions: SessionStore
       topics: TopicStore
       tools: ToolRegistry
       skills: SkillRegistry
       gateway: Gateway
       # … complété au fil de la phase

   def build(settings: Settings | None = None) -> Container:
       """Construit le graphe d'objets dans l'ordre : settings → bus →
       providers → registries → engine. AUCUNE logique métier ici."""
   ```
   Ordre de construction strict : settings → bus → providers (llm, memory, audio, vision) → capabilities (tools, skills — qui reçoivent les providers dont ils ont besoin) → engine (gateway, agent, session manager, budget, mission engine, proactive, background) → retour du Container.

2. **Refactorer les constructeurs d'`engine/`** un fichier à la fois, dans cet ordre (du moins couplé au plus couplé) : `budget.py` → `tracking.py` → `session.py` → `router.py` → `agent.py` → `gateway.py` → `mission/orchestrator.py` → `proactive/engine.py` → `background/scheduler.py`.
   Pour chaque fichier : (a) typer les paramètres du constructeur avec les Protocols de `kernel.contracts`, (b) supprimer les instanciations internes et les imports différés correspondants, (c) câbler dans `bootstrap.py`, (d) adapter les tests (injection de fakes), (e) commit.

3. **Casser le CYCLE 1 (core ↔ llm)** : identifier ce que `providers/llm/api.py` importe d'`engine` (`ToolCapture`, etc. — ex-`core`). Ces types descendent dans `kernel/schemas.py` ou `kernel/contracts.py`. `providers/llm` ne doit plus importer `engine`. Idem **CYCLE 3 (skills ↔ agent)** : les schemas partagés entre `capabilities/skills` et `engine/mission` montent dans `kernel/schemas.py`.

4. **Dégraisser `app.py`** (ex-main.py, 708 l.) : il ne garde que la factory FastAPI, le montage des routers, le lifespan qui appelle `bootstrap.build()` et stocke le Container dans `app.state`. Cible : **< 120 lignes**. Les routers d'`interfaces/api/` accèdent au Container via dependency injection FastAPI (`Depends`), pas par import global.

5. **Purger les imports différés** : repasser sur la liste produite par `audit_imports.sh`. Chaque import différé restant est soit supprimé (résolu par l'injection), soit explicitement annoté `# lazy: <raison>` (réservé aux deps lourdes optionnelles : ultralytics, faster-whisper, livekit).

6. **Purger les ré-exports de compatibilité posés en Phase A** : les `from kernel.schemas import X  # noqa: F401` laissés dans les anciens fichiers schemas n'ont plus de raison d'être une fois tous les imports réécrits. Chaque type doit avoir UN foyer. Supprimer les ré-exports, corriger les derniers importeurs.

7. **Créer `scripts/validation/smoke_runtime.py`** — le scénario runtime sur le graphe câblé (les tests unitaires ne couvrent pas l'ordre d'init, la durée de vie des singletons ni le câblage bootstrap). Le script boote via `bootstrap.build()` (PAS via uvicorn) et exécute séquentiellement :
   1. une **mission complète** du Mission Engine (orchestration → vérification 3 couches → Reflexion) ;
   2. une **notification proactive** qui traverse le bus d'événements de bout en bout ;
   3. un **outil dépendant d'un provider injecté** (ex : un tool memory qui lit/écrit via `MemoryStore`) ;
   4. la **voix** si LiveKit est disponible localement (skip propre sinon).
   **Deux modes** : `--fake-llm` injecte un `FakeLLMProvider` déterministe via bootstrap (réponses canned, zéro réseau) — c'est le mode du gate automatique, et la démonstration que l'injection fonctionne ; `--real` utilise la clé Anthropic réelle — réservé à la validation humaine de fin de phase. Créer `tests/fakes/llm.py` (`FakeLLMProvider` conforme au Protocol) au passage : il resservira dans toute la suite de tests.
   Le script accepte `--process=api|voice` (voir tâche 8).

8. **Le process voix est un SECOND composition root — pas un simple fichier déplacé.** État actuel de `interfaces/voice/agent.py` (ex `voice_agent.py`) : il construit son graphe en direct — 14+ `__import__("tools.X")` en lambdas, `Path(__file__)`, `.env` chargé localement, `AgentSession` instancié à la main — dans un **process séparé** (`jarvis voice` / `make voice`), sans passer par aucun composition root. Après l'inversion de dépendance, il serait soit cassé, soit en contradiction frontale avec l'architecture. Décision architecturale (ferme) :
   - `bootstrap.build()` est **process-agnostic** : aucune dépendance à FastAPI, uvicorn ou LiveKit dans `bootstrap.py`.
   - `interfaces/voice/agent.py` appelle `bootstrap.build()` et tire `llm`, `memory`, `tools`, `gateway` du Container — les 14 lambdas `__import__` disparaissent au profit du `ToolRegistry` injecté.
   - Chaque process (API, voix) construit **son propre Container** ; ils partagent l'état via le SQLite sur disque (comportement déjà actuel). Vérifié sur le code : NI `journal_mode=WAL` NI `busy_timeout` ne sont actuellement configurés. À l'ouverture de connexion (un seul endroit : le provider memory) : `PRAGMA journal_mode=WAL` (lecteurs non bloqués par l'écrivain) **ET** `PRAGMA busy_timeout=5000` (le WAL sérialise toujours les écrivains — sans timeout, écriture concurrente voix+API = `database is locked`). Consigner dans le rapport.
   - Si un blocage technique impose une exception (contrainte LiveKit), elle est DOCUMENTÉE dans `docs/architecture/` avec sa justification — jamais silencieuse.

### C.2 Auto-vérifications

```bash
# GATE C1 — engine n'importe plus ni providers ni capabilities ni interfaces
grep -rn "^from jarvis\.\(providers\|capabilities\|interfaces\)" --include="*.py" src/jarvis/engine/ | grep -v TYPE_CHECKING ; test $? -eq 1 && echo "GATE C1 ✅"

# GATE C2 — providers n'importent que kernel
grep -rn "^from jarvis\.\(engine\|capabilities\|interfaces\)" --include="*.py" src/jarvis/providers/ | grep -v TYPE_CHECKING ; test $? -eq 1 && echo "GATE C2 ✅"

# GATE C3 — capabilities n'importent que kernel
grep -rn "^from jarvis\.\(engine\|providers\|interfaces\)" --include="*.py" src/jarvis/capabilities/ | grep -v TYPE_CHECKING ; test $? -eq 1 && echo "GATE C3 ✅"
# NOTE : si un tool a structurellement besoin d'un provider (ex: tools/vision),
# il le reçoit par injection à l'enregistrement dans bootstrap — pas par import.

# GATE C4 — imports différés inter-couches ≈ 0 (vs baseline 251)
bash scripts/migration/audit_imports.sh   # attendu : < 15, tous annotés "# lazy:"

# GATE C5 — app.py dégraissé
test $(wc -l < src/jarvis/app.py) -lt 120 && echo "GATE C5 ✅"

# GATE C6 — bootstrap construit le graphe complet sans réseau
uv run python -c "from jarvis.bootstrap import build; c = build(); print(type(c).__name__)" && echo "GATE C6 ✅"

# GATE C7 — tests verts + smoke test serveur + identité des routes
uv run pytest -x -q && echo "GATE C7a ✅"
uv run python scripts/migration/snapshot_routes.py > /tmp/routes.now.txt
diff scripts/migration/routes.baseline.txt /tmp/routes.now.txt && echo "GATE C7b ✅"

# GATE C8 — scénario runtime sur le graphe câblé (mission + bus + tool injecté)
uv run python scripts/validation/smoke_runtime.py --fake-llm && echo "GATE C8 ✅"

# GATE C9 — zéro ré-export résiduel (chaque type a UN foyer)
# EXCLUSION NOMMÉE (permanente, pas un oubli) : l'alias ABI skills de _loader.py (B.2bis)
# n'est PAS un ré-export de migration — il est documenté comme contrat public (cf. docs).
grep -rn "noqa: F401" --include="*.py" src/jarvis/ | grep -v "capabilities/skills/_loader.py" ; test $? -eq 1 && echo "GATE C9 ✅"
# (tolérance : liste justifiée < 3 dans le rapport, ex. exports volontaires d'__init__.py)

# GATE C10 — le process voix compose et boote en standalone via son propre Container
# (sans serveur API lancé, sans LiveKit réel, zéro réseau)
uv run python scripts/validation/smoke_runtime.py --fake-llm --process=voice && echo "GATE C10 ✅"
grep -cE "__import__\(" src/jarvis/interfaces/voice/agent.py | grep -q "^0$" && echo "GATE C10b ✅ (zéro __import__ résiduel dans la voix)"
```

### C.3 Critères de validation humaine (STOP)
- Relecture de `bootstrap.py` (c'est désormais la carte du système).
- Test manuel complet identique à B.5 + `uv run python scripts/validation/smoke_runtime.py --real` (mission réelle de bout en bout, clé Anthropic).
- `jarvis voice` lancé réellement si LiveKit dispo : un échange vocal avec appel d'outil (météo) — c'est le seul test qui valide le Container voix en conditions réelles.
- Vérifier dans le rapport la liste des `# lazy:` restants et leur justification.
- Tag `migration-phase-C`.

---

## 6. PHASE D — Bus d'événements (casser le CYCLE 4 et les communications montantes)

**Objectif :** remplacer tous les imports « vers le haut » par des publications d'événements sur `kernel.events.bus`. Cible principale : le cycle `engine ← background` (ex `core → background`), les notifications, et les hooks post-mission.

**Durée estimée :** 1-2 sessions.

### D.0 Préconditions
- Tag `migration-phase-C`. GO reçu.

### D.1 Tâches

1. **Inventaire des communications montantes.** Lister tous les points où un module bas appelle un module haut (le grep des imports résiduels de C en révèle la plupart). Cas connus :
   - Gateway/engine → `background/notifications` (file de notifications) → événement `NotificationRequested(channel, payload, priority)`.
   - Fin de mission → déclenchement Reflexion → événement `MissionCompleted(mission_id, verdict, artifacts)` ; `engine/mission/reflexion.py` s'abonne.
   - Ingestion mémoire → consolidation/AutoDream → événement `MemoryIngested(...)` si un couplage direct existe.
   - Budget → alertes → `BudgetThresholdReached(ratio, provider)`.
2. **Brancher les abonnés dans `bootstrap.py`** (section dédiée `# --- Câblage des événements ---` en fin de `build()`). Les abonnements sont EXPLICITES et centralisés — pas d'auto-découverte magique.
3. **Supprimer les imports correspondants** et mettre à jour `audit_imports.sh` si besoin.
4. **Tests** : pour chaque événement, un test unitaire (publication → handler appelé avec le bon payload) + un test d'isolation (handler qui lève → les autres handlers reçoivent quand même, l'erreur est loguée).
5. **Documentation** : créer `docs/architecture/events.md` — table de tous les événements : nom, payload, émetteurs, abonnés. Ce fichier est mis à jour à CHAQUE nouvel événement (règle permanente).

### D.2 Auto-vérifications

```bash
# GATE D1 — plus aucun import montant résiduel (C1-C3 toujours verts)
grep -rn "^from jarvis\.\(providers\|capabilities\|interfaces\)" --include="*.py" src/jarvis/engine/ | grep -v TYPE_CHECKING ; test $? -eq 1 && echo "GATE D1 ✅"

# GATE D2 — events.md exhaustif : chaque dataclass d'événement y figure
python - << 'EOF'
import re, pathlib
src = pathlib.Path("src/jarvis/kernel/events.py").read_text()
doc = pathlib.Path("docs/architecture/events.md").read_text()
events = re.findall(r"class (\w+)\(.*Event.*\):|@dataclass\nclass (\w+)", src)
missing = [e for pair in events for e in pair if e and e not in doc and e != "EventBus"]
print("GATE D2", "✅" if not missing else f"❌ manquants: {missing}")
EOF

# GATE D3 — tests verts + smoke test serveur, et une notification proactive
# réelle traverse le bus (test d'intégration à écrire : collector météo simulé
# → NotificationRequested → sink de test la reçoit)
uv run pytest -x -q && echo "GATE D3 ✅"
```

### D.3 Critères de validation humaine (STOP)
- Relecture de `docs/architecture/events.md` : le flux est-il compréhensible sans lire le code ?
- Test manuel : déclencher un briefing météo proactif, vérifier la notification de bout en bout (WebSocket + Telegram si configuré).
- Tag `migration-phase-D`.

---

## 7. PHASE E — Anomalies de couches & conventions

**Objectif :** réparer l'anomalie `tools → api`, unifier les conventions de nommage d'`interfaces/api/`, scinder le monolithe `http_config.py`.

**Durée estimée :** 1 session.

### E.0 Préconditions
- Tag `migration-phase-D`. GO reçu.

### E.1 Tâches

1. **Anomalie `tools → api`.** Auditer chaque fichier de `capabilities/tools/` qui importait `api` (suspects relevés : `show_view.py`, `preset.py`, et tout fichier listé par le grep). Pour chacun, déterminer le besoin réel :
   - besoin de pousser quelque chose à l'UI → événement (`ViewRequested`, etc.) consommé par la couche interfaces ;
   - besoin d'une logique partagée → la logique descend dans `engine/` ou `kernel/` ;
   - JAMAIS de solution « l'outil importe le router ».
2. **Conventions `interfaces/api/`.** Supprimer le préfixe `http_` (le dossier EST la couche HTTP) : `http_memory.py` → `memory.py`, `http_budget.py` → `budget.py`, etc. (`git mv`). Regrouper les doublons évidents (`analytics.py` + `http_analytics.py` → un seul module). Un router par domaine, nommage aligné sur les domaines d'`engine/`.
3. **Scinder `http_config.py` (942 l.)** en sous-modules par responsabilité (`api/config/llm.py`, `api/config/integrations.py`, `api/config/system.py`… selon le contenu réel — proposer le découpage AVANT de l'exécuter, dans un mini-rapport intermédiaire).
4. **`__init__.py` comme API publique** : pour `kernel`, `providers/*`, `capabilities/*`, `engine` — exports explicites avec `__all__`. Modules internes préfixés `_` quand pertinent (généraliser la convention déjà présente dans skills/).

### E.2 Auto-vérifications

```bash
# GATE E1 — plus aucun import api depuis capabilities
grep -rn "from jarvis.interfaces" --include="*.py" src/jarvis/capabilities/ src/jarvis/providers/ src/jarvis/engine/ ; test $? -eq 1 && echo "GATE E1 ✅"

# GATE E2 — convention de nommage api unifiée + PREUVE que les URL n'ont pas bougé
ls src/jarvis/interfaces/api/ | grep "^http_" ; test $? -eq 1 && echo "GATE E2a ✅"
uv run python scripts/migration/snapshot_routes.py > /tmp/routes.now.txt
diff scripts/migration/routes.baseline.txt /tmp/routes.now.txt && echo "GATE E2b ✅ (renommage des modules, URLs intactes)"

# GATE E3 — plus de fichier > 600 lignes dans interfaces/api
find src/jarvis/interfaces/api -name "*.py" | xargs wc -l | awk '$1 > 600 && $2 != "total" {print; f=1} END {exit f}' && echo "GATE E3 ✅"

# GATE E4 — tests verts + smoke test complet (admin, chat, un outil, mémoire)
uv run pytest -x -q && echo "GATE E4 ✅"
```

### E.3 Critères de validation humaine (STOP)
- Vérifier que toutes les pages de l'UI admin répondent (l'identité des URLs est déjà prouvée mécaniquement par E2b).
- Tag `migration-phase-E`.

---

## 8. PHASE F — Verrouillage, hygiène & finalisation

**Objectif :** rendre l'architecture **auto-défendue** (la dette ne peut plus revenir), nettoyer le repo, réorganiser les tests, merger.

**Durée estimée :** 1-2 sessions.

### F.0 Préconditions
- Tag `migration-phase-E`. GO reçu.

### F.1 Tâches

1. **import-linter** — le contrat d'architecture exécutable :
   ```toml
   [tool.importlinter]
   root_package = "jarvis"

   [[tool.importlinter.contracts]]
   name = "Architecture en couches"
   type = "layers"
   layers = [
       "jarvis.interfaces | jarvis.app | jarvis.bootstrap",
       "jarvis.engine",
       "jarvis.providers | jarvis.capabilities | jarvis.analytics | jarvis.hardware",
       "jarvis.kernel",
   ]

   [[tool.importlinter.contracts]]
   name = "Kernel indépendant"
   type = "forbidden"
   source_modules = ["jarvis.kernel"]
   forbidden_modules = ["jarvis.engine", "jarvis.providers", "jarvis.capabilities", "jarvis.interfaces"]
   ```
   Ajouter `lint-imports` aux dev-dependencies, au Makefile (`make lint`), et en **pre-commit hook**.
2. **CI GitHub Actions — deux lanes** : le `ci.yml` existant installe déjà les dépendances lourdes (cmake/openblas pour dlib, portaudio19-dev pour RealtimeSTT, libgl1 pour opencv) et lance `pytest -q` complet — il est FAIT pour la couverture lourde, ne pas la perdre ni la payer à chaque push :
   - **Lane rapide** (chaque push/PR) : `uv sync` → `ruff check` → `lint-imports` → mypy-conformité → `pytest -m "not integration" -q` → snapshot-routes diff. Pas de deps lourdes → rapide.
   - **Lane complète** (push sur `main` + scheduled hebdo) : deps lourdes + `pytest -m integration -q` (vérifier la sélection : `pytest -m integration --collect-only -q` > 0 — les ~13 fichiers lourds doivent être dedans).
   Compléter le `ci.yml` existant, ne pas l'écraser. Rappel §0.5 : les gates [LOCAL] (B8, smoke `--real`) ne sont JAMAIS portés en CI.
3. **Ruff** : activer les règles `TID` (tidy-imports, interdire les imports relatifs au-delà du package) et `I` (isort) dans `pyproject.toml`. Appliquer le reformatage en un commit dédié.

3bis. **Type-checker — rendre les Protocols réellement contraignants.** Sans type-checker, `kernel/contracts.py` est de la documentation, pas un contrat : les Protocols Python sont structurels et ne sont JAMAIS vérifiés au runtime. Attention au piège : `mypy src/jarvis/providers` seul ne prouve PAS la conformité — mypy ne compare les signatures qu'au point d'assignation typée. Mécanisme imposé :
   - Créer `tests/unit/kernel/test_contracts_conformance.py` : une assignation typée explicite **par implémentation** :
     ```python
     from jarvis.kernel.contracts import LLMProvider, MemoryStore, ToolRegistry
     def test_conformance_static() -> None:
         _a: LLMProvider = AnthropicProvider(...)   # mypy compare ici les signatures
         _m: LLMProvider = MistralProvider(...)
         _g: LLMProvider = GeminiProvider(...)
         _o: LLMProvider = OllamaProvider(...)
         _s: MemoryStore = MemoryKernel(...)
         # … une ligne par couple (Protocol, implémentation)
     ```
   - mypy en CI et Makefile, **scopé** : `uv run mypy src/jarvis/kernel tests/unit/kernel/test_contracts_conformance.py` — PAS de mypy strict sur les 46k lignes (chantier séparé, → BACKLOG).
   - Ceinture-bretelles runtime : décorer les Protocols `@runtime_checkable` et ajouter dans `bootstrap.build()` des `assert isinstance(llm, LLMProvider)` (vérifie la présence des méthodes au boot — pas les signatures, d'où la nécessité du point précédent).
4. **Réorganisation des tests** : `tests/unit/` en miroir de `src/jarvis/` (`tests/unit/engine/`, `tests/unit/providers/memory/`, …), `tests/integration/` pour les tests qui touchent disque/réseau/Docker. Marqueurs pytest (`@pytest.mark.integration`) + config : `pytest` seul = unit only, `pytest -m integration` = le reste. Objectif : suite unitaire **< 30 s**.
5. **Hygiène racine et assets** :
   - Supprimer `ui/static/*.old.*` (5 fichiers) — `git rm`.
   - Déplacer `CDC_jarvis_evolution.md`, `INTEGRATION-DONE.md`, ce CDC → `docs/`.
   - Compresser `Favicon.png` (cible < 30 Ko) et `Cover_Jarvis_Github.png` (cible < 300 Ko, ou WebP).
   - `scripts/phase*_real_*.py` → `scripts/validation/`.
   - Fusionner `install.sh` dans `setup.sh` OU documenter leur différence en tête de fichier (DÉCISION : poser la question).
   - README : mettre à jour la section Architecture (nouveau schéma de couches) et le tableau des modules.
6. **Identité** : `jarvis-os` partout (pyproject ✅ en phase B, vérifier README, CLI `--version`, UI footer).
7. **Merge** : PR `refonte/architecture-couches` → `main`, squash interdit (historique des phases conservé), tag final `v0.2.0-architecture`.

### F.2 Auto-vérifications

```bash
# GATE F1 — le contrat de couches passe
uv run lint-imports && echo "GATE F1 ✅"

# GATE F1bis — conformité des implémentations aux Protocols (statique + runtime)
uv run mypy src/jarvis/kernel tests/unit/kernel/test_contracts_conformance.py && echo "GATE F1bis-a ✅"
uv run python -c "from jarvis.bootstrap import build; build()" && echo "GATE F1bis-b ✅ (asserts isinstance au boot)"

# GATE F2 — CI verte sur la branche (vérifier le run GitHub Actions)

# GATE F3 — suite unitaire rapide
time uv run pytest -m "not integration" -q   # < 30 s

# GATE F4 — plus de fichiers morts ni de doc à la racine
ls *.old.* CDC_jarvis_evolution.md INTEGRATION-DONE.md 2>/dev/null ; test $? -ne 0 && echo "GATE F4 ✅"

# GATE F5 — poids des assets
test $(stat -c%s ui/static/favicon.png 2>/dev/null || stat -c%s src/jarvis/interfaces/ui/static/favicon.png) -lt 30720 && echo "GATE F5 ✅"

# GATE F6 — bilan final vs baseline (§1) : refaire toutes les mesures
bash scripts/migration/audit_imports.sh
find src -name "*.py" | xargs wc -l | tail -1
```

### F.3 Critères de validation humaine (STOP FINAL)
- Revue de la PR complète.
- Session d'utilisation réelle de 30 min (chat, voix si dispo, mission, proactif, Telegram).
- Comparer le rapport final à la baseline §1 : imports différés 251 → < 15 annotés ; cycles 4 → 0 ; anomalie tools→api → résolue ; chemins en dur 23+76 → 0 hors `kernel/paths.py` ; imports dynamiques de l'ancien namespace → 0 ; contrat de couches + conformité des Protocols actifs en CI ; routes byte-identiques à la baseline ; état des données identique à la baseline (faits, tokens, 8 skills, faces) ; les DEUX process (API + voix) composent via `bootstrap.build()` ; install à froid verte (B9 rejoué sur l'état final) ; deux lanes CI actives.
- Merge + tag `v0.2.0-architecture`.

---

## 9. Hors périmètre (explicitement)

Pour éviter toute dérive de scope, ce CDC NE couvre PAS :
- La réécriture du front (ES modules pour `capabilities.js` / `macropad_2k.js`) → CDC ultérieur.
- Tout changement fonctionnel, optimisation de prompt, ou évolution du Mission Engine.
- La question de la licence et du positionnement open source.
- Le typage strict généralisé du codebase (mypy strict sur 46k lignes) — seul le périmètre kernel + conformité des Protocols est couvert (F.3bis).
- Le retrait des shims racine `main.py`/`voice_agent.py` (conservés une version pour les appelants externes ; le CLI en est découplé dès B) → BACKLOG.
- Le retrait de l'alias ABI skills — contrat permanent documenté, pas un résidu de migration (B.2bis).
- Git LFS / réécriture d'historique pour les gros binaires (les compressions de F.1.5 ne nettoient que le futur).
- Le déplacement éventuel de `skills/installed/` hors package SI la décision B.4-Q2 le reporte.

## 10. Récapitulatif des décisions à prendre par Barth

| ID | Question | Phase | Recommandation |
|---|---|---|---|
| Q1 | Fichiers de config YAML/JSON : données racine ou code package ? | B | Données à la racine, loaders dans kernel |
| Q2 | `skills/installed/` dans le package ou en données utilisateur ? | B | Données utilisateur (`skills_data/`) |
| Q3 | Découpage proposé de `http_config.py` | E | Validé sur mini-rapport intermédiaire |
| Q4 | `install.sh` vs `setup.sh` : fusion ou doc ? | F | Fusion dans `setup.sh` |

---

*Fin du CDC. Claude Code : commence par lire l'intégralité du document, confirme ta compréhension du protocole §0, pose les questions Q1/Q2 si la Phase B approche, puis attends « GO PHASE A ».*
