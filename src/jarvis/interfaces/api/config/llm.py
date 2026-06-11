"""LLM status + Ollama API — Phase E §E.1.3.

Routes :
  - GET  /api/config/llm-status — provider LLM actif réel (l'instance vivante).
  - GET  /api/ollama/models — modèles installés localement.
  - POST /api/ollama/pull — télécharge un modèle (streaming SSE).
"""

from __future__ import annotations

import json as _json
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jarvis.kernel.settings import settings as _s

router = APIRouter()


@router.get("/api/config/llm-status")
async def get_llm_status(request: Request) -> dict:
    """Provider LLM actif réel (pas le réglage .env — l'instance vivante dans le gateway).

    Utile pour vérifier d'un coup d'œil quel cerveau répond sans redémarrer.
    """

    def _describe(obj: object) -> dict[str, str]:
        cls = type(obj).__name__
        model = (
            getattr(obj, "_model", None)
            or getattr(obj, "model", None)
            or getattr(obj, "ollama_model", None)
            or "?"
        )
        return {"provider": cls, "model": str(model)}

    gw = getattr(request.app.state, "gateway", None)
    vgw = getattr(request.app.state, "voice_gateway", None)
    worker = getattr(request.app.state, "worker", None)

    result: dict[str, object] = {
        "setting": _s.llm_provider,
        "gateway": _describe(gw._agent._llm) if gw else None,
        "voice_gateway": _describe(vgw._agent._llm) if vgw else None,
        "worker": _describe(worker._llm) if worker else None,
    }

    recall = getattr(gw, "_recall", None) if gw else None
    result["recall"] = _describe(recall._llm) if recall else None

    pe = getattr(request.app.state, "proactive_engine", None)
    gen = getattr(pe, "_generator", None) if pe else None
    result["initiative_generator"] = _describe(gen._llm) if gen else None

    return result


@router.get("/api/ollama/models")
async def get_ollama_models() -> dict:
    """Liste les modèles téléchargés sur le serveur Ollama local."""
    base_url = _s.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return {"available": True, "models": data.get("models", [])}
    except Exception:
        return {"available": False, "models": []}


class OllamaPullBody(BaseModel):
    model: str


@router.post("/api/ollama/pull")
async def pull_ollama_model(body: OllamaPullBody) -> StreamingResponse:
    """Télécharge un modèle Ollama en streaming SSE (progress events)."""
    base_url = _s.ollama_base_url.rstrip("/")

    async def _stream() -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/pull",
                    json={"name": body.model, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield f"data: {line}\n\n"
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield 'data: {"done":true}\n\n'

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
