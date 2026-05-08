from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from config.settings import settings

router = APIRouter(prefix="/api/spotify")

_SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state streaming user-read-email user-read-private"
_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"


# ── Token management ──────────────────────────────────────────

def _token_path() -> Path:
    return Path(settings.spotify_token_path)


def _load_token() -> dict | None:
    p = _token_path()
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _save_token(data: dict) -> None:
    _token_path().write_text(json.dumps(data))


def _basic_auth() -> str:
    creds = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    return base64.b64encode(creds.encode()).decode()


async def _get_access_token() -> str | None:
    token = _load_token()
    if not token:
        return None

    if token.get("expires_at", 0) > time.time() + 60:
        return token["access_token"]

    # Refresh
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {_basic_auth()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
            },
        )
        if not resp.is_success:
            logger.error("Spotify token refresh failed", status=resp.status_code)
            return None

        new_token = resp.json()
        token["access_token"] = new_token["access_token"]
        token["expires_at"] = time.time() + new_token["expires_in"]
        if "refresh_token" in new_token:
            token["refresh_token"] = new_token["refresh_token"]
        _save_token(token)
        return token["access_token"]


# ── OAuth flow ────────────────────────────────────────────────

@router.get("/auth")
async def spotify_auth() -> RedirectResponse:
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": _SCOPES,
    }
    return RedirectResponse(f"{_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def spotify_callback(code: str | None = None, error: str | None = None) -> RedirectResponse:
    if error or not code:
        logger.error("Spotify OAuth error", error=error)
        return RedirectResponse("/?spotify_error=1")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {_basic_auth()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _save_token({
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data["expires_in"],
        })
        logger.info("Spotify token saved")

    return RedirectResponse("/?spotify_ok=1")


# ── Token for Web Playback SDK ────────────────────────────────

@router.get("/token")
async def get_token() -> JSONResponse:
    token = await _get_access_token()
    return JSONResponse({"token": token})


@router.post("/transfer")
async def transfer_playback(request: Request) -> JSONResponse:
    body = await request.json()
    device_id = body.get("device_id")
    if not device_id:
        return JSONResponse({"ok": False}, status_code=400)
    token = await _get_access_token()
    if not token:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.put(
                f"{_API_BASE}/me/player",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"device_ids": [device_id], "play": False},
            )
        return JSONResponse({"ok": resp.status_code in (200, 204)})
    except httpx.RequestError as e:
        logger.warning("Spotify transfer error", error=str(e))
        return JSONResponse({"ok": False})


# ── Player state ──────────────────────────────────────────────

async def _get_player_state() -> dict:
    token = await _get_access_token()
    if not token:
        return {"connected": False}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_API_BASE}/me/player",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException:
        logger.debug("Spotify player timeout")
        return {"connected": True, "is_playing": False, "track": None}
    except httpx.RequestError as e:
        logger.warning("Spotify player request error", error=str(e))
        return {"connected": False}

    if resp.status_code == 204:
        return {"connected": True, "is_playing": False, "track": None}

    if not resp.is_success:
        return {"connected": False}

    data = resp.json()
    item = data.get("item") or {}
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    images = (item.get("album") or {}).get("images", [])
    album_art = images[0]["url"] if images else None

    return {
        "connected": True,
        "is_playing": data.get("is_playing", False),
        "track": item.get("name", ""),
        "artist": artists,
        "album": (item.get("album") or {}).get("name", ""),
        "album_art": album_art,
        "progress_ms": data.get("progress_ms", 0),
        "duration_ms": item.get("duration_ms", 0),
        "track_url": (item.get("external_urls") or {}).get("spotify", ""),
    }


@router.get("/player")
async def get_player() -> JSONResponse:
    return JSONResponse(await _get_player_state())


# ── Playback controls ─────────────────────────────────────────

async def _player_action(method: str, endpoint: str) -> JSONResponse:
    token = await _get_access_token()
    if not token:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            req = getattr(client, method)
            resp = await req(
                f"{_API_BASE}/me/player/{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
            )
        return JSONResponse({"ok": resp.status_code in (200, 204)})
    except httpx.TimeoutException:
        logger.debug("Spotify action timeout", endpoint=endpoint)
        return JSONResponse({"ok": False})
    except httpx.RequestError as e:
        logger.warning("Spotify action error", endpoint=endpoint, error=str(e))
        return JSONResponse({"ok": False})


@router.post("/play")
async def play() -> JSONResponse:
    return await _player_action("put", "play")


@router.post("/pause")
async def pause() -> JSONResponse:
    return await _player_action("put", "pause")


@router.post("/next")
async def next_track() -> JSONResponse:
    return await _player_action("post", "next")


@router.post("/previous")
async def previous_track() -> JSONResponse:
    return await _player_action("post", "previous")
