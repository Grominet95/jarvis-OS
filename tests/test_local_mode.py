"""Tests — cohérence du mode local (Ollama) hors-ligne."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Never
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.engine.agent import Agent
from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.gateway import Gateway
from jarvis.engine.session import SessionManager
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.llm.local import OllamaProvider
from jarvis.providers.memory.consolidation import CrossSessionRecall

# ── Fixtures de mode ──────────────────────────────────────────────────────────


@pytest.fixture
def local_mode() -> Iterator[None]:
    from jarvis.kernel.settings import settings

    old = settings.llm_provider
    object.__setattr__(settings, "llm_provider", "local")
    yield
    object.__setattr__(settings, "llm_provider", old)


@pytest.fixture
def api_mode() -> Iterator[None]:
    from jarvis.kernel.settings import settings

    old = settings.llm_provider
    object.__setattr__(settings, "llm_provider", "api")
    yield
    object.__setattr__(settings, "llm_provider", old)


# ── LLM factice ───────────────────────────────────────────────────────────────


class _MockLLM(LLMProvider):
    """Provider factice — retourne une réponse fixe sans réseau."""

    def __init__(self, response: str = "[I] ok") -> None:
        self._response = response
        self._model = "mock-model"

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs: object,
    ) -> str | AsyncIterator[str]:
        if stream:
            return self._stream()
        return self._response

    async def _stream(self) -> AsyncIterator[str]:
        for word in self._response.split():
            yield word + " "

    async def health_check(self) -> bool:
        return True


# ── Test 1 : is_offline_mode ──────────────────────────────────────────────────


def test_offline_mode_when_local(local_mode: None) -> None:
    """is_offline_mode() est True quand llm_provider == 'local'."""
    from jarvis.kernel.connectivity import is_offline_mode

    assert is_offline_mode() is True


def test_online_mode_when_api(api_mode: None) -> None:
    """is_offline_mode() est False quand llm_provider == 'api'."""
    from jarvis.kernel.connectivity import is_offline_mode

    assert is_offline_mode() is False


# ── Test 2 : factory retourne OllamaProvider en mode local ───────────────────


def test_gateway_uses_ollama_in_local_mode(local_mode: None) -> None:
    """En mode local, get_llm_provider() doit retourner OllamaProvider."""
    from jarvis.providers.llm.factory import get_llm_provider

    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider), (
        f"Mode local doit instancier OllamaProvider, got {type(provider).__name__}"
    )
    assert not isinstance(provider, AnthropicProvider)


def test_background_llm_not_anthropic_in_local_mode(local_mode: None) -> None:
    """create_background_llm() ne renvoie pas AnthropicProvider en mode local."""
    from jarvis.providers.llm.factory import create_background_llm

    bg_llm = create_background_llm()
    assert not isinstance(bg_llm, AnthropicProvider)
    assert isinstance(bg_llm, OllamaProvider)


# ── Test 3 : hot-swap met à jour gateway + voice_gateway ─────────────────────


def test_hot_swap_updates_gateway_and_voice_gateway(local_mode: None) -> None:
    """Après hot-swap en mode local, gateway ET voice_gateway utilisent OllamaProvider."""
    anthropic_llm = _MockLLM()

    from jarvis.kernel.settings import settings as _settings

    agent_main = Agent(settings=_settings, llm=anthropic_llm)
    agent_voice = Agent(settings=_settings, llm=anthropic_llm)
    notifications = NotificationQueue()
    worker = BackgroundWorker(llm=anthropic_llm, notifications=notifications)
    mgr = SessionManager()

    gw = Gateway(session_manager=mgr, agent=agent_main, notifications=notifications, worker=worker)
    vgw = Gateway(
        session_manager=mgr, agent=agent_voice, notifications=notifications, worker=worker
    )

    # Simule le hot-swap (même logique que http_config.update_setting)
    from jarvis.providers.llm.factory import get_llm_provider

    new_llm = get_llm_provider()
    object.__setattr__(gw._agent, "_llm", new_llm)
    object.__setattr__(vgw._agent, "_llm", new_llm)
    object.__setattr__(worker, "_llm", new_llm)

    assert isinstance(gw._agent._llm, OllamaProvider), "gateway doit utiliser OllamaProvider"
    assert isinstance(vgw._agent._llm, OllamaProvider), "voice_gateway doit utiliser OllamaProvider"
    assert isinstance(worker._llm, OllamaProvider), "worker doit utiliser OllamaProvider"
    assert not isinstance(gw._agent._llm, AnthropicProvider)
    assert not isinstance(vgw._agent._llm, AnthropicProvider)


# ── Test 4 : CrossSessionRecall skip résumé LLM en mode offline ───────────────


@pytest.mark.asyncio
async def test_cross_session_recall_offline_skips_llm(local_mode: None) -> None:
    """CrossSessionRecall.recall() en mode local ne fait pas d'appel LLM."""
    mock_llm = _MockLLM()
    mock_llm.complete = AsyncMock(return_value="résumé LLM")

    fts_mock = MagicMock()
    fts_mock.search = AsyncMock(
        return_value=[{"doc_id": "s1", "text": "Barth aime l'électronique"}]
    )
    vec_mock = MagicMock()
    vec_mock.search = AsyncMock(return_value=[])

    recall = CrossSessionRecall(llm=mock_llm, fts_index=fts_mock, vector_index=vec_mock)
    result = await recall.recall("électronique")

    mock_llm.complete.assert_not_called()
    assert result is not None
    assert "Barth" in result


@pytest.mark.asyncio
async def test_cross_session_recall_online_calls_llm(api_mode: None) -> None:
    """CrossSessionRecall.recall() en mode api appelle bien le LLM pour le résumé."""
    mock_llm = _MockLLM()
    mock_llm.complete = AsyncMock(return_value="résumé produit par le LLM")

    fts_mock = MagicMock()
    fts_mock.search = AsyncMock(
        return_value=[{"doc_id": "s1", "text": "Barth aime l'électronique"}]
    )
    vec_mock = MagicMock()
    vec_mock.search = AsyncMock(return_value=[])

    recall = CrossSessionRecall(llm=mock_llm, fts_index=fts_mock, vector_index=vec_mock)
    result = await recall.recall("électronique")

    mock_llm.complete.assert_called_once()
    assert result == "résumé produit par le LLM"


# ── Test 5 : CollectorBase en mode offline → [] sans ERROR ────────────────────


@pytest.mark.asyncio
async def test_collector_base_offline_no_error_log(
    local_mode: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """En mode local, une exception dans _collect() produit un DEBUG, pas un ERROR."""
    from jarvis.engine.proactive.collectors.base import CollectorBase

    class _FailingCollector(CollectorBase):
        name = "test_failing"

        async def _collect(self) -> Never:
            raise ConnectionRefusedError("réseau inaccessible")

    import logging

    with caplog.at_level(logging.DEBUG):
        items = await _FailingCollector().collect()

    assert items == []
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_records, (
        f"Des ERROR inattendus en mode local : {[r.message for r in error_records]}"
    )


@pytest.mark.asyncio
async def test_collector_base_online_returns_empty_on_failure(api_mode: None) -> None:
    """En mode api, une exception dans _collect() retourne [] sans lever."""
    from jarvis.engine.proactive.collectors.base import CollectorBase

    class _FailingCollector(CollectorBase):
        name = "test_failing_online"

        async def _collect(self) -> Never:
            raise ConnectionRefusedError("réseau inaccessible")

    # CollectorBase.collect() doit absorber l'exception et retourner [] dans tous les cas
    items = await _FailingCollector().collect()
    assert items == []
