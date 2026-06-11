from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── OllamaProvider — chat-only ────────────────────────────────────────────────


def test_ollama_supports_tools_true() -> None:
    """OllamaProvider supporte les outils (function calling Ollama) : supports_tools=True."""
    from jarvis.providers.llm.local import OllamaProvider

    provider = OllamaProvider()
    assert provider.supports_tools is True


# ── AnthropicProvider — régression ───────────────────────────────────────────


def test_anthropic_supports_tools_true() -> None:
    """AnthropicProvider annonce le support des outils (régression)."""
    with patch("jarvis.providers.llm.api.anthropic.AsyncAnthropic"):
        from jarvis.providers.llm.api import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.supports_tools is True


# ── MistralProvider ───────────────────────────────────────────────────────────


def test_mistral_supports_tools_true() -> None:
    """MistralProvider annonce le support des outils."""
    with patch("jarvis.providers.llm.api.AsyncOpenAI"):
        from jarvis.providers.llm.api import MistralProvider

        provider = MistralProvider()
        assert provider.supports_tools is True


@pytest.mark.asyncio
async def test_mistral_tool_loop_executes_tool() -> None:
    """tool_loop Mistral : l'outil est exécuté et la synthèse LLM est retournée."""
    with patch("jarvis.providers.llm.api.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Réponse 1 : appel d'outil
        tc_mock = MagicMock()
        tc_mock.id = "call_01"
        tc_mock.function.name = "get_weather"
        tc_mock.function.arguments = json.dumps({"city": "Paris"})

        resp1 = MagicMock()
        resp1.choices[0].finish_reason = "tool_calls"
        resp1.choices[0].message.content = None
        resp1.choices[0].message.tool_calls = [tc_mock]

        # Réponse 2 : synthèse finale
        resp2 = MagicMock()
        resp2.choices[0].finish_reason = "stop"
        resp2.choices[0].message.content = "Il fait 25°C à Paris."
        resp2.choices[0].message.tool_calls = None

        mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        from jarvis.providers.llm.api import MistralProvider

        provider = MistralProvider()
        executed: list[str] = []

        async def mock_executor(name: str, inputs: dict) -> str:
            executed.append(name)
            assert name == "get_weather"
            assert inputs.get("city") == "Paris"
            return "Ensoleillé, 25°C"

        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "Quel temps à Paris ?"}],
            system="Tu es Jarvis.",
            tools=[
                {
                    "name": "get_weather",
                    "description": "Retourne la météo d'une ville.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "Nom de la ville"}
                        },
                        "required": ["city"],
                    },
                }
            ],
            tool_executor=mock_executor,
        )

        assert "get_weather" in executed
        assert "25" in result or "Paris" in result
        assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_mistral_stream_with_capture_detects_tool() -> None:
    """stream_with_capture Mistral : un tool call delta peuple ToolCapture.calls."""
    with patch("jarvis.providers.llm.api.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Chunk texte
        chunk_text = MagicMock()
        chunk_text.choices = [MagicMock()]
        chunk_text.choices[0].delta.content = "Je vérifie..."
        chunk_text.choices[0].delta.tool_calls = None
        chunk_text.choices[0].finish_reason = None

        # Chunk tool_call
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_42"
        tc_delta.function.name = "get_weather"
        tc_delta.function.arguments = '{"city":"Lyon"}'

        chunk_tool = MagicMock()
        chunk_tool.choices = [MagicMock()]
        chunk_tool.choices[0].delta.content = None
        chunk_tool.choices[0].delta.tool_calls = [tc_delta]
        chunk_tool.choices[0].finish_reason = "tool_calls"

        async def _fake_chunks(*_args: object, **_kw: object) -> AsyncIterator[object]:
            for c in [chunk_text, chunk_tool]:
                yield c

        mock_client.chat.completions.create = AsyncMock(return_value=_fake_chunks())

        from jarvis.providers.llm.api import MistralProvider

        provider = MistralProvider()
        stream, capture = provider.stream_with_capture(
            messages=[{"role": "user", "content": "Météo Lyon ?"}],
            system="Tu es Jarvis.",
            tools=[
                {
                    "name": "get_weather",
                    "description": "Météo",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                }
            ],
        )

        text_chunks: list[str] = []
        async for chunk in stream:
            text_chunks.append(chunk)

        assert capture.calls, "ToolCapture.calls doit contenir au moins un appel"
        assert capture.calls[0][1] == "get_weather"
        assert capture.calls[0][2] == {"city": "Lyon"}
        assert "Je vérifie..." in text_chunks


# ── GeminiProvider ────────────────────────────────────────────────────────────


def test_gemini_supports_tools_true() -> None:
    """GeminiProvider annonce le support des outils."""
    import google.genai  # noqa: F401 — force le chargement avant patch (idem)

    with patch("google.genai.Client"):
        from jarvis.providers.llm.api import GeminiProvider

        provider = GeminiProvider()
        assert provider.supports_tools is True


@pytest.mark.asyncio
async def test_gemini_tool_loop_executes_tool() -> None:
    """tool_loop Gemini : l'outil est exécuté et la synthèse LLM est retournée."""
    # NB : pré-charger google.genai pour éviter la fragilité de mock.patch
    # quand le namespace google a déjà été chargé partiellement (google.auth
    # via Calendar/Gmail Tool) — sinon `patch("google.genai.Client")` ne
    # capture pas correctement la classe selon l'ordre des tests.
    import google.genai  # noqa: F401 — force le chargement avant patch

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Réponse 1 : function call
        fc_mock = MagicMock()
        fc_mock.name = "get_weather"
        fc_mock.args = {"city": "Lyon"}

        part_fc = MagicMock()
        part_fc.function_call = fc_mock
        part_fc.text = None

        content1 = MagicMock()
        content1.parts = [part_fc]

        cand1 = MagicMock()
        cand1.content = content1

        resp1 = MagicMock()
        resp1.candidates = [cand1]
        resp1.function_calls = [fc_mock]
        resp1.text = None

        # Réponse 2 : texte final
        part_text = MagicMock()
        part_text.function_call = None
        part_text.text = "Il fait 22°C à Lyon."

        content2 = MagicMock()
        content2.parts = [part_text]

        cand2 = MagicMock()
        cand2.content = content2

        resp2 = MagicMock()
        resp2.candidates = [cand2]
        resp2.function_calls = None
        resp2.text = "Il fait 22°C à Lyon."

        mock_client.aio.models.generate_content = AsyncMock(side_effect=[resp1, resp2])

        from jarvis.providers.llm.api import GeminiProvider

        provider = GeminiProvider()
        executed: list[str] = []

        async def mock_executor(name: str, inputs: dict) -> str:
            executed.append(name)
            assert name == "get_weather"
            assert inputs.get("city") == "Lyon"
            return "Nuageux, 22°C"

        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "Météo Lyon ?"}],
            system="Tu es Jarvis.",
            tools=[
                {
                    "name": "get_weather",
                    "description": "Retourne la météo.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ],
            tool_executor=mock_executor,
        )

        assert "get_weather" in executed
        assert "22" in result or "Lyon" in result
        assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_gemini_stream_with_capture_detects_tool() -> None:
    """stream_with_capture Gemini : chunk.function_calls peuple ToolCapture.calls."""
    # NB : pré-charger google.genai pour éviter la fragilité de mock.patch
    # quand le namespace google a déjà été chargé partiellement (google.auth
    # via Calendar/Gmail Tool) — sinon `patch("google.genai.Client")` ne
    # capture pas correctement la classe selon l'ordre des tests.
    import google.genai  # noqa: F401 — force le chargement avant patch

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fc_mock = MagicMock()
        fc_mock.name = "search_web"
        fc_mock.args = {"query": "Python asyncio"}

        # Chunk texte
        chunk_text = MagicMock()
        chunk_text.text = "Je cherche..."
        chunk_text.function_calls = None

        # Chunk final avec function_call
        chunk_fc = MagicMock()
        chunk_fc.text = None
        chunk_fc.function_calls = [fc_mock]

        async def _fake_stream(*_args: object, **_kw: object) -> AsyncIterator[object]:
            for c in [chunk_text, chunk_fc]:
                yield c

        mock_client.aio.models.generate_content_stream = AsyncMock(return_value=_fake_stream())

        from jarvis.providers.llm.api import GeminiProvider

        provider = GeminiProvider()
        stream, capture = provider.stream_with_capture(
            messages=[{"role": "user", "content": "Cherche Python asyncio"}],
            system="Tu es Jarvis.",
            tools=[
                {
                    "name": "search_web",
                    "description": "Recherche web",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                }
            ],
        )

        text_chunks: list[str] = []
        async for chunk in stream:
            text_chunks.append(chunk)

        assert capture.calls, "ToolCapture.calls doit contenir au moins un appel"
        assert capture.calls[0][1] == "search_web"
        assert capture.calls[0][2] == {"query": "Python asyncio"}
        assert "Je cherche..." in text_chunks
