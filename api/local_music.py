from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/api/local-music")

_FIELDS = ["title", "artist", "album", "artworkURL", "playbackRate", "duration", "elapsedTime"]


async def _run(cmd: str, *args: str) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nowplaying-cli", cmd, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return stdout.decode().strip()
    except FileNotFoundError:
        logger.debug("nowplaying-cli not installed")
        return None
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug("nowplaying-cli error", error=str(e))
        return None


async def _get_player_state() -> dict:
    output = await _run("get", *_FIELDS)
    if output is None:
        return {"connected": False}

    lines = output.split("\n")
    if len(lines) < len(_FIELDS):
        return {"connected": True, "is_playing": False, "track": None}

    values = dict(zip(_FIELDS, lines))
    title = values.get("title", "")
    if not title or title == "null":
        return {"connected": True, "is_playing": False, "track": None}

    try:
        rate = float(values.get("playbackRate") or 0)
    except ValueError:
        rate = 0.0
    try:
        duration_ms = int(float(values.get("duration") or 0) * 1000)
    except ValueError:
        duration_ms = 0
    try:
        progress_ms = int(float(values.get("elapsedTime") or 0) * 1000)
    except ValueError:
        progress_ms = 0

    art = values.get("artworkURL", "")
    return {
        "connected": True,
        "is_playing": rate > 0,
        "track": title,
        "artist": values.get("artist", "") or "",
        "album": values.get("album", "") or "",
        "album_art": art if art and art != "null" else None,
        "progress_ms": progress_ms,
        "duration_ms": duration_ms,
    }


@router.get("/player")
async def get_player() -> JSONResponse:
    return JSONResponse(await _get_player_state())


@router.post("/play")
async def play() -> JSONResponse:
    await _run("play")
    return JSONResponse({"ok": True})

@router.post("/pause")
async def pause() -> JSONResponse:
    await _run("pause")
    return JSONResponse({"ok": True})

@router.post("/next")
async def next_track() -> JSONResponse:
    await _run("next")
    return JSONResponse({"ok": True})

@router.post("/previous")
async def previous_track() -> JSONResponse:
    await _run("previous")
    return JSONResponse({"ok": True})
