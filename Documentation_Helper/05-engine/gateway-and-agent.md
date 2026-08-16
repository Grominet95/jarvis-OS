# Gateway and Agent

**Gateway** (`engine/gateway.py`) routes chat/voice requests, attaches memory context, invokes **Agent** (`engine/agent.py`) for LLM + tool loops.

Shared between API and voice agent via bootstrap Container.


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [overview](./overview.md)
- [bootstrap-wiring](../00-meta/bootstrap-wiring.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
