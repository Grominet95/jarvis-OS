"""Spotify OAuth token management — Phase E §E.1.1.

Le tool `capabilities/tools/spotify.py` ET le router OAuth
`interfaces/api/spotify.py` partagent ce module. Auparavant `_get_access_token`
vivait dans `interfaces/api/spotify.py` et le tool l'importait — anomalie
`capabilities → interfaces` (RÈGLE 3). Phase E §E.1 ramène la logique
partagée en couche `capabilities` ; le router OAuth la consomme.

API publique (imports stables) :
  - `_TOKEN_URL` : endpoint OAuth refresh.
  - `_load_token`, `_save_token` : persistance disque.
  - `_basic_auth` : header Basic <client_id:client_secret>.
  - `_get_access_token` : retourne un access token valide (refresh transparent).
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx
from loguru import logger

from jarvis.kernel.settings import settings

_TOKEN_URL = "https://accounts.spotify.com/api/token"


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
