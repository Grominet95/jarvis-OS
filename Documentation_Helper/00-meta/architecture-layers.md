# Architecture Layers (L0–L3)

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


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [bootstrap-wiring](./bootstrap-wiring.md)
- [process-map](../maps/process-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
