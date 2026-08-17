# Troubleshooting

## Bundle missing

**Symptom:** `Bundle offline absent` on run.

**Fix:** Run `.\jarvis.ps1 setup` to download CDN bundle.

## OneDrive install

**Symptom:** Guard blocks setup from OneDrive path.

**Fix:** Move repo to local disk or accept auto-relocate prompt.

## LIVEKIT_URL / voice fails

**Symptom:** Voice agent cannot connect.

**Fix:** Set `LIVEKIT_URL`, keys in `.env`. For local dev, `jarvis.ps1 run` starts embedded livekit-server on :7880.

## API timeout on run

**Symptom:** API health check fails after 90s.

**Fix:** Read `%TEMP%\jarvis\api.log`. Common: missing native dep, invalid .env, port in use. Run `python -m jarvis.kernel.preflight`.

## pyvenv / bundle path broken

**Fix:** Run `scripts/release/rehome_bundle.ps1`.


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [logs-and-doctor](./logs-and-doctor.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [process-map](../maps/process-map.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)
- [release-and-bundle](./release-and-bundle.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
