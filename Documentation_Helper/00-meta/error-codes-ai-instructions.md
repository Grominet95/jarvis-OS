# Error codes — AI agent instructions

Use this document when adding or updating `JRV-*` error codes in Jarvis OS.

## Source of truth

| File | Role |
|------|------|
| `scripts/error_audit/error-codes.yaml` | **Only** editable registry (75+ codes) |
| `scripts/error_audit/inventory.json` | Generated audit of all error sites |
| `src/jarvis/kernel/_error_codes_generated.py` | **Generated** — never edit |
| `Documentation_Helper/09-operations/error-codes.md` | **Generated** — never edit |

There is no copy under `Documentation_Helper/maps/`. The YAML in `scripts/error_audit/` is the single source.

## Workflow (strict order)

1. Run baseline:
   ```bash
   uv run python scripts/error_audit/scan.py --check
   ```
2. Identify the unmapped site in `inventory.json` or scan output (`file:line [kind]`).
3. Choose domain prefix and next free `NNN` (see table below).
4. Add entry to `scripts/error_audit/error-codes.yaml` with **all** required fields and **French with accents**.
5. Regenerate:
   ```bash
   uv run python scripts/error_audit/generate_registry.py
   uv run python scripts/error_audit/generate_docs.py
   ```
6. Wire the failure site in Python (one of):
   - `collector.error("JRV-XXX-NNN", "message", cause=exc)`
   - `collector.warning("JRV-XXX-NNN", "message", cause=exc)`
   - `raise_api_error("JRV-XXX-NNN", status, "detail")`
   - `raise ToolError("JRV-XXX-NNN", "message", cause=exc)`
   - `# jrv: justification` on intentional silent handlers (preflight probes, expected shutdown)
7. Verify:
   ```bash
   uv run python scripts/error_audit/scan.py --check
   uv run pytest tests/test_error_collector.py tests/test_error_codes_registry.py tests/test_preflight_codes.py -q
   uv run ruff check src/jarvis
   ```
8. If user-facing symptom: update `playbooks/error-catalog.md` and `INDEX.md` if needed.

## YAML schema (template)

```yaml
JRV-TOL-015:
  domain: TOL
  severity: error          # error | warning
  title_fr: "Échec outil exemple"
  message_fr: "Description courte du symptôme terminal."
  resolution_fr: "Action concrète pour l'utilisateur ou l'ops."
  docs: ["04-capabilities/tools/example.md"]
  since: "0.3.3"
  modules: ["capabilities/tools/example.py"]
```

Required fields: `domain`, `severity`, `title_fr`, `message_fr`, `resolution_fr`, `docs`, `since`.

French rules: use accents (`é`, `è`, `à`, `ç`), full sentences, apostrophes (`l'API`, `n'a pas`).

## Domain prefixes

| Prefix | Domain | Generic fallback |
|--------|--------|------------------|
| JRV-KRN | kernel, bundle, paths, preflight | JRV-KRN-002 |
| JRV-SET | setup wizard | JRV-SET-001 |
| JRV-BTS | bootstrap | JRV-BTS-001 |
| JRV-LLM | LLM providers | JRV-LLM-002 |
| JRV-API | HTTP routes | JRV-API-001 |
| JRV-TOL | tools | JRV-TOL-001 |
| JRV-SKL | skills | JRV-SKL-001 |
| JRV-MEM | memory | JRV-MEM-001 |
| JRV-GWY | gateway | JRV-GWY-001 |
| JRV-PRO | proactive | JRV-PRO-001 |
| JRV-MSG | channels | JRV-MSG-001 |
| JRV-ENG | engine generic | JRV-ENG-000 |
| JRV-UNK | uncaught | JRV-UNK-001 |

Reserved: `JRV-ENG-999` (impossible branch), `JRV-ENG-000` (generic catch-all).

## When to create a specific code vs reuse generic

| Create specific `JRV-TOL-00N` | Reuse `JRV-TOL-001` |
|-------------------------------|---------------------|
| User can identify the tool (Spotify, Gmail) | Autofix `except Exception` in tool internals |
| Symptom in error-catalog.md | Rare one-off degradation |
| Ops needs distinct resolution steps | |

API status mapping (already used in migrated routes):

| HTTP status | Code |
|-------------|------|
| 400, 422 | JRV-API-004 |
| 401 | JRV-API-002 |
| 403 | JRV-PRM-001 |
| 404 | JRV-API-003 |
| 503 | JRV-API-005 |
| other | JRV-API-001 |

## Forbidden

- Edit `_error_codes_generated.py` or `error-codes.md` manually
- `except: pass` without emit or `# jrv:` comment
- Bare `raise HTTPException(...)` in API routes (use `raise_api_error`)
- ASCII French without accents in YAML (`Echec`, `cle`, `depasse`)
- Duplicate codes in YAML

## Tool registry mapping

`capabilities/tools/registry.py` maps tool names to specific codes (`JRV-TOL-002` Spotify, etc.). When adding a new first-class tool, add a row to `_TOOL_CODES` and a YAML entry.

## Related docs

- [error-collector-guide.md](error-collector-guide.md) — Python API reference
- [error-codes-contributor-guide.md](../09-operations/error-codes-contributor-guide.md) — human workflow
- [error-codes.md](../09-operations/error-codes.md) — ops catalogue (generated)
