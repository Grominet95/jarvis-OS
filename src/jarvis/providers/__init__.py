"""L1 — Providers : implémentations concrètes des contrats kernel.

Sous-packages :
- llm/    — providers LLM (Anthropic, Mistral, Gemini, OpenAI, Ollama, …).
- memory/ — Memory Kernel, AutoDream, CrossSessionRecall, ingestion, …
- audio/  — TTS (ElevenLabs, Piper), Deepgram, Clap detector, …
- vision/ — Object detection, face recognition, vision daemon, …

L'API publique de chaque sous-package est définie dans son propre
`__init__.py` ; ce module-ci ne réagrège que les pointeurs canoniques.
"""

from __future__ import annotations

__all__: list[str] = []
