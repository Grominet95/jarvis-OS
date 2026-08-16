# paths.py

- **Layer:** L0
- **Path:** `src/jarvis/kernel/paths.py`
- **Purpose:** Chemins runtime du projet — source de vérité unique (CDC §B.5).
- **Key symbols:** Functions: `_find_project_root`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/kernel/paths.py](../../src/jarvis/kernel/paths.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [overview](../overview.md)
- [env-reference](../../07-config/env-reference.md)
- [architecture-layers](../../00-meta/architecture-layers.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../bundle-offline.md)
- [process-map](../../maps/process-map.md)
- [run-flow](../../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
