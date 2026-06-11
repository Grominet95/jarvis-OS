from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
from loguru import logger

from jarvis.kernel.settings import settings
from jarvis.providers.llm.base import LLMProvider

# Strip <think>...</think> au cas où Ollama les laisse passer (fallback)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_MAX_TOOL_ITERATIONS = 8


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).lstrip()


def _claude_tools_to_ollama(tools: list[dict]) -> list[dict]:
    """Convertit le schéma d'outils interne Jarvis (format Claude) vers le format Ollama/OpenAI.

    Entrée  : [{"name": "...", "description": "...", "input_schema": {...}}]
    Sortie  : [{"type": "function", "function": {"name", "description", "parameters"}}]
    """
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


class OllamaProvider(LLMProvider):
    """Provider Ollama pour les modèles locaux (Qwen2.5/3, Llama 3.1+, Mistral…).

    supports_tools retourne True : Ollama accepte le champ "tools" pour les modèles
    compatibles (Qwen2.5/3, Llama 3.1+, Mistral…). Les modèles non-tool ignorent ce
    champ silencieusement — tool_loop retourne alors le texte brut sans exécuter d'outil.
    """

    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model

    @property
    def supports_tools(self) -> bool:
        """True — Ollama route le champ "tools" vers les modèles compatibles.

        Avertissement : un modèle non-tool (ex. petit Qwen3) ignorera les outils et
        ne produira jamais de tool_calls. tool_loop terminera normalement mais sans
        avoir exécuté d'outil — le résultat sera incomplet si une action était attendue.
        """
        return True

    def _payload(
        self,
        messages: list[dict],
        system: str,
        stream: bool,
        tools: list[dict] | None = None,
    ) -> dict:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
            "think": False,  # désactive le mode reasoning Qwen3 côté Ollama
            "options": {"temperature": 0.7},
        }
        if tools:
            payload["tools"] = _claude_tools_to_ollama(tools)
        return payload

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        payload = self._payload(messages, system, stream, tools)

        if stream:
            return self._stream(payload)

        # read=300 pour absorber le cold-start du modèle (chargement GPU/CPU ~100s+)
        _timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=_timeout) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            text: str = data["message"]["content"]
            logger.debug("Ollama complete", model=self._model, chars=len(text))
            return _strip_think(text)

    async def _stream(self, payload: dict) -> AsyncIterator[str]:
        _timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=_timeout) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                in_think = False
                think_buf = ""

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    delta: str = data.get("message", {}).get("content", "")

                    if delta:
                        # Filtre <think>...</think> token par token (sécurité)
                        think_buf += delta
                        output = ""
                        while think_buf:
                            if in_think:
                                end = think_buf.find("</think>")
                                if end == -1:
                                    think_buf = ""
                                    break
                                think_buf = think_buf[end + len("</think>") :]
                                in_think = False
                            else:
                                start = think_buf.find("<think>")
                                if start == -1:
                                    output += think_buf
                                    think_buf = ""
                                    break
                                output += think_buf[:start]
                                think_buf = think_buf[start + len("<think>") :]
                                in_think = True
                        if output:
                            yield output

                    if data.get("done"):
                        break

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Boucle tool use Ollama (function calling natif, /api/chat).

        Envoie le champ "tools" et traite message.tool_calls en multi-tours.
        Robustesse :
        - arguments dict ou string JSON selon le modèle — les deux sont gérés.
        - outil inconnu ou erreur d'exécution → tool result d'erreur renvoyé au modèle
          plutôt qu'une exception, pour permettre l'auto-correction.
        - arrêt automatique après _MAX_TOOL_ITERATIONS tours pour éviter les boucles.
        """
        tool_names = {t["name"] for t in tools}
        ollama_tools = _claude_tools_to_ollama(tools)
        current: list[dict] = [{"role": "system", "content": system}, *messages]

        async def _exec_one(call_id: str, name: str, args: dict) -> tuple[str, str]:
            if name not in tool_names:
                logger.warning("Ollama tool_loop: outil inconnu", name=name)
                return call_id, f"Erreur : outil '{name}' inconnu."
            try:
                result = await tool_executor(name, args)
                return call_id, result
            except Exception as exc:
                logger.warning("Ollama tool_loop: erreur exécution", name=name, error=str(exc))
                return call_id, f"Erreur lors de l'exécution de '{name}' : {exc}"

        for iteration in range(_MAX_TOOL_ITERATIONS):
            payload: dict = {
                "model": self._model,
                "messages": current,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.7},
                "tools": ollama_tools,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()

            msg: dict = data.get("message", {})
            raw_tool_calls: list[dict] = msg.get("tool_calls") or []

            if not raw_tool_calls:
                text: str = _strip_think(msg.get("content", ""))
                logger.debug("Ollama tool loop done", iterations=iteration + 1)
                return text

            # Réinjecte la réponse assistant avec ses tool_calls dans l'historique
            current.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": raw_tool_calls,
                }
            )

            # Parse les tool calls : arguments peuvent être dict OU string JSON
            parsed: list[tuple[str, str, dict]] = []
            for i, tc in enumerate(raw_tool_calls):
                fn = tc.get("function", {})
                tc_name: str = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                call_id: str = tc.get("id", f"call_{tc_name}_{iteration}_{i}")

                if isinstance(raw_args, str):
                    try:
                        tc_args: dict = json.loads(raw_args)
                    except json.JSONDecodeError:
                        tc_args = {}
                elif isinstance(raw_args, dict):
                    tc_args = raw_args
                else:
                    tc_args = {}

                parsed.append((call_id, tc_name, tc_args))

            results: list[tuple[str, str]] = await asyncio.gather(
                *(_exec_one(cid, n, a) for cid, n, a in parsed)
            )
            logger.debug("Ollama tools called", names=[n for _, n, _ in parsed])

            for _cid, result in results:
                current.append({"role": "tool", "content": result})

        logger.warning("Ollama tool loop max iterations reached", max=_MAX_TOOL_ITERATIONS)
        return "Je n'ai pas pu terminer — trop d'étapes."

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error("Ollama health check failed", error=str(e))
            return False
