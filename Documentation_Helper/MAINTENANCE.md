# Maintenance Protocol

Documentation_Helper is **tracked in git** (except `AI_INSTRUCTIONS.md`, kept local to limit prompt injection). Regenerate indexes and cards when the codebase changes.

## Gitignore

```
Documentation_Helper/AI_INSTRUCTIONS.md
Documentation_Helper/doc_index.sqlite
```

Entry lives in the repo root `.gitignore`.

## Update triggers

| Code change | Doc action |
|-------------|------------|
| New/modified `src/jarvis/**/*.py` | Update/create module card; bump `maps/file-to-doc.yaml` |
| Router added/removed | Regenerate `maps/route-map.md` (compare `scripts/migration/routes.baseline.txt`) |
| `.env.example` key added | Update `07-config/env-reference.md` |
| Launcher script change | Update `01-entry-points/*` |
| New external integration | Add row in `08-integrations/index.md` + sheet in `08-integrations/sheets/` |
| `pyproject.toml` dependency bump | Update `00-meta/dependency-versions.md` |
| New JRV code in `error-codes.yaml` | Run `generate_docs.py` + `sync_doc_helper.py` (or `check_pr.py` gate) |

## Update checklist

1. Identify changed paths: `git diff --name-only`
2. Lookup paths in `maps/file-to-doc.yaml`
3. Edit listed docs + set **Last reviewed** date
4. If unmapped file: create module card + add YAML entry (or run generator)
5. For API changes: compare `scripts/migration/snapshot_routes.py` output to baseline

## Bulk regeneration

```powershell
python scripts/doc_helper/generate_module_cards.py
python scripts/doc_helper/write_overviews.py
uv run python scripts/error_audit/sync_doc_helper.py
cd scripts/doc_helper && npm install && npm run enrich-links && npm run build-index
```

`sync_doc_helper.py` regenerates `error-codes.md`, `error_codes.json`, and rebuilds `doc_index.sqlite` (table `error_codes` + FTS chunks).

This refreshes module cards, cross-links, and the FTS5 search index.

## FTS5 search index (~1k tokens for AI)

SQLite: `Documentation_Helper/doc_index.sqlite` (gitignored, rebuild with `npm run build-index`).

```powershell
cd scripts/doc_helper
npm run query -- --max-tokens 1000 "livekit voix marche pas"
npm run query -- --json "install bundle onedrive"
```

- **build-index** — chunk docs by section, expand FR/EN keywords + typo variants
- **query** — BM25 snippets + related links, capped at ~1000 tokens
- **enrich-links** — inject `## Related docs` across the corpus

Keywords: `scripts/doc_helper/keywords.js`

## Optional automation (phase 2)

- `scripts/doc_helper/sync_map.py` — scan `src/jarvis/**/*.py`, warn missing cards
- `scripts/doc_helper/stale_check.py` — compare git mtime vs doc Last reviewed


## Related docs

- [INDEX](./INDEX.md)
- [AI_INSTRUCTIONS](./AI_INSTRUCTIONS.md)
- [setup-flow](./01-entry-points/setup-flow.md)
- [windows-launchers](./01-entry-points/windows-launchers.md)
- [bundle-offline](./02-kernel/bundle-offline.md)
- [process-map](./maps/process-map.md)
- [env-reference](./07-config/env-reference.md)
- [run-flow](./01-entry-points/run-flow.md)
- [logs-and-doctor](./09-operations/logs-and-doctor.md)
- [troubleshooting](./09-operations/troubleshooting.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
