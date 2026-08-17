# api.py

- **Layer:** L1
- **Path:** `src/jarvis/providers/llm/api.py`
- **Purpose:** Module `providers/llm/api.py`.
- **Key symbols:** Classes: `AnthropicProvider`, `MistralProvider`, `GeminiProvider`, `OpenAIProvider`; Functions: `_is_retryable_anthropic`, `_claude_tools_to_openai`, `_messages_to_openai`, `_anthropic_extract_text`, `get_api_provider`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/providers/llm/api.py](../../src/jarvis/providers/llm/api.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [overview](../overview.md)
- [architecture-layers](../../00-meta/architecture-layers.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../02-kernel/bundle-offline.md)
- [process-map](../../maps/process-map.md)
- [env-reference](../../07-config/env-reference.md)
- [run-flow](../../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
