# Bootstrap Wiring

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

## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [architecture-layers](./architecture-layers.md)
- [process-map](../maps/process-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
