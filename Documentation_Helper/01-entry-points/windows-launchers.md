# Windows Launchers

## jarvis.ps1

Main Windows entry point. Commands: `setup`, `run`, `stop`, `doctor`, etc.

- Uses `bundle/.venv/Scripts/python.exe` when present, else `.venv`, else `uv run`
- Sources `scripts/onedrive_guard.ps1` and `scripts/download_bundle.ps1`
- `Require-JarvisBundle` blocks `run` without bundle or dev venv
- `Invoke-JarvisRun` starts LiveKit (:7880), API (`jarvis.app`), voice agent

## Related scripts

| Script | Role |
|--------|------|
| `scripts/download_bundle.ps1` | CDN bundle download (techalchemy.fr) |
| `scripts/release/rehome_bundle.ps1` | Fix venv paths after bundle extract |
| `scripts/onedrive_guard.ps1` | Block or relocate OneDrive installs |
| `setup.ps1` | Bundle-only Python setup helper |

- **Source of truth:** [jarvis.ps1](../../jarvis.ps1)

## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [process-map](../maps/process-map.md)
- [troubleshooting](../09-operations/troubleshooting.md)
- [env-reference](../07-config/env-reference.md)
- [setup-flow](./setup-flow.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [run-flow](./run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)
- [release-and-bundle](../09-operations/release-and-bundle.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
