from __future__ import annotations

import asyncio
import json as _json
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

import anthropic
from google.genai import types as _t
from loguru import logger
from openai import AsyncOpenAI

from jarvis.kernel.contracts import UsageTracker
from jarvis.kernel.schemas import ToolCapture, UsageEntry, calculate_cost
from jarvis.kernel.settings import settings
from jarvis.providers.llm.base import LLMProvider

_MAX_TOOL_ITERATIONS = 20

# CYCLE 1 (CDC §C.1.3) — bouclé : aucun import depuis `jarvis.engine.*`.
# Le tracker est reçu par constructeur (DI), typé via le Protocol
# `jarvis.kernel.contracts.UsageTracker`. Câblage dans `bootstrap.build()`.


# ── Helpers de conversion de format ──────────────────────────────────────────


def _claude_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convertit le schéma d'outils Claude (input_schema) vers le format OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """Convertit les messages Anthropic (tool_use / tool_result) vers le format OpenAI.

    Nécessaire pour la passe de synthèse où agent.py injecte des blocs Anthropic
    dans l'historique avant un appel complete() sans outils (Mistral).
    """
    result: list[dict] = []
    for msg in messages:
        role: str = msg["role"]
        content: Any = msg.get("content", "")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        has_tool_use = any(b.get("type") == "tool_use" for b in content)
        has_tool_result = any(b.get("type") == "tool_result" for b in content)

        if has_tool_use:
            text = " ".join(b["text"] for b in content if b.get("type") == "text" and b.get("text"))
            tool_calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": _json.dumps(b.get("input", {})),
                    },
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            result.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": tool_calls,
                }
            )
        elif has_tool_result:
            # Chaque tool_result devient un message "tool" séparé (rôle OpenAI)
            for block in content:
                if block.get("type") == "tool_result":
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        }
                    )
        else:
            text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
            result.append({"role": role, "content": text})

    return result


# ── Providers ─────────────────────────────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    """Provider Anthropic Claude via SDK officiel."""

    def __init__(
        self,
        max_tokens: int = 2048,
        model: str | None = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        self._model = model or settings.anthropic_model
        self._max_tokens = max_tokens
        self._tracker = tracker

    def set_tracker(self, tracker: UsageTracker) -> None:
        """Injection post-construction (utilisé pour providers créés par factory)."""
        self._tracker = tracker

    @property
    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        if stream:
            return self._stream(kwargs)

        response = await self._client.messages.create(**kwargs)
        text = response.content[0].text
        logger.debug("Anthropic complete", model=self._model, tokens=response.usage.output_tokens)
        cost = calculate_cost(
            "anthropic",
            self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        if self._tracker is not None:
            self._tracker.track(
                UsageEntry(
                    timestamp=datetime.now().isoformat(),
                    provider="anthropic",
                    model=self._model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cost_usd=cost,
                    context=context,
                )
            )
        return text

    async def _stream(self, kwargs: dict) -> AsyncIterator[str]:
        async with self._client.messages.stream(**kwargs) as stream:
            async for chunk in stream.text_stream:
                yield chunk

    def stream_with_capture(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
    ) -> tuple[AsyncIterator[str], ToolCapture]:
        """Stream les tokens texte ET capture les tool_use blocks après épuisement.

        Le ToolCapture est populé dès que l'itérateur retourné est entièrement consommé.
        """
        capture = ToolCapture()
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return self._stream_capturing(kwargs, capture), capture

    async def _stream_capturing(self, kwargs: dict, capture: ToolCapture) -> AsyncIterator[str]:
        """Stream text via raw events + peuple capture dès que chaque bloc tool_use est complet.

        Traite tous les événements en une passe — pas de get_final_message() séparé.
        capture.calls est peuplé dès content_block_stop pour chaque outil, ce qui permet
        à _pipe() de démarrer la task outil aussitôt que le stream texte est épuisé.
        """
        _input: dict[int, str] = {}  # index → partial_json accumulé
        _meta: dict[int, tuple[str, str]] = {}  # index → (tool_id, tool_name)

        async with self._client.messages.stream(**kwargs) as s:
            async for event in s:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield delta.text
                    elif delta.type == "input_json_delta" and delta.partial_json:
                        _input[event.index] = _input.get(event.index, "") + delta.partial_json
                elif event.type == "content_block_start":
                    cb = event.content_block
                    if cb.type == "tool_use":
                        _meta[event.index] = (cb.id, cb.name)
                        _input[event.index] = ""
                elif event.type == "content_block_stop":
                    if event.index in _meta:
                        tool_id, tool_name = _meta[event.index]
                        raw = _input.get(event.index, "{}")
                        try:
                            tool_input = _json.loads(raw)
                        except _json.JSONDecodeError:
                            tool_input = {}
                        capture.calls.append((tool_id, tool_name, tool_input))
                elif event.type == "message_delta":
                    sr = getattr(event.delta, "stop_reason", None)
                    if sr:
                        capture.stop_reason = sr

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Boucle tool use : appels non-streaming jusqu'à stop_reason != tool_use."""
        current = list(messages)

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=current,
                tools=tools,
            )
            cost = calculate_cost(
                "anthropic",
                self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            if self._tracker is not None:
                self._tracker.track(
                    UsageEntry(
                        timestamp=datetime.now().isoformat(),
                        provider="anthropic",
                        model=self._model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        cost_usd=cost,
                        context=context,
                    )
                )

            if response.stop_reason != "tool_use":
                text = "".join(
                    block.text
                    for block in response.content
                    if hasattr(block, "text") and block.text
                )
                logger.debug("Tool loop done", iterations=iteration + 1)
                return text

            # Sépare le contenu assistant et collecte les appels
            assistant_content = []
            tool_calls: list[tuple[str, str, dict]] = []  # (id, name, input)

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    tool_calls.append((block.id, block.name, block.input))

            # Exécution parallèle de tous les outils
            results = await asyncio.gather(
                *(tool_executor(name, inputs) for _, name, inputs in tool_calls)
            )
            logger.debug("Tools called", names=[n for _, n, _ in tool_calls])

            tool_results = [
                {"type": "tool_result", "tool_use_id": tool_id, "content": result}
                for (tool_id, _, _), result in zip(tool_calls, results, strict=True)
            ]

            current = current + [
                {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": tool_results},
            ]

        logger.warning("Tool loop max iterations reached", max=_MAX_TOOL_ITERATIONS)
        return "Je n'ai pas pu terminer — trop d'étapes."

    async def health_check(self) -> bool:
        try:
            await self._client.messages.create(
                model=self._model,
                max_tokens=1,
                system="ping",
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error("Anthropic health check failed", error=str(e))
            return False


class MistralProvider(LLMProvider):
    """Provider Mistral via l'API OpenAI-compatible.

    Supporte le function calling natif (supports_tools=True) via le format OpenAI.
    Les messages Anthropic (tool_use/tool_result) sont convertis automatiquement
    par _messages_to_openai() avant chaque appel, ce qui permet à agent.synthesize()
    de fonctionner sans modification de core/.
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.mistral_api_key.get_secret_value(),
            base_url="https://api.mistral.ai/v1",
        )
        self._model = settings.mistral_model

    @property
    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system}, *_messages_to_openai(messages)]

        if stream:
            return self._stream(full_messages)

        kwargs: dict = {"model": self._model, "messages": full_messages}
        if tools:
            kwargs["tools"] = _claude_tools_to_openai(tools)
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        logger.debug("Mistral complete", model=self._model)
        return text

    async def _stream(self, messages: list[dict]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def stream_with_capture(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
    ) -> tuple[AsyncIterator[str], ToolCapture]:
        """Stream + capture des tool calls Mistral (OpenAI streaming avec tool_call deltas).

        ToolCapture.calls est peuplé à l'épuisement du stream ; la passe de synthèse
        appelle ensuite complete() avec l'historique Anthropic converti via _messages_to_openai.
        """
        capture = ToolCapture()
        full_messages = [{"role": "system", "content": system}, *_messages_to_openai(messages)]
        openai_tools = _claude_tools_to_openai(tools) if tools else None
        return self._stream_capturing(full_messages, openai_tools, capture), capture

    async def _stream_capturing(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        capture: ToolCapture,
    ) -> AsyncIterator[str]:
        """Stream texte + accumule les tool_call deltas ; peuple capture à la fin."""
        kwargs: dict = {"model": self._model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        _calls: dict[int, dict] = {}  # index → {id, name, arguments}

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in _calls:
                        _calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        _calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            _calls[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            _calls[idx]["arguments"] += tc.function.arguments

            if choice.finish_reason:
                capture.stop_reason = choice.finish_reason

        for idx in sorted(_calls.keys()):
            call = _calls[idx]
            try:
                tool_input = _json.loads(call["arguments"]) if call["arguments"] else {}
            except _json.JSONDecodeError:
                tool_input = {}
            capture.calls.append((call["id"], call["name"], tool_input))

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Boucle tool use Mistral (function calling OpenAI-compatible)."""
        current: list[dict] = [
            {"role": "system", "content": system},
            *_messages_to_openai(messages),
        ]
        openai_tools = _claude_tools_to_openai(tools)

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=current,
                tools=openai_tools,
                tool_choice="auto",
            )
            choice = response.choices[0]

            if choice.finish_reason != "tool_calls":
                logger.debug("Mistral tool loop done", iterations=iteration + 1)
                return choice.message.content or ""

            tc_list = choice.message.tool_calls or []
            current.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tc_list
                    ],
                }
            )

            parsed: list[tuple[str, str, dict]] = []
            for tc in tc_list:
                try:
                    inp = _json.loads(tc.function.arguments or "{}")
                except _json.JSONDecodeError:
                    inp = {}
                parsed.append((tc.id, tc.function.name, inp))

            results = await asyncio.gather(*(tool_executor(name, inp) for _, name, inp in parsed))
            logger.debug("Mistral tools called", names=[n for _, n, _ in parsed])

            for (tool_id, _, _), result in zip(parsed, results, strict=True):
                current.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result,
                    }
                )

        logger.warning("Mistral tool loop max iterations reached", max=_MAX_TOOL_ITERATIONS)
        return "Je n'ai pas pu terminer — trop d'étapes."

    async def health_check(self) -> bool:
        try:
            await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.error("Mistral health check failed", error=str(e))
            return False


class GeminiProvider(LLMProvider):
    """Provider Google Gemini via SDK google-genai.

    Supporte le function calling natif (supports_tools=True).
    La passe de synthèse post-outils passe par complete() qui convertit
    automatiquement les messages Anthropic (tool_use/tool_result) vers les
    Content/Part Gemini via _messages_to_gemini().

    Clé API lue depuis la variable d'environnement GEMINI_API_KEY.
    Modèle configurable via GEMINI_MODEL (défaut : gemini-2.0-flash).
    """

    def __init__(self, model: str | None = None, max_tokens: int = 4096) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError("google-genai requis : pip install google-genai") from exc
        api_key = os.environ.get("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key)
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._max_tokens = max_tokens

    @property
    def supports_tools(self) -> bool:
        return True

    # ── Helpers internes ────────────────────────────────────────────────────

    def _json_schema_to_gemini(self, schema: dict) -> object:
        """Convertit un schéma JSON (format Claude) vers types.Schema Gemini (récursif)."""

        type_map: dict[str, Any] = {
            "string": _t.Type.STRING,
            "number": _t.Type.NUMBER,
            "integer": _t.Type.INTEGER,
            "boolean": _t.Type.BOOLEAN,
            "array": _t.Type.ARRAY,
            "object": _t.Type.OBJECT,
        }
        schema_type = type_map.get(schema.get("type", "string"), _t.Type.STRING)
        kwargs: dict = {"type": schema_type}

        if desc := schema.get("description"):
            kwargs["description"] = desc
        if props := schema.get("properties"):
            kwargs["properties"] = {k: self._json_schema_to_gemini(v) for k, v in props.items()}
        if req := schema.get("required"):
            kwargs["required"] = req
        if items := schema.get("items"):
            kwargs["items"] = self._json_schema_to_gemini(items)
        if enum := schema.get("enum"):
            kwargs["enum"] = enum

        return _t.Schema(**kwargs)

    def _claude_tools_to_gemini(self, tools: list[dict]) -> list[Any]:
        """Convertit le schéma d'outils Claude vers une liste de Tool Gemini."""

        declarations = [
            _t.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=self._json_schema_to_gemini(t.get("input_schema", {})),
            )
            for t in tools
        ]
        return [_t.Tool(function_declarations=declarations)]

    def _build_config(self, system: str, tools: list[dict] | None) -> object:
        """Construit GenerateContentConfig avec système et outils optionnels."""

        config_kwargs: dict = {
            "system_instruction": system,
            "max_output_tokens": self._max_tokens,
        }
        if tools:
            config_kwargs["tools"] = self._claude_tools_to_gemini(tools)
        return _t.GenerateContentConfig(**config_kwargs)

    def _messages_to_gemini(self, messages: list[dict]) -> list[Any]:
        """Convertit les messages (format Anthropic ou simple) vers des Content Gemini.

        Gère la passe de synthèse où agent.py injecte des blocs tool_use / tool_result
        dans l'historique. Construit la map id→name en amont pour les FunctionResponse
        qui nécessitent le nom de la fonction, pas l'id.
        """

        # Passe 1 : map tool_use_id → tool_name pour résoudre les tool_result
        id_to_name: dict[str, str] = {}
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_use":
                        id_to_name[block["id"]] = block["name"]

        result: list[Any] = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            content: Any = msg.get("content", "")

            if isinstance(content, str):
                result.append(_t.Content(role=role, parts=[_t.Part(text=content)]))
                continue

            has_tool_use = any(b.get("type") == "tool_use" for b in content)
            has_tool_result = any(b.get("type") == "tool_result" for b in content)

            if has_tool_use or has_tool_result:
                model_parts: list[Any] = []
                user_parts: list[Any] = []

                for block in content:
                    btype = block.get("type")
                    if btype == "text" and block.get("text"):
                        model_parts.append(_t.Part(text=block["text"]))
                    elif btype == "tool_use":
                        model_parts.append(
                            _t.Part(
                                function_call=_t.FunctionCall(
                                    name=block["name"],
                                    args=block.get("input", {}),
                                )
                            )
                        )
                    elif btype == "tool_result":
                        tool_name = id_to_name.get(block["tool_use_id"], block["tool_use_id"])
                        user_parts.append(
                            _t.Part(
                                function_response=_t.FunctionResponse(
                                    name=tool_name,
                                    response={"result": block.get("content", "")},
                                )
                            )
                        )

                if model_parts:
                    result.append(_t.Content(role="model", parts=model_parts))
                if user_parts:
                    result.append(_t.Content(role="user", parts=user_parts))
            else:
                text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
                result.append(_t.Content(role=role, parts=[_t.Part(text=text)]))

        return result

    # ── Interface publique ───────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        contents = self._messages_to_gemini(messages)
        config = self._build_config(system, tools)

        if stream:
            return self._stream(contents, config)

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )
        text: str = response.text or ""
        logger.debug("Gemini complete", model=self._model)
        return text

    async def _stream(self, contents: list[Any], config: object) -> AsyncIterator[str]:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    def stream_with_capture(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
    ) -> tuple[AsyncIterator[str], ToolCapture]:
        """Stream + capture des function calls Gemini.

        ToolCapture.calls est peuplé dès que chunk.function_calls est non-vide
        (dernier chunk du stream). La synthèse passe par complete() avec conversion
        automatique de l'historique Anthropic via _messages_to_gemini.
        """
        capture = ToolCapture()
        contents = self._messages_to_gemini(messages)
        config = self._build_config(system, tools)
        return self._stream_capturing(contents, config, capture), capture

    async def _stream_capturing(
        self,
        contents: list[Any],
        config: object,
        capture: ToolCapture,
    ) -> AsyncIterator[str]:
        """Stream texte + capture les function_calls Gemini en fin de stream."""
        seen_keys: set[str] = set()
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text
            if chunk.function_calls:
                for fc in chunk.function_calls:
                    if fc.name not in seen_keys:
                        seen_keys.add(fc.name)
                        call_id = f"call_{fc.name}_{uuid.uuid4().hex[:8]}"
                        capture.calls.append((call_id, fc.name, dict(fc.args) if fc.args else {}))
                        capture.stop_reason = "tool_use"

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Boucle tool use Gemini (function calling natif)."""

        contents: list[Any] = self._messages_to_gemini(messages)
        config = self._build_config(system, tools)

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )

            function_calls = response.function_calls or []
            if not function_calls:
                text: str = response.text or ""
                logger.debug("Gemini tool loop done", iterations=iteration + 1)
                return text

            # Ajoute le contenu modèle (avec function_call parts) à l'historique
            candidate = response.candidates[0]
            contents.append(candidate.content)

            tool_calls_data = [(fc.name, dict(fc.args) if fc.args else {}) for fc in function_calls]
            results = await asyncio.gather(
                *(tool_executor(name, inp) for name, inp in tool_calls_data)
            )
            logger.debug("Gemini tools called", names=[n for n, _ in tool_calls_data])

            function_responses = [
                _t.Part(
                    function_response=_t.FunctionResponse(
                        name=name,
                        response={"result": result},
                    )
                )
                for (name, _), result in zip(tool_calls_data, results, strict=True)
            ]
            contents.append(_t.Content(role="user", parts=function_responses))

        logger.warning("Gemini tool loop max iterations reached", max=_MAX_TOOL_ITERATIONS)
        return "Je n'ai pas pu terminer — trop d'étapes."

    async def health_check(self) -> bool:
        try:
            await self._client.aio.models.generate_content(
                model=self._model,
                contents="ping",
            )
            return True
        except Exception as e:
            logger.error("Gemini health check failed", error=str(e))
            return False


class OpenAIProvider(LLMProvider):
    """Provider OpenAI API via SDK officiel.

    Supporte le function calling natif (supports_tools=True) via le format OpenAI.
    Les messages Anthropic (tool_use/tool_result) sont convertis automatiquement
    par _messages_to_openai() avant chaque appel, ce qui permet à agent.synthesize()
    et au gateway double-passe de fonctionner sans modification de engine/.
    """

    def __init__(
        self,
        model: str | None = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._model = model or settings.openai_model
        self._tracker = tracker

    def set_tracker(self, tracker: UsageTracker) -> None:
        """Injection post-construction (utilisé pour providers créés par factory)."""
        self._tracker = tracker

    @property
    def supports_tools(self) -> bool:
        return True

    def _track(self, response: Any, context: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None or self._tracker is None:
            return
        cost = calculate_cost(
            "openai",
            self._model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
        self._tracker.track(
            UsageEntry(
                timestamp=datetime.now().isoformat(),
                provider="openai",
                model=self._model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                cost_usd=cost,
                context=context,
            )
        )

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system}, *_messages_to_openai(messages)]

        if stream:
            return self._stream(full_messages)

        kwargs: dict = {"model": self._model, "messages": full_messages}
        if tools:
            kwargs["tools"] = _claude_tools_to_openai(tools)
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        logger.debug("OpenAI complete", model=self._model)
        self._track(response, context)
        return text

    async def _stream(self, messages: list[dict]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def stream_with_capture(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
    ) -> tuple[AsyncIterator[str], ToolCapture]:
        """Stream texte + capture des tool calls OpenAI (deltas streaming).

        ToolCapture.calls est peuplé à l'épuisement du stream ; la passe de synthèse
        appelle ensuite complete() avec l'historique Anthropic converti.
        """
        capture = ToolCapture()
        full_messages = [{"role": "system", "content": system}, *_messages_to_openai(messages)]
        openai_tools = _claude_tools_to_openai(tools) if tools else None
        return self._stream_capturing(full_messages, openai_tools, capture), capture

    async def _stream_capturing(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        capture: ToolCapture,
    ) -> AsyncIterator[str]:
        """Stream texte + accumule les tool_call deltas ; peuple capture à la fin."""
        kwargs: dict = {"model": self._model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        _calls: dict[int, dict] = {}  # index → {id, name, arguments}

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in _calls:
                        _calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        _calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            _calls[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            _calls[idx]["arguments"] += tc.function.arguments

            if choice.finish_reason:
                capture.stop_reason = choice.finish_reason

        for idx in sorted(_calls.keys()):
            call = _calls[idx]
            try:
                tool_input = _json.loads(call["arguments"]) if call["arguments"] else {}
            except _json.JSONDecodeError:
                tool_input = {}
            capture.calls.append((call["id"], call["name"], tool_input))

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Boucle tool use OpenAI (function calling natif)."""
        current: list[dict] = [
            {"role": "system", "content": system},
            *_messages_to_openai(messages),
        ]
        openai_tools = _claude_tools_to_openai(tools)

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=current,
                tools=openai_tools,
                tool_choice="auto",
            )
            self._track(response, context)
            choice = response.choices[0]

            if choice.finish_reason != "tool_calls":
                logger.debug("OpenAI tool loop done", iterations=iteration + 1)
                return choice.message.content or ""

            tc_list = choice.message.tool_calls or []
            current.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tc_list
                    ],
                }
            )

            parsed: list[tuple[str, str, dict]] = []
            for tc in tc_list:
                try:
                    inp = _json.loads(tc.function.arguments or "{}")
                except _json.JSONDecodeError:
                    inp = {}
                parsed.append((tc.id, tc.function.name, inp))

            results = await asyncio.gather(*(tool_executor(name, inp) for _, name, inp in parsed))
            logger.debug("OpenAI tools called", names=[n for _, n, _ in parsed])

            for (tool_id, _, _), result in zip(parsed, results, strict=True):
                current.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result,
                    }
                )

        logger.warning("OpenAI tool loop max iterations reached", max=_MAX_TOOL_ITERATIONS)
        return "Je n'ai pas pu terminer — trop d'étapes."

    async def health_check(self) -> bool:
        try:
            await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.error("OpenAI health check failed", error=str(e))
            return False


def get_api_provider(
    backend: str = "anthropic",
    max_tokens: int = 2048,
    model: str | None = None,
    tracker: UsageTracker | None = None,
) -> LLMProvider:
    """Retourne le provider API selon le backend demandé.

    `tracker` est passé aux providers Anthropic et OpenAI (qui poussent une
    UsageEntry vers le tracker). Mistral l'ignore pour l'instant.
    `model` surcharge le modèle par défaut du backend (None = modèle .env).
    """
    if backend == "gemini":
        return GeminiProvider(model=model, max_tokens=max_tokens)
    if backend == "mistral":
        return MistralProvider()
    if backend == "openai":
        return OpenAIProvider(model=model, tracker=tracker)
    return AnthropicProvider(max_tokens=max_tokens, model=model, tracker=tracker)
