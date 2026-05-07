from __future__ import annotations

from config.settings import settings
from llm.api import get_api_provider
from llm.base import LLMProvider
from llm.local import OllamaProvider


def get_llm_provider() -> LLMProvider:
    """Instancie le provider LLM selon LLM_PROVIDER dans .env."""
    if settings.llm_provider == "local":
        return OllamaProvider()
    return get_api_provider(settings.api_backend)


def create_background_llm() -> LLMProvider:
    """Provider léger et indépendant pour les tâches background (consolidation, auto_dream).

    Instance séparée = client HTTP distinct = aucune contention avec le provider principal.
    max_tokens=500 suffit largement pour les réponses de mémorisation.
    """
    if settings.llm_provider == "local":
        return OllamaProvider()
    if settings.api_backend == "anthropic":
        return get_api_provider("anthropic", max_tokens=500)
    return get_api_provider(settings.api_backend)
