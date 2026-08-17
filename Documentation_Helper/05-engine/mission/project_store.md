# project_store.py

- **Layer:** L2
- **Path:** `src/jarvis/engine/mission/project_store.py`
- **Purpose:** Persistance des projets sur disque — JSONL pour les logs, JSON pour l'état.
- **Key symbols:** Classes: `ProjectStore`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/engine/mission/project_store.py](../../src/jarvis/engine/mission/project_store.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [overview](../overview.md)
- [gateway-and-agent](../gateway-and-agent.md)
- [bootstrap-wiring](../../00-meta/bootstrap-wiring.md)
- [overview](./overview.md)
- [backends](./backends.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../02-kernel/bundle-offline.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
