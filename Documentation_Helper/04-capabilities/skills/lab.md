# lab.py

- **Layer:** L1
- **Path:** `src/jarvis/capabilities/skills/lab.py`
- **Purpose:** Skill Lab (CDC §7) — génération + test sandbox + cycle de vie.
- **Key symbols:** Classes: `SandboxTestResult`, `LabScanResult`, `SkillLab`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/capabilities/skills/lab.py](../../src/jarvis/capabilities/skills/lab.py)

## Related docs

- [INDEX](../../INDEX.md)
- [AI_INSTRUCTIONS](../../AI_INSTRUCTIONS.md)
- [tools-registry](../tools-registry.md)
- [gateway-and-agent](../../05-engine/gateway-and-agent.md)
- [setup-flow](../../01-entry-points/setup-flow.md)
- [windows-launchers](../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../02-kernel/bundle-offline.md)
- [process-map](../../maps/process-map.md)
- [env-reference](../../07-config/env-reference.md)
- [run-flow](../../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
