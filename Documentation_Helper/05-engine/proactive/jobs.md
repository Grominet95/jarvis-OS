# jobs.py

- **Layer:** L2
- **Path:** `src/jarvis/engine/proactive/trackers/jobs.py`
- **Purpose:** JobTracker — suivi des candidatures stages/jobs.
- **Key symbols:** Classes: `JobStatus`, `JobApplication`, `JobTracker`; Functions: `_jobs_path`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/engine/proactive/trackers/jobs.py](../../src/jarvis/engine/proactive/trackers/jobs.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [overview](../overview.md)
- [gateway-and-agent](../gateway-and-agent.md)
- [bootstrap-wiring](../../00-meta/bootstrap-wiring.md)
- [overview](./overview.md)
- [index](../../08-integrations/index.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../02-kernel/bundle-offline.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
