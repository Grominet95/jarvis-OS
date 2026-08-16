# agent.py

- **Layer:** L3
- **Path:** `src/jarvis/interfaces/voice/agent.py`
- **Purpose:** Jarvis Voice Agent — LiveKit Agents pipeline vocal.
- **Key symbols:** Classes: `_ProxyMemoryTool`, `JarvisVoiceAgent`; Functions: `_voice_system_base`, `_build_voice_instructions`, `_now_context`, `_load_user_profile`, `_dynamic_context`, `_make_livekit_tool`, `_voice_broadcast`, `_call_api_memory_tool`, `_build_voice_tools`, `prewarm`, `_build_voice_stt`, `_build_voice_elevenlabs`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/interfaces/voice/agent.py](../../src/jarvis/interfaces/voice/agent.py)

## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [overview](./overview.md)
- [route-map](../maps/route-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
