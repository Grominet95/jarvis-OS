# Glossary

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
