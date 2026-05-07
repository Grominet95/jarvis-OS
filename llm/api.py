from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

import anthropic
from openai import AsyncOpenAI
from loguru import logger
from mistralai.client import Mistral

from config.settings import settings
from core.tracking import UsageEntry, calculate_cost, tracker
from llm.base import LLMProvider

_MAX_TOOL_ITERATIONS = 20


@dataclass
class ToolCapture:
    """Collecte les tool_use blocks émis pendant un stream Anthropic."""
    calls: list[tuple[str, str, dict]] = field(default_factory=list)
    stop_reason: str = "end_turn"


class AnthropicProvider(LLMProvider):
    """Provider Anthropic Claude via SDK officiel."""

    def __init__(self, max_tokens: int = 2048, model: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.anthropic_model
        self._max_tokens = max_tokens

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
            "anthropic", self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        tracker.track(UsageEntry(
            timestamp=datetime.now().isoformat(),
            provider="anthropic",
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
            context=context,
        ))
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
        import json as _json
        _input: dict[int, str] = {}            # index → partial_json accumulé
        _meta: dict[int, tuple[str, str]] = {} # index → (tool_id, tool_name)

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
                "anthropic", self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            tracker.track(UsageEntry(
                timestamp=datetime.now().isoformat(),
                provider="anthropic",
                model=self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost_usd=cost,
                context=context,
            ))

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
    """Provider Mistral API via SDK officiel."""

    def __init__(self) -> None:
        self._client = Mistral(api_key=settings.mistral_api_key)
        self._model = settings.mistral_model

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        # Mistral intègre le system message dans la liste messages
        full_messages = [{"role": "system", "content": system}, *messages]

        if stream:
            return self._stream(full_messages)

        response = await self._client.chat.complete_async(
            model=self._model,
            messages=full_messages,
        )
        text = response.choices[0].message.content
        logger.debug("Mistral complete", model=self._model)
        return text

    async def _stream(self, messages: list[dict]) -> AsyncIterator[str]:
        stream = await self._client.chat.stream_async(
            model=self._model,
            messages=messages,
        )
        async for event in stream:
            delta = event.data.choices[0].delta.content
            if delta:
                yield delta

    async def health_check(self) -> bool:
        try:
            await self._client.chat.complete_async(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error("Mistral health check failed", error=str(e))
            return False


class OpenAIProvider(LLMProvider):
    """Provider OpenAI API via SDK officiel."""

    def __init__(self, model: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = model or settings.openai_model

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system}, *messages]

        if stream:
            return self._stream(full_messages)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
        )
        text = response.choices[0].message.content or ""
        logger.debug("OpenAI complete", model=self._model)
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


def get_api_provider(backend: str = "anthropic", max_tokens: int = 2048) -> LLMProvider:
    """Retourne le provider API selon le backend demandé."""
    if backend == "mistral":
        return MistralProvider()
    if backend == "openai":
        return OpenAIProvider()
    return AnthropicProvider(max_tokens=max_tokens)
