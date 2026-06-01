from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

import httpx
from loguru import logger

from config.settings import settings
from llm.base import LLMProvider

# Strip <think>...</think> au cas où Ollama les laisse passer (fallback)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


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

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            text: str = data["message"]["content"]
            logger.debug("Ollama complete", model=self._model, chars=len(text))
            return _strip_think(text)

    async def _stream(self, payload: dict) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=120.0) as client:
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

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error("Ollama health check failed", error=str(e))
            return False
