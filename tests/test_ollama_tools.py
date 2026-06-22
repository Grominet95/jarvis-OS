# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

_WEATHER_TOOL = {
    "name": "get_weather",
    "description": "Retourne la météo d'une ville.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "Nom de la ville"}},
        "required": ["city"],
    },
}

_ECHO_TOOL = {
    "name": "echo",
    "description": "Renvoie le texte fourni.",
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


def _mock_response(data: dict) -> MagicMock:
    """Construit un mock httpx.Response retournant data via .json()."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _make_httpx_mock(*json_responses: dict) -> tuple[MagicMock, AsyncMock]:
    """Retourne (mock_ctx, mock_client) pour patcher llm.local.httpx.AsyncClient.

    mock_ctx est renvoyé par httpx.AsyncClient(...) ; mock_client.post répond
    aux requêtes dans l'ordre avec les données json_responses.
    """
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[_mock_response(d) for d in json_responses])

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_client


def _tool_call_response(name: str, arguments: object) -> dict:
    """Réponse Ollama simulant un appel d'outil."""
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    }


def _text_response(content: str) -> dict:
    """Réponse Ollama simulant une réponse texte finale."""
    return {"message": {"role": "assistant", "content": content}}


# ── supports_tools ────────────────────────────────────────────────────────────


def test_supports_tools_true() -> None:
    """OllamaProvider.supports_tools doit valoir True (function calling activé)."""
    from jarvis.providers.llm.local import OllamaProvider

    provider = OllamaProvider()
    assert provider.supports_tools is True


# ── _payload ──────────────────────────────────────────────────────────────────


def test_payload_includes_tools_when_provided() -> None:
    """_payload inclut le champ 'tools' au format Ollama/OpenAI quand des outils sont fournis."""
    from jarvis.providers.llm.local import OllamaProvider

    provider = OllamaProvider()
    payload = provider._payload(
        messages=[{"role": "user", "content": "test"}],
        system="Tu es Jarvis.",
        stream=False,
        tools=[_WEATHER_TOOL],
    )

    assert "tools" in payload
    tools = payload["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    fn = tools[0]["function"]
    assert fn["name"] == "get_weather"
    assert fn["description"] == "Retourne la météo d'une ville."
    assert fn["parameters"]["type"] == "object"
    assert "city" in fn["parameters"]["properties"]


def test_payload_no_tools_key_when_none() -> None:
    """_payload n'ajoute pas le champ 'tools' quand tools=None."""
    from jarvis.providers.llm.local import OllamaProvider

    provider = OllamaProvider()
    payload = provider._payload(
        messages=[{"role": "user", "content": "test"}],
        system="Tu es Jarvis.",
        stream=False,
        tools=None,
    )
    assert "tools" not in payload


def test_payload_tools_schema_maps_input_schema() -> None:
    """_payload convertit input_schema (Claude) vers parameters (OpenAI/Ollama)."""
    from jarvis.providers.llm.local import OllamaProvider

    provider = OllamaProvider()
    tool = {
        "name": "search",
        "description": "Recherche web",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    payload = provider._payload([], "sys", False, tools=[tool])
    fn = payload["tools"][0]["function"]
    assert fn["parameters"]["required"] == ["query"]
    assert "query" in fn["parameters"]["properties"]


# ── tool_loop — cas de base ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_loop_simple_call() -> None:
    """tool_loop : outil détecté, executor appelé, résultat réinjecté, texte final retourné."""
    from jarvis.providers.llm.local import OllamaProvider

    resp1 = _tool_call_response("get_weather", {"city": "Paris"})
    resp2 = _text_response("Il fait 25°C à Paris.")
    mock_ctx, mock_client = _make_httpx_mock(resp1, resp2)

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        executed: list[str] = []

        async def mock_executor(name: str, args: dict) -> str:
            executed.append(name)
            assert name == "get_weather"
            assert args.get("city") == "Paris"
            return "Ensoleillé, 25°C"

        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "Quel temps à Paris ?"}],
            system="Tu es Jarvis.",
            tools=[_WEATHER_TOOL],
            tool_executor=mock_executor,
        )

    assert "get_weather" in executed
    assert "25" in result or "Paris" in result
    assert mock_client.post.call_count == 2


# ── tool_loop — format des arguments ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_loop_args_as_dict() -> None:
    """tool_loop gère les arguments dict (format natif Ollama pour certains modèles)."""
    from jarvis.providers.llm.local import OllamaProvider

    resp1 = _tool_call_response("get_weather", {"city": "Lyon"})
    resp2 = _text_response("Nuageux à Lyon.")
    mock_ctx, _ = _make_httpx_mock(resp1, resp2)

    received_args: list[dict] = []

    async def mock_executor(name: str, args: dict) -> str:
        received_args.append(args)
        return "nuageux"

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        await provider.tool_loop(
            messages=[{"role": "user", "content": "Météo Lyon ?"}],
            system="sys",
            tools=[_WEATHER_TOOL],
            tool_executor=mock_executor,
        )

    assert received_args[0] == {"city": "Lyon"}


@pytest.mark.asyncio
async def test_tool_loop_args_as_json_string() -> None:
    """tool_loop parse les arguments en string JSON (certains modèles locaux sérialisent en str)."""
    from jarvis.providers.llm.local import OllamaProvider

    # Arguments en string JSON, pas en dict
    resp1 = _tool_call_response("get_weather", json.dumps({"city": "Marseille"}))
    resp2 = _text_response("Ensoleillé à Marseille.")
    mock_ctx, _ = _make_httpx_mock(resp1, resp2)

    received_args: list[dict] = []

    async def mock_executor(name: str, args: dict) -> str:
        received_args.append(args)
        return "ensoleillé"

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        await provider.tool_loop(
            messages=[{"role": "user", "content": "Météo Marseille ?"}],
            system="sys",
            tools=[_WEATHER_TOOL],
            tool_executor=mock_executor,
        )

    # Les args doivent être un dict, pas une string
    assert isinstance(received_args[0], dict)
    assert received_args[0].get("city") == "Marseille"


# ── tool_loop — robustesse ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_loop_unknown_tool_no_crash() -> None:
    """tool_loop : un tool_call vers un outil inexistant injecte une erreur sans crasher."""
    from jarvis.providers.llm.local import OllamaProvider

    resp1 = _tool_call_response("outil_qui_nexiste_pas", {"param": "val"})
    resp2 = _text_response("Je ne peux pas utiliser cet outil.")
    mock_ctx, mock_client = _make_httpx_mock(resp1, resp2)

    executor_called = False

    async def mock_executor(name: str, args: dict) -> str:
        nonlocal executor_called
        executor_called = True
        return "ne devrait pas être appelé"

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "Fais quelque chose."}],
            system="sys",
            tools=[_WEATHER_TOOL],  # seul "get_weather" est connu
            tool_executor=mock_executor,
        )

    # Pas de crash, executor non appelé, erreur injectée dans le second appel
    assert not executor_called
    assert isinstance(result, str)
    assert mock_client.post.call_count == 2
    # Le second appel doit contenir le message d'erreur dans les messages
    second_call_args = mock_client.post.call_args_list[1]
    messages_sent = second_call_args.kwargs["json"]["messages"]
    tool_messages = [m for m in messages_sent if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "inconnu" in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_tool_loop_executor_exception_no_crash() -> None:
    """tool_loop : une exception dans l'executor est capturée et renvoyée comme erreur."""
    from jarvis.providers.llm.local import OllamaProvider

    resp1 = _tool_call_response("get_weather", {"city": "Bordeaux"})
    resp2 = _text_response("Je n'ai pas pu obtenir la météo.")
    mock_ctx, mock_client = _make_httpx_mock(resp1, resp2)

    async def failing_executor(name: str, args: dict) -> str:
        raise RuntimeError("Service météo indisponible")

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "Météo Bordeaux ?"}],
            system="sys",
            tools=[_WEATHER_TOOL],
            tool_executor=failing_executor,
        )

    assert isinstance(result, str)
    assert mock_client.post.call_count == 2
    second_call_args = mock_client.post.call_args_list[1]
    messages_sent = second_call_args.kwargs["json"]["messages"]
    tool_messages = [m for m in messages_sent if m.get("role") == "tool"]
    assert "Erreur" in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_tool_loop_max_iterations_respected() -> None:
    """tool_loop respecte _MAX_TOOL_ITERATIONS et retourne un message d'échec lisible."""
    from jarvis.providers.llm.local import _MAX_TOOL_ITERATIONS, OllamaProvider

    always_tool_call = _tool_call_response("echo", {"text": "ping"})
    mock_ctx, mock_client = _make_httpx_mock(*([always_tool_call] * (_MAX_TOOL_ITERATIONS + 1)))

    async def mock_executor(name: str, args: dict) -> str:
        return "pong"

    with patch("jarvis.providers.llm.local.httpx.AsyncClient", return_value=mock_ctx):
        provider = OllamaProvider()
        result = await provider.tool_loop(
            messages=[{"role": "user", "content": "ping"}],
            system="sys",
            tools=[_ECHO_TOOL],
            tool_executor=mock_executor,
        )

    assert "étapes" in result
    assert mock_client.post.call_count == _MAX_TOOL_ITERATIONS
