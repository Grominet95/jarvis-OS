# ingest.py

- **Layer:** L1
- **Path:** `src/jarvis/providers/memory/ingest.py`
- **Purpose:** Pipeline d'ingestion : event → facts via LLM + réconciliation (CDC §6.4–§6.6).
- **Key symbols:** Classes: `IngestResult`, `MemoryIngest`, `_Candidate`, `_Outcome`, `_ArbiterVerdict`; Functions: `_build_prompt`, `_build_arbiter_prompt`, `_initial_confidence`, `_parse_arbiter_verdict`, `_parse_extract_response`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/providers/memory/ingest.py](../../src/jarvis/providers/memory/ingest.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [overview](../overview.md)
- [architecture-layers](../../00-meta/architecture-layers.md)
- [memory-flow](./memory-flow.md)
- [memory](../../04-capabilities/tools/memory.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../02-kernel/bundle-offline.md)
- [process-map](../../maps/process-map.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
