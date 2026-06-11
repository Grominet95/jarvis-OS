from __future__ import annotations

from jarvis.kernel.settings import settings


def is_offline_mode() -> bool:
    """Retourne True si l'utilisateur a explicitement choisi le mode local (Ollama).

    Le signal primaire est le choix utilisateur (llm_provider == "local"),
    indépendamment de l'état réel du réseau. Cela garantit un comportement
    prévisible : si l'utilisateur dit "local", tous les services cloud se dégradent
    silencieusement, wifi ou pas.
    """
    return settings.llm_provider == "local"
