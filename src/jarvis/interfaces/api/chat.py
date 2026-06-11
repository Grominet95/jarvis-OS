from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from livekit.api import (
    AccessToken,
    CreateAgentDispatchRequest,
    CreateRoomRequest,
    LiveKitAPI,
    VideoGrants,
)
from pydantic import BaseModel

from jarvis.engine.background.notifications import broadcast_event
from jarvis.engine.background.worker import BackgroundTask
from jarvis.engine.router import RouteEnum
from jarvis.providers.audio.tts import tts_engine

router = APIRouter()


# ── Tools API ─────────────────────────────────────────────────────────────────


@router.get("/api/tools")
async def list_tools_endpoint(request: Request) -> list[dict]:
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        return []
    return [
        {"name": s.get("name", ""), "description": s.get("description", "")}
        for s in registry.core_schemas()
    ]


class ToolExecuteRequest(BaseModel):
    tool: str
    params: dict = {}


@router.post("/api/tools/execute")
async def execute_tool(body: ToolExecuteRequest, request: Request) -> dict:
    """Bridge générique — le voice agent LiveKit appelle les outils Jarvis via cet endpoint."""
    registry = request.app.state.tool_registry
    result = await registry.call(body.tool, body.params)
    return {
        "success": not result.is_error,
        "result": result.content,
    }


# ── Voice API ─────────────────────────────────────────────────────────────────


@router.post("/api/voice/speak")
async def voice_speak(body: dict) -> dict:
    """
    Synthétise un texte en audio via TTS et retourne les bytes en base64.
    Le frontend joue l'audio directement avec Web Audio API.
    """
    import base64

    text = body.get("text", "").strip()
    if not text:
        return {"status": "error", "audio_b64": None}


    audio_bytes = await tts_engine.synthesize(text)
    return {
        "status": "ok",
        "audio_b64": base64.b64encode(audio_bytes).decode() if audio_bytes else None,
    }


class VoiceGenerateRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/api/voice/generate")
async def voice_generate(body: VoiceGenerateRequest, request: Request) -> StreamingResponse:
    """Bridge voix → gateway Jarvis.
    Même pipeline que le chat texte (Claude + outils + mémoire).
    Partage la session si session_id fourni.
    """
    import asyncio


    gateway = request.app.state.voice_gateway
    worker = request.app.state.worker
    orchestrator = getattr(request.app.state, "orchestrator", None)
    consolidation = request.app.state.consolidation
    auto_dream = request.app.state.auto_dream

    voice_msg = f"{body.message}\n[voix]"

    session, route, response = await gateway.handle(
        message=voice_msg,
        session_id=body.session_id,
        stream=True,
    )

    message_original = body.message

    async def _stream() -> AsyncGenerator[str, None]:
        full = ""
        try:
            if isinstance(response, str):
                full = response
                yield response
            else:
                async for chunk in response:
                    full += chunk
                    yield chunk
        except Exception as e:
            from loguru import logger as _log

            _log.error("Voice generate stream error", error=str(e))
            full = "Désolé, j'ai eu un souci."
            yield full

        session.add_message("assistant", full)

        if route is RouteEnum.BACKGROUND:
            worker.submit(BackgroundTask(session_id=str(session.id), instruction=message_original))
        elif route is RouteEnum.PROJECT and orchestrator:
            asyncio.create_task(
                orchestrator.create_and_run(message_original),
                name=f"voice-project-{str(session.id)[:8]}",
            )

        asyncio.create_task(
            consolidation._run_safe(user_message=message_original, assistant_message=full),
            name="voice-consolidation",
        )
        asyncio.create_task(
            auto_dream._run_micro_safe(user_message=message_original, assistant_message=full),
            name="voice-autodream",
        )

    return StreamingResponse(
        _stream(),
        media_type="text/plain",
        headers={"X-Session-Id": str(session.id)},
    )


@router.get("/api/voice/token")
async def get_voice_token(session_id: str | None = None) -> dict:  # noqa: ARG001
    """Génère un token LiveKit et dispatche l'agent jarvis dans la room."""
    import os
    import uuid


    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")

    room_name = f"jarvis-{uuid.uuid4().hex[:8]}"

    async with LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret) as lkapi:
        await lkapi.room.create_room(CreateRoomRequest(name=room_name))
        await lkapi.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(room=room_name, agent_name="jarvis")
        )

    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity("barth")
        .with_name("Barth")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    return {"token": token, "url": livekit_url}


# ── Internal broadcast ────────────────────────────────────────────────────────


@router.post("/internal/broadcast", include_in_schema=False)
async def internal_broadcast(request: Request) -> dict:
    """Endpoint interne utilisé par le voice agent pour envoyer des événements UI."""

    event = await request.json()
    await broadcast_event(event)
    return {"ok": True}
