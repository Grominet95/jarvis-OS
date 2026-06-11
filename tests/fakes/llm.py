"""FakeLLMProvider — implémentation déterministe conforme au Protocol.

Conforme à `jarvis.kernel.contracts.LLMProvider` :
  - `supports_tools` (property → bool)
  - `complete(messages, system, tools=None, stream=False, context="")`
  - `tool_loop(messages, system, tools, tool_executor, context="")`
  - `health_check() -> bool`

Toutes les réponses sont déterministes et hors-réseau. Le contenu est
choisi pour que le smoke runtime puisse vérifier que la chaîne
LLM → Agent → Gateway → Session a fonctionné de bout en bout.

Réponses canned :
  - messages contenant "ping" → "pong (fake-llm)"
  - messages contenant "plan" → JSON de plan minimal (1 step)
  - tout le reste → echo "Reçu : <derniers 60 chars du dernier message user>"
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable


class FakeLLMProvider:
    """Implémentation Protocol-conforme avec réponses canned."""

    def __init__(self, *, marker: str = "fake-llm") -> None:
        self._marker = marker
        self.calls: list[dict] = []  # historique pour les assertions de test

    @property
    def supports_tools(self) -> bool:
        return True

    def _last_user_content(self, messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    return content
                # Format Anthropic (liste de blocs) : on prend le 1er bloc texte.
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return str(block.get("text", ""))
        return ""

    def _decide_response(self, messages: list[dict]) -> str:
        last = self._last_user_content(messages).lower()
        if "ping" in last:
            return f"pong ({self._marker})"
        if "plan" in last or "mission" in last:
            # Plan minimal exploitable par ProjectManager._parse_plan.
            return json.dumps(
                {
                    "title": "Smoke mission",
                    "steps": [
                        {
                            "id": "s1",
                            "title": "Vérifier le boot",
                            "success_criterion": "smoke runtime imprime BOOT OK",
                        }
                    ],
                }
            )
        last_full = self._last_user_content(messages)
        snippet = last_full[-60:] if last_full else "(vide)"
        return f"Reçu ({self._marker}) : {snippet}"

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        self.calls.append(
            {
                "method": "complete",
                "stream": stream,
                "n_messages": len(messages),
                "context": context,
            }
        )
        text = self._decide_response(messages)
        if stream:

            async def _chunks() -> AsyncIterator[str]:
                # Découpe en 2 chunks pour exercer le path streaming.
                mid = len(text) // 2 or 1
                yield text[:mid]
                yield text[mid:]

            return _chunks()
        return text

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        self.calls.append(
            {
                "method": "tool_loop",
                "n_messages": len(messages),
                "n_tools": len(tools),
                "context": context,
            }
        )
        return self._decide_response(messages)

    async def health_check(self) -> bool:
        return True
