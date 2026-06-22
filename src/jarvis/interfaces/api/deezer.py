# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from loguru import logger

from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/deezer")

_AUTH_URL = "https://connect.deezer.com/oauth/auth.php"
_TOKEN_URL = "https://connect.deezer.com/oauth/access_token.php"
_API_BASE = "https://api.deezer.com"
_PERMS = "basic_access,email,offline_access,listening_history,manage_library"

# Deezer n'a pas de PKCE : l'échange du token EXIGE le secret de l'app, qu'on
# ne peut donc pas embarquer en repo public. Chaque utilisateur enregistre sa
# propre app (developers.deezer.com/myapps) et colle App ID + Secret dans
# Mission Control → Capacités → Deezer. Ce garde-fou évite la page d'erreur
# Deezer cryptique (« You must specify a valid redirect_uri ») quand rien
# n'est configuré.
_UNCONFIGURED_HTML = (
    "<!doctype html><meta charset='utf-8'>"
    "<body style='font-family:system-ui;background:#0e0e12;color:#e8e8ec;"
    "padding:48px;max-width:560px;margin:auto'>"
    "<h2>Deezer non configuré</h2>"
    "<p>Il manque l'<b>App ID</b> et/ou la <b>Secret Key</b> de ton application "
    "Deezer. Crée une app sur "
    "<a style='color:#7aa2ff' href='https://developers.deezer.com/myapps' "
    "target='_blank' rel='noopener'>developers.deezer.com/myapps</a> "
    "(Redirect URL : <code>http://127.0.0.1:8000/api/deezer/callback</code>), "
    "puis renseigne les identifiants dans "
    "<b>Mission Control → Capacités → Deezer</b>.</p>"
    "<p><a style='color:#7aa2ff' href='/capabilities#integrations'>← Retour aux capacités</a></p>"
    "</body>"
)


def _token_path() -> Path:
    return Path(settings.deezer_token_path)


def _load_token() -> dict | None:
    p = _token_path()
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _save_token(data: dict) -> None:
    _token_path().write_text(json.dumps(data))


def _get_access_token() -> str | None:
    token = _load_token()
    return token.get("access_token") if token else None


# ── OAuth ─────────────────────────────────────────────────────


@router.get("/auth")
async def deezer_auth() -> Response:
    if not settings.deezer_app_id or not settings.deezer_app_secret.get_secret_value():
        return HTMLResponse(_UNCONFIGURED_HTML, status_code=400)
    params = {
        "app_id": settings.deezer_app_id,
        "redirect_uri": settings.deezer_redirect_uri,
        "perms": _PERMS,
    }
    return RedirectResponse(f"{_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def deezer_callback(
    code: str | None = None, error_reason: str | None = None
) -> RedirectResponse:
    if error_reason or not code:
        logger.error("Deezer OAuth error", error=error_reason)
        return RedirectResponse("/?deezer_error=1")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _TOKEN_URL,
            params={
                "app_id": settings.deezer_app_id,
                "secret": settings.deezer_app_secret.get_secret_value(),
                "code": code,
                "output": "json",
            },
        )
        if not resp.is_success:
            logger.error("Deezer token fetch failed", status=resp.status_code)
            return RedirectResponse("/?deezer_error=1")

        data = resp.json()
        _save_token({"access_token": data["access_token"]})
        logger.info("Deezer token saved")

    return RedirectResponse("/?deezer_ok=1")


# ── Token for frontend SDK ─────────────────────────────────────


@router.get("/token")
async def get_token() -> JSONResponse:
    return JSONResponse({"token": _get_access_token()})


# ── Player state ──────────────────────────────────────────────


async def _get_player_state() -> dict:
    token = _get_access_token()
    if not token:
        return {"connected": False}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_API_BASE}/user/me/history",
                params={"access_token": token, "limit": 1},
            )
    except httpx.TimeoutException:
        logger.debug("Deezer player timeout")
        return {"connected": True, "is_playing": False, "track": None}
    except httpx.RequestError as e:
        logger.warning("Deezer player request error", error=str(e))
        return {"connected": False}

    if not resp.is_success:
        return {"connected": False}

    tracks = resp.json().get("data", [])
    if not tracks:
        return {"connected": True, "is_playing": False, "track": None}

    t = tracks[0]
    album = t.get("album") or {}
    return {
        "connected": True,
        "is_playing": False,
        "track": t.get("title", ""),
        "artist": (t.get("artist") or {}).get("name", ""),
        "album": album.get("title", ""),
        "album_art": album.get("cover_medium") or None,
        "progress_ms": 0,
        "duration_ms": t.get("duration", 0) * 1000,
    }


@router.get("/player")
async def get_player() -> JSONResponse:
    return JSONResponse(await _get_player_state())


# ── Controls ──────────────────────────────────────────────────


async def _action(method: str, endpoint: str) -> JSONResponse:
    token = _get_access_token()
    if not token:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            fn = getattr(client, method)
            resp = await fn(
                f"{_API_BASE}/user/me/player/{endpoint}",
                params={"access_token": token},
            )
        return JSONResponse({"ok": resp.status_code in (200, 204)})
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("Deezer action error", endpoint=endpoint, error=str(e))
        return JSONResponse({"ok": False})


@router.post("/play")
async def play() -> JSONResponse:
    return await _action("put", "play")


@router.post("/pause")
async def pause() -> JSONResponse:
    return await _action("put", "pause")


@router.post("/next")
async def next_track() -> JSONResponse:
    return await _action("post", "next")


@router.post("/previous")
async def previous_track() -> JSONResponse:
    return await _action("post", "previous")
