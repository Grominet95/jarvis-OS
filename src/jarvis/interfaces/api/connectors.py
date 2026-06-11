"""État de santé des connecteurs OAuth/API (M5 intégration UI).

Endpoint lecture-seule consommé par la section "Connexions" de Réglages
(settings.html). Probe chaque connecteur sans déclencher de side-effects :

  - Google Gmail / Calendar : présence du fichier token + parse expiry
  - Spotify : présence + expiry (avec marge 60s pour refresh)
  - Deezer  : présence (Deezer n'expire pas, token statique)
  - Notion  : présence de la clé API en .env
  - Telegram/Discord : présence des creds + flag _ENABLED

Aucune écriture, aucun appel réseau. Si un token semble valide localement
mais que le serveur distant a révoqué (cas Gmail invalid_grant), le statut
reste "ok" — c'est l'appel applicatif suivant qui basculera en "error".
On préfère l'optimisme local au coût d'un probe réseau systématique.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from config.settings import settings

router = APIRouter()


def _safe_load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _google_health(token_path: Path) -> dict:
    """Probe local d'un token Google. Renvoie ok | expired | missing | error."""
    if not token_path.exists():
        return {"token_health": "missing", "expires_at": None}
    tok = _safe_load_json(token_path)
    if tok is None:
        return {"token_health": "error", "expires_at": None}
    expiry = tok.get("expiry") or tok.get("expires_at")
    if expiry is None:
        # Token sans expiry — on optimistically renvoie ok (le refresh_token tient)
        return {"token_health": "ok", "expires_at": None}
    # Google stocke "expiry" en ISO 8601
    try:
        if isinstance(expiry, str):
            exp_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            exp_ts = exp_dt.timestamp()
        else:
            exp_ts = float(expiry)
    except Exception:  # noqa: BLE001
        return {"token_health": "error", "expires_at": str(expiry)}
    # On considère "expired" si plus de refresh possible. En pratique le
    # refresh_token Google ne meurt pas tant qu'il n'a pas été révoqué — donc
    # un access_token expiré n'est pas un vrai problème, sauf si refresh_token
    # absent.
    if exp_ts < time.time() and not tok.get("refresh_token"):
        return {"token_health": "expired", "expires_at": exp_ts}
    return {"token_health": "ok", "expires_at": exp_ts}


def _spotify_health() -> dict:
    p = Path(settings.spotify_token_path)
    tok = _safe_load_json(p)
    if tok is None:
        return {"token_health": "missing", "expires_at": None}
    exp = tok.get("expires_at", 0)
    if exp and exp < time.time() and not tok.get("refresh_token"):
        return {"token_health": "expired", "expires_at": exp}
    return {"token_health": "ok", "expires_at": exp or None}


def _deezer_health() -> dict:
    p = Path(settings.deezer_token_path)
    tok = _safe_load_json(p)
    if tok is None or not tok.get("access_token"):
        return {"token_health": "missing", "expires_at": None}
    return {"token_health": "ok", "expires_at": None}


def _env_present(key: str) -> bool:
    return (os.environ.get(key) or "").strip() != ""


@router.get("/api/connectors/status")
async def connectors_status() -> list[dict]:
    """Liste l'état de santé de chaque connecteur. Lecture seule, pas de probe réseau."""
    google_creds = Path(settings.google_credentials_path)
    gmail_token = google_creds.parent / "google_gmail_token.json"
    calendar_token = Path(settings.google_token_path)

    items: list[dict] = []

    # Google Gmail
    items.append({
        "name": "Gmail",
        "kind": "oauth",
        "connected": gmail_token.exists(),
        **_google_health(gmail_token),
        "reconnect_url": "/api/google/auth/gmail",
        "edit_url": "/capabilities#integrations",
    })

    # Google Calendar
    items.append({
        "name": "Google Calendar",
        "kind": "oauth",
        "connected": calendar_token.exists(),
        **_google_health(calendar_token),
        "reconnect_url": "/api/google/auth/calendar",
        "edit_url": "/capabilities#integrations",
    })

    # Spotify
    items.append({
        "name": "Spotify",
        "kind": "oauth",
        "connected": Path(settings.spotify_token_path).exists(),
        **_spotify_health(),
        "reconnect_url": "/api/spotify/auth",
        "edit_url": "/capabilities#integrations",
    })

    # Deezer
    items.append({
        "name": "Deezer",
        "kind": "oauth",
        "connected": Path(settings.deezer_token_path).exists(),
        **_deezer_health(),
        "reconnect_url": "/api/deezer/auth",
        "edit_url": "/capabilities#integrations",
    })

    # Notion (clé API statique en .env)
    notion_ok = _env_present("NOTION_TOKEN")
    items.append({
        "name": "Notion",
        "kind": "key",
        "connected": notion_ok,
        "token_health": "ok" if notion_ok else "missing",
        "expires_at": None,
        "reconnect_url": None,
        "edit_url": "/capabilities#integrations",
    })

    # Telegram (bot)
    tg_ok = _env_present("TELEGRAM_BOT_TOKEN") and _env_present("TELEGRAM_OWNER_ID")
    tg_enabled = (os.environ.get("TELEGRAM_ENABLED") or "").strip().lower() in (
        "1", "true", "yes",
    )
    items.append({
        "name": "Telegram",
        "kind": "messaging",
        "connected": tg_ok and tg_enabled,
        "token_health": "ok" if tg_ok else "missing",
        "expires_at": None,
        "reconnect_url": None,
        "edit_url": "/capabilities#integrations",
        "enabled": tg_enabled,
    })

    # Discord (bot)
    dc_ok = _env_present("DISCORD_BOT_TOKEN") and _env_present("DISCORD_OWNER_ID")
    dc_enabled = (os.environ.get("DISCORD_ENABLED") or "").strip().lower() in (
        "1", "true", "yes",
    )
    items.append({
        "name": "Discord",
        "kind": "messaging",
        "connected": dc_ok and dc_enabled,
        "token_health": "ok" if dc_ok else "missing",
        "expires_at": None,
        "reconnect_url": None,
        "edit_url": "/capabilities#integrations",
        "enabled": dc_enabled,
    })

    return items
