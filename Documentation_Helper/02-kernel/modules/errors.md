# errors.py

- **Layer:** L0
- **Path:** `src/jarvis/kernel/errors.py`
- **Purpose:** Hiérarchie d'exceptions Jarvis avec codes `JRV-*` (CDC §A.1.3).
- **Key symbols:** `JarvisError`, `LLMError`, `MemoryError_`, `ToolError`, `SkillError`, `BudgetExceeded`, `PermissionDenied`
- **Related:** `error_collector.py`, `error_emit.py`, `error_hooks.py`, `http_errors.py`
- **Registry:** `scripts/error_audit/error-codes.yaml`
- **Developer guide:** [error-collector-guide.md](../../00-meta/error-collector-guide.md)
- **Contributor guide:** [error-codes-contributor-guide.md](../../09-operations/error-codes-contributor-guide.md)
- **AI instructions:** [error-codes-ai-instructions.md](../../00-meta/error-codes-ai-instructions.md)
- **Source of truth:** [src/jarvis/kernel/errors.py](../../src/jarvis/kernel/errors.py)

## Related docs

- [error-codes.md](../../09-operations/error-codes.md)
- [error-collector-guide.md](../../00-meta/error-collector-guide.md)
- [INDEX](../../INDEX.md)

- **Last reviewed:** 2026-08-16 (jarvis-os @ local)
