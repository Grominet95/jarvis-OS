# Error collector — Python API reference

Source of truth for codes: `scripts/error_audit/error-codes.yaml`.

Human workflow: [error-codes-contributor-guide.md](../09-operations/error-codes-contributor-guide.md)  
AI workflow: [error-codes-ai-instructions.md](error-codes-ai-instructions.md)

## When to emit

| Situation | API | Terminal level |
|-----------|-----|----------------|
| User-blocking failure | `collector.error(code, msg, cause=e)` | ERROR |
| Optional subsystem degraded | `collector.warning(code, msg, cause=e)` | WARN |
| Unreachable branch | `collector.impossible(msg, cause=e)` | IMPOSSIBLE → `JRV-ENG-999` |
| Preflight (stdlib only) | `_emit_stderr(code, msg, level=...)` in preflight | ERROR/WARN |
| HTTP route failure | `raise_api_error(code, status, detail)` | ERROR + HTTP response |

## Adding a new code

1. Pick domain prefix and next free `NNN` in `scripts/error_audit/error-codes.yaml`.
2. Add entry with French accents in all text fields.
3. Run `uv run python scripts/error_audit/generate_registry.py`
4. Run `uv run python scripts/error_audit/generate_docs.py`
5. Wire the code at the failure site.

## API

```python
from jarvis.kernel.error_collector import collector
from jarvis.kernel.errors import JarvisError, ToolError
from jarvis.kernel.http_errors import raise_api_error

collector.warning("JRV-PRO-001", "Collecteur email offline", cause=exc)
raise ToolError("JRV-TOL-002", "Spotify API failed", cause=exc)
raise_api_error("JRV-API-003", 404, "Ressource introuvable")
```

## Forbidden

- `except Exception: pass` without emit or `# jrv:` justification
- Bare `HTTPException` in API routes (use `raise_api_error`)
- User-facing strings without a registry entry
- Manual edits to generated files

## PR checklist

- [ ] New failure path has a `JRV-*` code in YAML (French with accents)
- [ ] `uv run python scripts/error_audit/scan.py --check` passes
- [ ] Test proves stderr contains `[JRV-...]` when applicable

## CI

```bash
uv run python scripts/error_audit/generate_registry.py
uv run python scripts/error_audit/scan.py --check
uv run pytest tests/test_error_collector.py tests/test_error_codes_registry.py tests/test_preflight_codes.py -q
```
