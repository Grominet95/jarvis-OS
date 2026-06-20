from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable


class LLMProvider(ABC):
    """Interface commune à tous les providers LLM."""

    @property
    def supports_tools(self) -> bool:
        """True si le provider supporte la boucle tool use.

        Providers actifs : Anthropic, Mistral, Gemini, OpenAI.
        Providers chat-only (False) : Ollama.
        """
        return False

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        """Retourne la réponse complète ou un itérateur de chunks si stream=True."""

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Exécute la boucle tool use et retourne le texte final de la réponse.

        Doit être surchargée par les providers qui supportent les outils.
        """
        raise NotImplementedError("Tool use non supporté par ce provider.")

    @abstractmethod
    async def health_check(self) -> bool:
        """Vérifie que le provider est joignable."""
