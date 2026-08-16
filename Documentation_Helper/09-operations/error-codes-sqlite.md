# JRV error codes in doc_index.sqlite

Structured lookup table synced from `scripts/error_audit/error-codes.yaml` into `Documentation_Helper/doc_index.sqlite`.

## Pipeline

1. `uv run python scripts/error_audit/generate_docs.py`
   - `Documentation_Helper/09-operations/error-codes.md` (human + FTS chunks)
   - `scripts/doc_helper/error_codes.json` (machine export)
2. `cd scripts/doc_helper && npm run build-index`
   - fills table `error_codes` (one row per `JRV-*` code)
3. One-shot: `uv run python scripts/error_audit/sync_doc_helper.py`

## Schema

| Column | Role |
|--------|------|
| `code` | Primary key, e.g. `JRV-KRN-011` |
| `domain` | Three-letter domain (`KRN`, `API`, `TOL`, …) |
| `severity` | `error`, `warning`, … |
| `title_fr` | Short French title |
| `message_fr` | User-facing message |
| `resolution_fr` | Suggested fix |
| `docs` | Pipe-separated doc paths (`09-operations/...`) |
| `modules` | Pipe-separated source modules |
| `since` | Version introduced |

FTS chunks for the markdown catalogue remain in `chunks` / `chunks_fts`. Exact code lookup uses `error_codes`.

## Query examples

```powershell
cd scripts/doc_helper
npm run query -- --max-tokens 1000 "JRV-KRN-011 bundle"
npm run query -- --json "code erreur telegram"
```

```sql
SELECT code, title_fr, resolution_fr FROM error_codes WHERE code = 'JRV-TOL-001';
```

## Runtime (Python)

- `jarvis.kernel.error_doc_lookup` — registry lookup + optional SQLite enrichment
- Telegram / Discord: `/error JRV-XXX-NNN`, `/jrv …`, or a message that is only the code

## Related docs

- [error-codes.md](./error-codes.md)
- [error-codes-contributor-guide.md](./error-codes-contributor-guide.md)
- [../00-meta/error-collector-guide.md](../00-meta/error-collector-guide.md)
- [../playbooks/error-catalog.md](../playbooks/error-catalog.md)

- **Last reviewed:** 2026-08-16 (jarvis-os @ local)
