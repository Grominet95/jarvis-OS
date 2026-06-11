from __future__ import annotations

from jarvis.kernel.contracts import UsageTracker
from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import get_api_provider
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.llm.local import OllamaProvider


def get_llm_provider(tracker: UsageTracker | None = None) -> LLMProvider:
    """Instancie le provider LLM selon LLM_PROVIDER dans .env."""
    if settings.llm_provider == "local":
        return OllamaProvider()
    return get_api_provider(settings.api_backend, tracker=tracker)


def create_background_llm(tracker: UsageTracker | None = None) -> LLMProvider:
    """Provider léger et indépendant pour les tâches background (consolidation, auto_dream).

    Instance séparée = client HTTP distinct = aucune contention avec le provider principal.
    max_tokens=500 suffit largement pour les réponses de mémorisation.
    """
    if settings.llm_provider == "local":
        return OllamaProvider()
    if settings.api_backend == "anthropic":
        return get_api_provider("anthropic", max_tokens=500, tracker=tracker)
    return get_api_provider(settings.api_backend, tracker=tracker)
