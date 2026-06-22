# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from collections.abc import AsyncIterator

from jarvis.engine.agent import Agent
from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.gateway import Gateway
from jarvis.engine.router import RouteEnum
from jarvis.engine.session import Session, SessionManager
from jarvis.kernel.settings import settings as _test_settings
from jarvis.providers.llm.base import LLMProvider


class _MockLLM(LLMProvider):
    """Provider mock pour les tests — retourne une réponse fixe."""

    def __init__(self, response: str = "[I] Bonjour chef.") -> None:
        self._response = response

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        if stream:
            return self._stream()
        return self._response

    async def _stream(self) -> AsyncIterator[str]:
        for word in self._response.split():
            yield word + " "

    async def health_check(self) -> bool:
        return True


def _make_gateway(response: str = "[I] Bonjour chef.") -> tuple[Gateway, SessionManager]:
    mgr = SessionManager()
    llm = _MockLLM(response)
    agent = Agent(settings=_test_settings, llm=llm)
    notifications = NotificationQueue()
    worker = BackgroundWorker(llm=llm, notifications=notifications)
    return (
        Gateway(session_manager=mgr, agent=agent, notifications=notifications, worker=worker),
        mgr,
    )


async def test_gateway_returns_session_and_response() -> None:
    gw, _ = _make_gateway()
    session, route, response = await gw.handle(message="Salut", stream=False)
    assert isinstance(session, Session)
    assert isinstance(response, str)
    assert "Bonjour" in response
    assert route == RouteEnum.INSTANT


async def test_gateway_reuses_session() -> None:
    gw, _ = _make_gateway()
    session1, _, _ = await gw.handle(message="Premier message", stream=False)
    session2, _, _ = await gw.handle(
        message="Deuxième message", session_id=str(session1.id), stream=False
    )
    assert session1.id == session2.id
    # Historique: user1, assistant1, user2, assistant2
    assert len(session1.messages) == 4


async def test_gateway_stream() -> None:
    gw, _ = _make_gateway("[I] Bonjour chef.")
    session, route, response = await gw.handle(message="Salut", stream=True)
    assert not isinstance(response, str)
    assert route == RouteEnum.INSTANT
    full = ""
    async for chunk in response:  # type: ignore[union-attr]
        full += chunk
    session.add_message("assistant", full)
    assert "Bonjour" in full


async def test_gateway_fallback_on_error() -> None:
    class _BrokenLLM(_MockLLM):
        async def complete(self, **kwargs: object) -> str:  # type: ignore[override]
            raise RuntimeError("LLM down")

    mgr = SessionManager()
    llm = _BrokenLLM()
    agent = Agent(settings=_test_settings, llm=llm)
    notifications = NotificationQueue()
    worker = BackgroundWorker(llm=llm, notifications=notifications)
    gw = Gateway(session_manager=mgr, agent=agent, notifications=notifications, worker=worker)

    session, route, response = await gw.handle(message="Test", stream=False)
    assert isinstance(response, str)
    assert route == RouteEnum.INSTANT
    assert "souci" in response
