# Runtime Config Files

| File | Purpose |
|------|---------|
| `config/tools.yaml` | Tool whitelist for mission capability engine |
| `config/approvals.json` | Approval categories and policies |
| `config/google_credentials.json` | OAuth client (generated from .env) |
| `config/google_*_token.json` | Gmail/Calendar tokens |
| `config/spotify_token.json` | Spotify OAuth token |
| `config/permissions.yaml` | Permission toggles (if present) |

Paths resolved via `kernel.paths.CONFIG_DIR`.

- **Source of truth:** [src/jarvis/kernel/paths.py](../../src/jarvis/kernel/paths.py)

## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [env-reference](./env-reference.md)
- [settings-and-env](../02-kernel/settings-and-env.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [run-flow](../01-entry-points/run-flow.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
