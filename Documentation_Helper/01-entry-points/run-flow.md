# Run Flow

## Trigger

`.\jarvis.ps1 run` after setup complete.

## Sequence

1. `Require-JarvisBundle` — bundle or dev `.venv` required
2. `jarvis.kernel.preflight` — validate env, ports, native deps
3. Start **livekit-server** (:7880 dev keys)
4. Start **jarvis.app** (PORT from .env, default 8000)
5. Start **jarvis.interfaces.voice.agent dev**
6. Open browser to home UI

Logs: `%TEMP%\jarvis\*.log`


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [process-map](../maps/process-map.md)
- [troubleshooting](../09-operations/troubleshooting.md)
- [env-reference](../07-config/env-reference.md)
- [setup-flow](./setup-flow.md)
- [windows-launchers](./windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [logs-and-doctor](../09-operations/logs-and-doctor.md)
- [release-and-bundle](../09-operations/release-and-bundle.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
