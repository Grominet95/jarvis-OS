# Dependency Versions

Pinned summary from `pyproject.toml` (jarvis-os 0.3.2, Python >=3.11,<3.14).

## Core runtime

- `fastapi>=0.115.0`
- `python-multipart>=0.0.9`
- `uvicorn[standard]>=0.32.0`
- `pydantic>=2.9.0`
- `pydantic-settings>=2.6.0`
- `python-dotenv>=1.0.0`
- `anthropic>=0.40.0`
- `google-genai>=1.0.0`
- `ollama>=0.4.0`
- `httpx>=0.28.0`
- `loguru>=0.7.3`
- `pyyaml>=6.0.3`
- `beautifulsoup4>=4.12.0`
- `lxml>=5.0.0`
- `opencv-python>=4.13.0.92`
- `pillow>=10.0.0`
- `ultralytics>=8.0.0`
- `google-api-python-client>=2.197.0`
- `google-auth-oauthlib>=1.4.0`
- `faster-whisper>=1.1.0`

## Optional

- `face-recognition>=1.3.0` (vision extra)
- `pytest`, `pytest-asyncio`, `ruff` (dev extra)

## Source of truth

[pyproject.toml](../../pyproject.toml)


## Related docs

- [INDEX](../INDEX.md)
- [AI_INSTRUCTIONS](../AI_INSTRUCTIONS.md)
- [architecture-layers](./architecture-layers.md)
- [bootstrap-wiring](./bootstrap-wiring.md)
- [process-map](../maps/process-map.md)
- [setup-flow](../01-entry-points/setup-flow.md)
- [windows-launchers](../01-entry-points/windows-launchers.md)
- [bundle-offline](../02-kernel/bundle-offline.md)
- [env-reference](../07-config/env-reference.md)
- [run-flow](../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-13 (jarvis-os @ local)
