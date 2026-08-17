# Project Overview

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


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [architecture-layers](./architecture-layers.md)
- [bootstrap-wiring](./bootstrap-wiring.md)
- [process-map](../maps/process-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
