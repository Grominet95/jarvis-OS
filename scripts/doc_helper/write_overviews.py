#!/usr/bin/env python3
"""Write Documentation_Helper overview and flow docs (non-module-card files)."""
import re
from pathlib import Path

DOC = Path("Documentation_Helper")
TODAY = "2026-08-13"

def w(rel: str, content: str) -> None:
    p = DOC / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.strip() + "\n", encoding="utf-8")

w("00-meta/project-overview.md", f"""# Project Overview

Jarvis OS (v0.3.2) is a personal AI assistant with real-time voice (LiveKit), text chat, proactive briefings, mission/projects orchestration, memory, tools, and skills.

## Repository layout

| Path | Role |
|------|------|
| `src/jarvis/` | Python package (~223 modules) |
| `jarvis.ps1` / `jarvis` | Windows / Unix launchers |
| `setup.ps1` / `setup.sh` | Environment bootstrap |
| `bundle/` | Offline Python venv + binaries (gitignored, CDN download) |
| `config/` | Runtime YAML, approvals, OAuth token files |
| `memory_data/` | Local memory JSONL stores |
| `docs/` | Long-form architecture docs |
| `notices/` | Feature-specific deep dives |
| `prompts/` | System prompts |

## Entry points

- **Setup wizard:** `jarvis.setup_app` on port 8765
- **Main API:** `jarvis.app` (FastAPI, default `:8000`)
- **Voice agent:** `jarvis.interfaces.voice.agent` (LiveKit worker)
- **Composition root:** `src/jarvis/bootstrap.py` → `build()`

## Cross-links

- Architecture CDC: [docs/architecture/CDC_refonte_architecture.md](../../docs/architecture/CDC_refonte_architecture.md)
- Skills ABI: [docs/architecture/skills-abi.md](../../docs/architecture/skills-abi.md)
- README: [README.md](../../README.md)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("00-meta/architecture-layers.md", f"""# Architecture Layers (L0–L3)

Jarvis follows a strict layered architecture enforced by import-linter contracts.

## Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| **L0** | `jarvis.kernel` | Settings, paths, events, permissions, bundle, no business logic |
| **L1** | `jarvis.providers`, `jarvis.capabilities` | LLM, memory, audio, vision; tools and skills |
| **L2** | `jarvis.engine` | Gateway, agent, sessions, missions, proactive, background workers |
| **L3** | `jarvis.interfaces` | FastAPI routers, UI static files, voice LiveKit, messaging channels |

## Rules

- L3 may import L2/L1/L0; L2 may import L1/L0; L1 may import L0 only.
- **Single composition root:** `bootstrap.build()` wires the object graph synchronously (no network during construction).
- Async tasks (reindex, scheduler, proactive engine) start in `app.py` lifespan or voice agent, not in `build()`.

## Source of truth

- [docs/architecture/CDC_refonte_architecture.md](../../docs/architecture/CDC_refonte_architecture.md)
- [src/jarvis/bootstrap.py](../../src/jarvis/bootstrap.py)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("00-meta/bootstrap-wiring.md", f"""# Bootstrap Wiring

`bootstrap.build()` is the **unique composition root** for Jarvis object graph construction.

## Construction order

```
settings → bus → providers → capabilities → engine
```

## Key wired objects (~30+)

- **Kernel:** `Settings`, `EventBus`
- **Providers:** `MemoryKernel`, `MemoryIngest`, `FTSIndex`, `VectorIndex`, `MemoryMirror`, `UserModel`, LLM via factory, TTS engine
- **Capabilities:** `ToolRegistry` (weather, calendar, gmail, memory tools, skills tools, …), `SkillLifecycle`, `SkillLab`, `SkillSynthesizer`
- **Engine:** `Gateway`, `Agent`, `SessionManager`, `BudgetGuard`, `ApprovalChecker`, `ProjectOrchestrator`, `ProactiveEngine`, `BackgroundWorker`, `Scheduler`, `CommandCenter`, `Curator`

## Container

`bootstrap.Container` dataclass holds all references returned by `build()`. Both `app.py` and `interfaces/voice/agent.py` should use the same container (migration in progress per CDC).

## Constraints

- `build()` is **synchronous** — no async tasks started inside.
- **Gate C6:** no outbound HTTP during construction (LLM clients instantiated but not called).

## Related

- Module card: [06-interfaces/bootstrap.md](../06-interfaces/bootstrap.md)
- Flow: [maps/process-map.md](../maps/process-map.md)

- **Source of truth:** [src/jarvis/bootstrap.py](../../src/jarvis/bootstrap.py)
- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("00-meta/glossary.md", f"""# Glossary

| Term | Meaning |
|------|---------|
| **Gateway** | Central request router; chat/voice/tools flow through `engine.gateway.Gateway` |
| **Agent** | LLM loop with tool execution (`engine.agent.Agent`) |
| **Mission** | Multi-step project orchestration (`engine.mission`) |
| **Proactive** | Scheduled briefings, initiatives, curator (`engine.proactive`) |
| **Memory kernel** | Core memory read/write API (`providers.memory.kernel`) |
| **Ingest** | Pipeline writing conversation facts to memory stores |
| **Mirror** | Cross-session memory reflection layer |
| **Tool** | Registered callable capability (`capabilities.tools`) |
| **Skill** | Installable UI/logic package (`capabilities.skills`) |
| **Bundle** | Offline CDN-delivered Python venv + LiveKit binary |
| **Setup app** | First-run wizard (`setup_app`, port 8765) |
| **LiveKit** | Real-time voice WebRTC stack for voice agent |

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("maps/process-map.md", f"""# Process Map — Setup, Run, Voice, Chat

## Setup flow

```mermaid
flowchart TD
  clone[git clone] --> setupCmd[jarvis.ps1 setup]
  setupCmd --> onedrive[onedrive_guard.ps1]
  onedrive --> dlBundle[download_bundle.ps1 CDN]
  dlBundle --> rehome[rehome_bundle.ps1]
  rehome --> setupApp[jarvis.setup_app :8765]
  setupApp --> wizard[setup.html + setup_wizard API]
  wizard --> envFile[.env SETUP_COMPLETE]
```

**Files (order):** `jarvis.ps1` → `scripts/onedrive_guard.ps1` → `scripts/download_bundle.ps1` → `scripts/release/rehome_bundle.ps1` → `jarvis.setup_app` → `interfaces/ui/static/setup.html` → `interfaces/api/setup_wizard.py`

**Failure modes:** OneDrive install path blocked; bundle missing; port 8765 in use. See [09-operations/troubleshooting.md](../09-operations/troubleshooting.md).

## Run flow

```mermaid
flowchart TD
  runCmd[jarvis.ps1 run] --> bundleCheck[Require-JarvisBundle]
  bundleCheck --> lk[livekit-server :7880]
  bundleCheck --> api[jarvis.app :PORT]
  bundleCheck --> voice[voice.agent dev]
  voice --> gateway[Gateway shared graph]
  api --> gateway
```

**Files:** `jarvis.ps1`, `jarvis.app`, `interfaces/voice/agent.py`, `bootstrap.py`

## Voice pipeline (LiveKit)

```mermaid
flowchart LR
  mic[Browser mic] --> lkRoom[LiveKit room]
  lkRoom --> agent[voice/agent.py]
  agent --> stt[STT provider]
  stt --> llm[LLM provider]
  llm --> tts[TTS ElevenLabs/etc]
  tts --> lkRoom
  agent --> gw[Gateway tools/memory]
```

See [06-interfaces/voice-livekit.md](../06-interfaces/voice-livekit.md).

## Chat flow

```mermaid
flowchart LR
  ui[home.html / command.html] --> api[POST /api/chat or WS]
  api --> gw[Gateway]
  gw --> agent[Agent + tools]
  agent --> mem[Memory ingest]
```

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# dependency-versions from pyproject

pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
deps = re.findall(r'"([^"]+>=[^"]+)"', pyproject)
w("00-meta/dependency-versions.md", f"""# Dependency Versions

Pinned summary from `pyproject.toml` (jarvis-os 0.3.2, Python >=3.11,<3.14).

## Core runtime

{chr(10).join('- `' + d + '`' for d in deps[:20])}

## Optional

- `face-recognition>=1.3.0` (vision extra)
- `pytest`, `pytest-asyncio`, `ruff` (dev extra)

## Source of truth

[pyproject.toml](../../pyproject.toml)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# env-reference from .env.example
env_lines = Path(".env.example").read_text(encoding="utf-8").splitlines()
groups: list[tuple[str, list[str]]] = []
current = "General"
buf: list[str] = []
for line in env_lines:
    if line.startswith("# ──"):
        if buf:
            groups.append((current, buf))
            buf = []
        # Deshabille un titre de section "# ── Titre ────" : on retire les
        # caracteres de decoration en tete et en queue, pas une sous-chaine.
        current = re.sub(r"^[#\s\u2500]+|[#\s\u2500]+$", "", line)
    elif line.strip() and not line.strip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        buf.append(f"- `{key}`")
if buf:
    groups.append((current, buf))
env_md = ["# Environment Reference", "", "Full `.env.example` grouped by section. Never commit real `.env`.", ""]
for title, keys in groups:
    if keys:
        env_md.append(f"## {title}")
        env_md.append("")
        env_md.extend(keys)
        env_md.append("")
env_md.append("- **Source of truth:** [.env.example](../../.env.example)")
env_md.append(f"- **Last reviewed:** {TODAY} (jarvis-os @ local)")
w("07-config/env-reference.md", "\n".join(env_md))

w("07-config/runtime-config-files.md", f"""# Runtime Config Files

| File | Purpose |
|------|---------|
| `config/tools.yaml` | Tool whitelist for mission capability engine |
| `config/approvals.json` | Approval categories and policies |
| `config/google_credentials.json` | OAuth client (generated from .env) |
| `config/google_*_token.json` | Gmail/Calendar tokens |
| `config/spotify_token.json` | Spotify OAuth token |
| `config/permissions.yaml` | Permission toggles (if present) |

Paths resolved via `kernel.paths.CONFIG_DIR`.

- **Source of truth:** [src/jarvis/kernel/paths.py](../../src/jarvis/kernel/paths.py)
- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# 01-entry-points
w("01-entry-points/windows-launchers.md", f"""# Windows Launchers

## jarvis.ps1

Main Windows entry point. Commands: `setup`, `run`, `stop`, `doctor`, etc.

- Uses `bundle/.venv/Scripts/python.exe` when present, else `.venv`, else `uv run`
- Sources `scripts/onedrive_guard.ps1` and `scripts/download_bundle.ps1`
- `Require-JarvisBundle` blocks `run` without bundle or dev venv
- `Invoke-JarvisRun` starts LiveKit (:7880), API (`jarvis.app`), voice agent

## Related scripts

| Script | Role |
|--------|------|
| `scripts/download_bundle.ps1` | CDN bundle download (techalchemy.fr) |
| `scripts/release/rehome_bundle.ps1` | Fix venv paths after bundle extract |
| `scripts/onedrive_guard.ps1` | Block or relocate OneDrive installs |
| `setup.ps1` | Bundle-only Python setup helper |

- **Source of truth:** [jarvis.ps1](../../jarvis.ps1)
- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("01-entry-points/unix-launchers.md", f"""# Unix Launchers

## jarvis (shell)

POSIX launcher mirroring Windows commands where applicable.

## setup.sh / Makefile

Bootstrap dependencies and optional bundle paths for Linux/macOS dev.

- **Source of truth:** [jarvis](../../jarvis), [setup.sh](../../setup.sh), [Makefile](../../Makefile)
- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("01-entry-points/setup-flow.md", rf"""# Setup Flow

## Trigger

User runs `.\jarvis.ps1 setup` (or equivalent) after clone.

## Sequence

1. OneDrive guard check
2. Download bundle from CDN if missing (`download_bundle.ps1`)
3. Rehome bundle venv (`rehome_bundle.ps1`)
4. Start `jarvis.setup_app` on port **8765**
5. Browser opens `setup.html` wizard
6. Wizard writes `.env` with `SETUP_COMPLETE=true`

## Key modules

- `kernel/bundle_download.py` — CDN URL constants
- `interfaces/api/setup_wizard.py` — setup API
- `interfaces/ui/static/setup.html`, `setup.js`

See [maps/process-map.md](../maps/process-map.md).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("01-entry-points/run-flow.md", f"""# Run Flow

## Trigger

`.\\jarvis.ps1 run` after setup complete.

## Sequence

1. `Require-JarvisBundle` — bundle or dev `.venv` required
2. `jarvis.kernel.preflight` — validate env, ports, native deps
3. Start **livekit-server** (:7880 dev keys)
4. Start **jarvis.app** (PORT from .env, default 8000)
5. Start **jarvis.interfaces.voice.agent dev**
6. Open browser to home UI

Logs: `%TEMP%\\jarvis\\*.log`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("01-entry-points/docker.md", f"""# Docker

Dockerfile and `entrypoint.sh` run Jarvis in a containerized environment.

Use for deployment; local dev typically uses `jarvis.ps1 run`.

- **Source of truth:** [Dockerfile](../../Dockerfile), [entrypoint.sh](../../entrypoint.sh)
- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# 02-kernel deep docs
kernel_modules = [
    "settings.py", "paths.py", "events.py", "bundle.py", "bundle_download.py",
    "approval.py", "approvals.py", "permissions.py", "preflight.py", "connectivity.py",
    "contracts.py", "errors.py", "file_lock.py", "notifications.py", "schemas.py",
    "setup_layout.py", "vocab.py", "backends.py", "__init__.py",
]
w("02-kernel/overview.md", f"""# Kernel Overview (L0)

19 modules under `src/jarvis/kernel/`. No business logic — settings, paths, events, bundle, permissions.

## Module cards

{chr(10).join(f'- [modules/{m.replace(".py","")}.md](modules/{m.replace(".py","")}.md)' for m in kernel_modules)}

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

for topic, fname, desc in [
    ("Settings and Environment", "settings-and-env.md", "`settings.py` — Pydantic Settings loading `.env`, all env keys typed."),
    ("Paths and Layout", "paths-and-layout.md", "`paths.py` — PROJECT_ROOT, CONFIG_DIR, memory paths, bundle paths."),
    ("Events Bus", "events-bus.md", "`events.py` — EventBus, typed events (MemoryIngested, MissionCompleted, …)."),
    ("Bundle Offline", "bundle-offline.md", "`bundle.py`, `bundle_download.py` — offline venv and CDN download."),
    ("Permissions and Approvals", "permissions-approvals.md", "`permissions.py`, `approval.py`, `approvals.py` — tool approval flow."),
]:
    w(f"02-kernel/{fname}", f"""# {topic}

{desc}

See module cards in [modules/](modules/) for per-file detail.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# providers
w("03-providers/overview.md", f"""# Providers Overview (L1)

External and local service adapters: LLM, memory, audio, vision.

## Subsystems

- [llm/](llm/) — API/local LLM factory
- [memory/](memory/) — ingest, kernel, retrieval, mirror, search
- [audio/](audio/) — STT, TTS, clap detector, ElevenLabs
- [vision/](vision/) — object detection, face recognition, daemon

Cross-link: [notices/memory-recall.md](../../notices/memory-recall.md)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("03-providers/memory/memory-flow.md", f"""# Memory Pipeline Flow

```mermaid
flowchart LR
  chat[Chat/Voice] --> ingest[MemoryIngest]
  ingest --> kernel[MemoryKernel]
  kernel --> topics[TopicStore]
  kernel --> sessions[SessionStore]
  ingest --> fts[FTSIndex]
  ingest --> vec[VectorIndex]
  recall[CrossSessionRecall] --> mirror[MemoryMirror]
  tools[Memory tools] --> retrieval[retrieval.py]
```

## Files (order)

1. `providers/memory/ingest.py`
2. `providers/memory/kernel.py`
3. `providers/memory/index.py`, `search.py`
4. `providers/memory/mirror.py`, `retrieval.py`
5. `capabilities/tools/memory.py`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# capabilities
w("04-capabilities/tools-overview.md", f"""# Tools Overview

Agent-callable tools registered in `ToolRegistry`. Whitelist in `config/tools.yaml` for missions.

See [tools/](tools/) module cards and [tools-registry.md](tools-registry.md).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("04-capabilities/tools-registry.md", f"""# Tools Registry

- **Registry:** `capabilities/tools/registry.py` — registers all tools at bootstrap
- **Whitelist:** `engine/mission/capability_engine.py` + `config/tools.yaml`
- **Execute API:** `POST /api/tools/execute`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("04-capabilities/skills/abi.md", f"""# Skills ABI

Installable skill packages with UI views and lifecycle hooks.

Full spec: [docs/architecture/skills-abi.md](../../../docs/architecture/skills-abi.md)

Module cards: `_abi_compat.py`, `_loader.py`, `_registry.py`, `registry.py`, `lifecycle.py`, `installer.py`, `lab.py`.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

for sk in ["registry", "lifecycle", "lab", "installer", "synthesizer", "standard"]:
    if not (DOC / f"04-capabilities/skills/{sk}.md").exists():
        w(f"04-capabilities/skills/{sk}-overview.md", f"# Skills — {sk}\n\nSee module card if generated.\n\n- **Last reviewed:** {TODAY}\n")

# engine
w("05-engine/overview.md", f"""# Engine Overview (L2)

Core runtime: gateway, agent, sessions, budget, missions, proactive, background workers.

- [gateway-and-agent.md](gateway-and-agent.md)
- [session-budget-auth.md](session-budget-auth.md)
- [mission/](mission/)
- [proactive/](proactive/)
- [background/](background/)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/gateway-and-agent.md", f"""# Gateway and Agent

**Gateway** (`engine/gateway.py`) routes chat/voice requests, attaches memory context, invokes **Agent** (`engine/agent.py`) for LLM + tool loops.

Shared between API and voice agent via bootstrap Container.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/session-budget-auth.md", f"""# Session, Budget, Auth

- **SessionManager** — conversation sessions, persistence
- **BudgetGuard** — token/cost limits, emits `BudgetThresholdReached`
- **API auth** — `API_AUTH_ENABLED`, `API_TOKEN` in .env

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/mission/overview.md", f"""# Mission / Projects

Multi-step project orchestration: `ProjectOrchestrator`, backends (local/docker/remote), capability engine.

See [notices/exec-backends.md](../../../notices/exec-backends.md).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/mission/backends.md", f"""# Mission Backends

- `backends/base.py`, `local.py`, `remote.py`
- `docker_executor.py`, `backend_factory.py`

Cross-link: [notices/exec-backends.md](../../../notices/exec-backends.md)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/proactive/overview.md", f"""# Proactive Engine

Briefings, initiatives, curator scans, command center snapshot.

Collectors: email, Home Assistant, jarvis internal.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("05-engine/background/overview.md", f"""# Background Workers

`BackgroundWorker`, `Scheduler`, notification queues, routines.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# interfaces
w("06-interfaces/overview.md", f"""# Interfaces Overview (L3)

FastAPI app, UI static files, voice LiveKit worker, messaging channels.

- [api/](api/) — REST routers
- [voice-livekit.md](voice-livekit.md)
- [channels-messaging.md](channels-messaging.md)
- [ui/](ui/)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("06-interfaces/voice-livekit.md", f"""# Voice LiveKit Pipeline

Process: `python -m jarvis.interfaces.voice.agent dev`

## Stack

- LiveKit room + browser client (`voice_livekit.js`)
- STT: Deepgram / OpenAI / Google (`STT_PROVIDER`)
- LLM: follows `API_BACKEND` / `VOICE_LLM_MODEL`
- TTS: ElevenLabs plugin or fallbacks

## Env keys

`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY`, `ELEVENLABS_*`

## Source of truth

[src/jarvis/interfaces/voice/agent.py](../../src/jarvis/interfaces/voice/agent.py)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("06-interfaces/channels-messaging.md", f"""# Channels and Messaging

Telegram, Discord, WhatsApp, Signal via `interfaces/channels/`. Unified gateway when `MESSAGING_GATEWAY_ENABLED=true`.

Cross-link: [notices/messaging-gateway.md](../../notices/messaging-gateway.md)

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

ui_pages = [
    ("home", "Main voice/chat home"),
    ("index", "Landing redirect"),
    ("settings", "Mission Control settings"),
    ("setup", "First-run wizard"),
    ("dashboard", "Analytics dashboard"),
    ("command", "Command center UI"),
    ("capabilities", "Capabilities manager"),
    ("admin", "Admin panel"),
]
for page, desc in ui_pages:
    w(f"06-interfaces/ui/{page}.md", f"""# UI — {page}

{desc}. Static: `interfaces/ui/static/{page}.html` (+ `.js`, `.css`).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("06-interfaces/api/overview.md", f"""# API Routers Overview

Aggregated in `interfaces/api/http.py`:

ui, logs, system, sessions, memory, skills, config, proactive, vision, chat, analytics.

Additional routers mounted in `app.py`: budget, briefing, music, spotify, projects, routines, globe, macropad, google_oauth, websocket, channels, admin.

See [maps/route-map.md](../../maps/route-map.md).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# integrations
sheets = [
    ("livekit", "LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET", "voice/agent.py"),
    ("deepgram", "DEEPGRAM_API_KEY", "STT LiveKit plugin"),
    ("elevenlabs", "ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID", "TTS + LiveKit plugin"),
    ("anthropic", "ANTHROPIC_API_KEY, ANTHROPIC_MODEL", "LLM api backend"),
    ("openai", "OPENAI_API_KEY", "LLM / STT / Whisper"),
    ("google", "GOOGLE_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET", "Gemini, Calendar, Gmail"),
    ("spotify", "SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET", "Music provider"),
    ("deezer", "DEEZER_APP_ID, DEEZER_APP_SECRET", "Music provider"),
    ("notion", "NOTION_TOKEN, NOTION_PAGE_ID", "Notion tasks tool"),
    ("telegram", "TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID", "Mobile channel"),
    ("discord", "DISCORD_BOT_TOKEN, DISCORD_OWNER_ID", "Discord channel"),
    ("mapbox", "MAPBOX_TOKEN, MAPTILER_KEY", "Globe / maps"),
]
index_rows = ["| Service | Env keys | Module |", "|---------|----------|--------|"]
for name, keys, mod in sheets:
    w(f"08-integrations/sheets/{name}.md", f"""# Integration — {name.title()}

**Env keys:** {keys}

**Primary module:** {mod}

Configure via `.env` or Mission Control → Capacities.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")
    index_rows.append(f"| {name.title()} | {keys} | {mod} |")

w("08-integrations/index.md", f"""# Integrations Index

{chr(10).join(index_rows)}

Sheets in [sheets/](sheets/).

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# operations
w("09-operations/troubleshooting.md", f"""# Troubleshooting

## Bundle missing

**Symptom:** `Bundle offline absent` on run.

**Fix:** Run `.\\jarvis.ps1 setup` to download CDN bundle.

## OneDrive install

**Symptom:** Guard blocks setup from OneDrive path.

**Fix:** Move repo to local disk or accept auto-relocate prompt.

## LIVEKIT_URL / voice fails

**Symptom:** Voice agent cannot connect.

**Fix:** Set `LIVEKIT_URL`, keys in `.env`. For local dev, `jarvis.ps1 run` starts embedded livekit-server on :7880.

## API timeout on run

**Symptom:** API health check fails after 90s.

**Fix:** Read `%TEMP%\\jarvis\\api.log`. Common: missing native dep, invalid .env, port in use. Run `python -m jarvis.kernel.preflight`.

## pyvenv / bundle path broken

**Fix:** Run `scripts/release/rehome_bundle.ps1`.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("09-operations/logs-and-doctor.md", f"""# Logs and Doctor

## Log locations (Windows run)

`%TEMP%\\jarvis\\livekit.log`, `api.log`, `voice.log`

## Doctor

`.\\jarvis.ps1 doctor` — environment diagnostics.

## Preflight

`python -m jarvis.kernel.preflight` — runs before API start on `run`.

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("09-operations/release-and-bundle.md", f"""# Release and Bundle

CDN bundle build and release process.

Cross-link: [RELEASING.md](../../RELEASING.md)

Scripts: `scripts/release/`, `scripts/download_bundle.ps1`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

# testing
w("10-testing/pytest-and-ci.md", f"""# Pytest and CI

Tests under `tests/`. Dev deps: pytest, pytest-asyncio, ruff.

Run: `uv run pytest` or bundle python `-m pytest`

CI: GitHub Actions workflows in `.github/workflows/`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

w("10-testing/validation-scripts.md", f"""# Validation Scripts

- `scripts/migration/snapshot_routes.py` — route snapshot vs baseline
- `scripts/migration/routes.baseline.txt` — expected API surface
- Import-linter contracts in `pyproject.toml`

- **Last reviewed:** {TODAY} (jarvis-os @ local)
""")

print("all overviews written")
