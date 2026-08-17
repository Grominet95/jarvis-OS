# Documentation_Helper — Master Index

Local AI knowledge base for Jarvis OS v0.3.2. Start here; see [AI_INSTRUCTIONS.md](AI_INSTRUCTIONS.md) for navigation rules.

## Quick lookup by question

| How do I…? | Doc |
|------------|-----|
| Install from clone | [01-entry-points/setup-flow.md](01-entry-points/setup-flow.md) |
| Start Jarvis | [01-entry-points/run-flow.md](01-entry-points/run-flow.md) |
| Fix bundle / OneDrive errors | [09-operations/troubleshooting.md](09-operations/troubleshooting.md) |
| Terminal `[JRV-...]` code | [09-operations/error-codes.md](09-operations/error-codes.md) |
| Contribuer un code erreur | [09-operations/error-codes-contributor-guide.md](09-operations/error-codes-contributor-guide.md) |
| Configure env vars | [07-config/env-reference.md](07-config/env-reference.md) |
| Find an API route | [maps/route-map.md](maps/route-map.md) |
| Understand voice/LiveKit | [06-interfaces/voice-livekit.md](06-interfaces/voice-livekit.md) |
| Trace memory pipeline | [03-providers/memory/memory-flow.md](03-providers/memory/memory-flow.md) |
| Add / debug a tool | [04-capabilities/tools-registry.md](04-capabilities/tools-registry.md) |
| Mission / project flow | [05-engine/mission/overview.md](05-engine/mission/overview.md) |
| External service keys | [08-integrations/index.md](08-integrations/index.md) |

| What is…? | Doc |
|-----------|-----|
| Architecture layers L0–L3 | [00-meta/architecture-layers.md](00-meta/architecture-layers.md) |
| Bootstrap object graph | [00-meta/bootstrap-wiring.md](00-meta/bootstrap-wiring.md) |
| Gateway / Agent | [05-engine/gateway-and-agent.md](05-engine/gateway-and-agent.md) |
| Skills ABI | [04-capabilities/skills/abi.md](04-capabilities/skills/abi.md) |

| Where is…? | Doc |
|------------|-----|
| Python module → doc | [maps/file-to-doc.yaml](maps/file-to-doc.yaml) |
| UI page | [06-interfaces/ui/](06-interfaces/ui/) |
| Kernel module | [02-kernel/modules/](02-kernel/modules/) |

## Section tree

### Meta
- [00-meta/project-overview.md](00-meta/project-overview.md)
- [00-meta/architecture-layers.md](00-meta/architecture-layers.md)
- [00-meta/bootstrap-wiring.md](00-meta/bootstrap-wiring.md)
- [00-meta/dependency-versions.md](00-meta/dependency-versions.md)
- [00-meta/glossary.md](00-meta/glossary.md)

### Entry points
- [01-entry-points/windows-launchers.md](01-entry-points/windows-launchers.md)
- [01-entry-points/unix-launchers.md](01-entry-points/unix-launchers.md)
- [01-entry-points/setup-flow.md](01-entry-points/setup-flow.md)
- [01-entry-points/run-flow.md](01-entry-points/run-flow.md)
- [01-entry-points/docker.md](01-entry-points/docker.md)

### Kernel (L0)
- [02-kernel/overview.md](02-kernel/overview.md)
- [02-kernel/settings-and-env.md](02-kernel/settings-and-env.md)
- [02-kernel/paths-and-layout.md](02-kernel/paths-and-layout.md)
- [02-kernel/events-bus.md](02-kernel/events-bus.md)
- [02-kernel/bundle-offline.md](02-kernel/bundle-offline.md)
- [02-kernel/permissions-approvals.md](02-kernel/permissions-approvals.md)
- [02-kernel/modules/](02-kernel/modules/) — 19 module cards

### Providers (L1)
- [03-providers/overview.md](03-providers/overview.md)
- [03-providers/llm/](03-providers/llm/)
- [03-providers/memory/](03-providers/memory/) + [memory-flow.md](03-providers/memory/memory-flow.md)
- [03-providers/audio/](03-providers/audio/)
- [03-providers/vision/](03-providers/vision/)

### Capabilities (L1)
- [04-capabilities/tools-overview.md](04-capabilities/tools-overview.md)
- [04-capabilities/tools-registry.md](04-capabilities/tools-registry.md)
- [04-capabilities/tools/](04-capabilities/tools/)
- [04-capabilities/skills/](04-capabilities/skills/)

### Engine (L2)
- [05-engine/overview.md](05-engine/overview.md)
- [05-engine/gateway-and-agent.md](05-engine/gateway-and-agent.md)
- [05-engine/session-budget-auth.md](05-engine/session-budget-auth.md)
- [05-engine/mission/](05-engine/mission/)
- [05-engine/proactive/](05-engine/proactive/)
- [05-engine/background/](05-engine/background/)

### Interfaces (L3)
- [06-interfaces/overview.md](06-interfaces/overview.md)
- [06-interfaces/api/overview.md](06-interfaces/api/overview.md)
- [06-interfaces/voice-livekit.md](06-interfaces/voice-livekit.md)
- [06-interfaces/channels-messaging.md](06-interfaces/channels-messaging.md)
- [06-interfaces/ui/](06-interfaces/ui/)

### Config
- [07-config/env-reference.md](07-config/env-reference.md)
- [07-config/runtime-config-files.md](07-config/runtime-config-files.md)

### Integrations
- [08-integrations/index.md](08-integrations/index.md)
- [08-integrations/sheets/](08-integrations/sheets/)

### Operations
- [09-operations/error-codes.md](09-operations/error-codes.md)
- [09-operations/error-codes-sqlite.md](09-operations/error-codes-sqlite.md)
- [09-operations/error-codes-contributor-guide.md](09-operations/error-codes-contributor-guide.md)
- [00-meta/error-codes-ai-instructions.md](00-meta/error-codes-ai-instructions.md)
- [00-meta/error-collector-guide.md](00-meta/error-collector-guide.md)
- [09-operations/troubleshooting.md](09-operations/troubleshooting.md)
- [09-operations/logs-and-doctor.md](09-operations/logs-and-doctor.md)
- [09-operations/release-and-bundle.md](09-operations/release-and-bundle.md)

### Testing
- [10-testing/pytest-and-ci.md](10-testing/pytest-and-ci.md)
- [10-testing/validation-scripts.md](10-testing/validation-scripts.md)

### Maps
- [maps/file-to-doc.yaml](maps/file-to-doc.yaml) — 223 Python files
- [maps/route-map.md](maps/route-map.md) — 194 routes
- [maps/process-map.md](maps/process-map.md)

## Keyword search (FR / EN, typos OK)

Use the FTS index: `npm run query -- "ta question"` from `scripts/doc_helper/`.

| Keywords (FR / EN) | Doc |
|--------------------|-----|
| install, setup, instaler, configuration | [01-entry-points/setup-flow.md](01-entry-points/setup-flow.md) |
| run, demarrer, lancer, start | [01-entry-points/run-flow.md](01-entry-points/run-flow.md) |
| voix, voice, micro, livekit, vocal | [06-interfaces/voice-livekit.md](06-interfaces/voice-livekit.md) |
| memoire, memory, rappel, recall | [03-providers/memory/memory-flow.md](03-providers/memory/memory-flow.md) |
| erreur, bug, probleme, fix, JRV, code erreur | [09-operations/error-codes.md](09-operations/error-codes.md) |
| env, cle, token, .env, config | [07-config/env-reference.md](07-config/env-reference.md) |
| api, route, endpoint | [maps/route-map.md](maps/route-map.md) |
| outil, tool, skill, competence | [04-capabilities/tools-registry.md](04-capabilities/tools-registry.md) |
| mission, projet, project | [05-engine/mission/overview.md](05-engine/mission/overview.md) |
| telegram, discord, message | [06-interfaces/channels-messaging.md](06-interfaces/channels-messaging.md) |
| musique, spotify, deezer | [08-integrations/index.md](08-integrations/index.md) |
| docker, sandbox | [05-engine/mission/backends.md](05-engine/mission/backends.md) |
| log, doctor, preflight | [09-operations/logs-and-doctor.md](09-operations/logs-and-doctor.md) |

Rebuild index: `npm run build-index` · Query ~1k tokens: `npm run query -- --max-tokens 1000 "question"`

## Maintenance

[MAINTENANCE.md](MAINTENANCE.md) | Regenerate cards: `python scripts/doc_helper/generate_module_cards.py`

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
