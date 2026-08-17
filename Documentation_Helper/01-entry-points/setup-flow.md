# Setup Flow

## Trigger

User runs `.\jarvis.ps1 setup` (or equivalent) after clone.

## Sequence

1. OneDrive guard check
2. Download bundle from CDN if missing (`download_bundle.ps1`)
3. Rehome bundle venv (`rehome_bundle.ps1`)
4. Start `jarvis.setup_app` on port **8765**
5. Browser opens `setup.html` wizard
6. Wizard writes `.env` with `SETUP_COMPLETE=true`

## Key modules

- `kernel/bundle_download.py` — CDN URL constants
- `interfaces/api/setup_wizard.py` — setup API
- `interfaces/ui/static/setup.html`, `setup.js`

See [maps/process-map.md](../maps/process-map.md).


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [process-map](../maps/process-map.md)
- [troubleshooting](../09-operations/troubleshooting.md)
- [env-reference](../07-config/env-reference.md)
- [windows-launchers](./windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [run-flow](./run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)
- [release-and-bundle](../09-operations/release-and-bundle.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
