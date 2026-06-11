from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from jarvis.interfaces.api import deezer as _dz
from jarvis.interfaces.api import local_music as _lm
from jarvis.interfaces.api import spotify as _sp
from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/music")


async def _get_state() -> dict:
    provider = settings.music_provider or ""
    if provider == "spotify":
        state = await _sp._get_player_state()
    elif provider == "deezer":
        state = await _dz._get_player_state()
    elif provider == "local":
        state = await _lm._get_player_state()
    else:
        return {"provider": None, "connected": False}
    state["provider"] = provider
    return state


async def _action(action: str) -> JSONResponse:
    provider = settings.music_provider or ""
    if not provider:
        return JSONResponse({"ok": False, "error": "no_provider"}, status_code=400)

    if provider == "spotify":
        mapping = {
            "play": _sp.play,
            "pause": _sp.pause,
            "next": _sp.next_track,
            "prev": _sp.previous_track,
        }
    elif provider == "deezer":
        mapping = {
            "play": _dz.play,
            "pause": _dz.pause,
            "next": _dz.next_track,
            "prev": _dz.previous_track,
        }
    elif provider == "local":
        mapping = {
            "play": _lm.play,
            "pause": _lm.pause,
            "next": _lm.next_track,
            "prev": _lm.previous_track,
        }
    else:
        return JSONResponse({"ok": False, "error": "unknown_provider"}, status_code=400)

    fn = mapping.get(action)
    if fn is None:
        return JSONResponse({"ok": False, "error": "unknown_action"}, status_code=400)
    return await fn()


@router.get("/status")
async def get_music_status() -> JSONResponse:
    return JSONResponse(await _get_state())


@router.get("/provider-status")
async def get_provider_status() -> JSONResponse:
    provider = settings.music_provider or ""
    if not provider:
        return JSONResponse({"provider": None, "connected": False})
    state = await _get_state()
    return JSONResponse({"provider": provider, "connected": state.get("connected", False)})


@router.post("/play")
async def music_play() -> JSONResponse:
    return await _action("play")


@router.post("/pause")
async def music_pause() -> JSONResponse:
    return await _action("pause")


@router.post("/next")
async def music_next() -> JSONResponse:
    return await _action("next")


@router.post("/prev")
async def music_prev() -> JSONResponse:
    return await _action("prev")
