from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config.settings import settings

router = APIRouter(prefix="/api/music")


@router.get("/status")
async def get_music_status() -> JSONResponse:
    provider = settings.music_provider or ""

    if provider == "spotify":
        from api.spotify import _get_player_state
        state = await _get_player_state()
    elif provider == "deezer":
        from api.deezer import _get_player_state
        state = await _get_player_state()
    elif provider == "local":
        from api.local_music import _get_player_state
        state = await _get_player_state()
    else:
        return JSONResponse({"provider": None, "connected": False})

    state["provider"] = provider
    return JSONResponse(state)


@router.get("/provider-status")
async def get_provider_status() -> JSONResponse:
    provider = settings.music_provider or ""
    if not provider:
        return JSONResponse({"provider": None, "connected": False})

    if provider == "spotify":
        from api.spotify import _get_player_state
        state = await _get_player_state()
    elif provider == "deezer":
        from api.deezer import _get_player_state
        state = await _get_player_state()
    elif provider == "local":
        from api.local_music import _get_player_state
        state = await _get_player_state()
    else:
        return JSONResponse({"provider": provider, "connected": False})

    return JSONResponse({"provider": provider, "connected": state.get("connected", False)})
