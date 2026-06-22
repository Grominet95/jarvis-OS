# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Google OAuth2 web flow — Gmail + Calendar."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from loguru import logger

from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/google")

_SCOPES_GMAIL = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
_SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]

# Endpoints OAuth2 Google — constants, communs à toutes les apps.
_GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
_GOOGLE_CERT_URI = "https://www.googleapis.com/oauth2/v1/certs"

# In-memory state store (single-user JARVIS)
_pending: dict[str, dict] = {}


def _redirect_uri(request: Request, service: str) -> str:
    base = str(request.base_url).rstrip("/")
    if not base.startswith("https://") and "127.0.0.1" not in base and "localhost" not in base:
        base = base.replace("http://", "https://", 1)
    return f"{base}/api/google/callback/{service}"


def _credentials_path() -> Path:
    return Path(settings.google_credentials_path)


def _maybe_write_credentials_from_env(request: Request) -> None:
    """Régénère google_credentials.json à partir de GOOGLE_CLIENT_ID/SECRET.

    Permet de configurer Google depuis l'UI/.env (comme Spotify/Deezer) sans
    déposer le fichier JSON à la main : les champs variables sont client_id +
    client_secret, le reste (auth_uri/token_uri/cert) est constant et les
    redirect_uris se déduisent du host courant.

    Ne fait rien si les credentials .env sont absents → un fichier déjà présent
    (install historique) continue d'être utilisé tel quel, zéro régression.
    """
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret.get_secret_value()
    if not client_id or not client_secret:
        return

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": _GOOGLE_AUTH_URI,
            "token_uri": _GOOGLE_TOKEN_URI,
            "auth_provider_x509_cert_url": _GOOGLE_CERT_URI,
            "redirect_uris": [
                _redirect_uri(request, "gmail"),
                _redirect_uri(request, "calendar"),
            ],
        }
    }
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def _token_path(service: str) -> Path:
    base = Path(settings.google_token_path)
    if service == "gmail":
        return base.parent / "google_gmail_token.json"
    return base  # calendar uses google_token.json


@router.get("/auth/{service}")
async def google_auth(service: str, request: Request) -> RedirectResponse:
    if service not in ("gmail", "calendar"):
        return RedirectResponse("/capabilities?error=unknown_service")

    # Si les credentials sont fournis en .env (UI), (re)génère le fichier JSON
    # que le reste du flux (et les consommateurs gmail/calendar) attendent.
    _maybe_write_credentials_from_env(request)

    creds_path = _credentials_path()
    if not creds_path.exists():
        logger.error("Google credentials file missing", path=str(creds_path))
        return RedirectResponse("/capabilities?google_error=no_credentials")

    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore

        scopes = _SCOPES_GMAIL if service == "gmail" else _SCOPES_CALENDAR
        redirect_uri = _redirect_uri(request, service)

        flow = Flow.from_client_secrets_file(str(creds_path), scopes=scopes)
        flow.redirect_uri = redirect_uri

        state = secrets.token_urlsafe(16)
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

        _pending[state] = {
            "service": service,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        return RedirectResponse(auth_url)

    except ImportError:
        logger.error("google-auth-oauthlib non installé")
        return RedirectResponse("/capabilities?google_error=missing_lib")
    except Exception as exc:
        logger.exception("Google auth error", error=str(exc))
        return RedirectResponse("/capabilities?google_error=1")


@router.get("/callback/{service}")
async def google_callback(
    service: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error or not code:
        logger.error("Google OAuth error", service=service, error=error)
        return RedirectResponse("/capabilities?google_error=1")

    pending = _pending.pop(state, None) if state else None
    if not pending or pending.get("service") != service:
        logger.warning("Google OAuth state mismatch", state=state)
        return RedirectResponse("/capabilities?google_error=state_mismatch")

    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore

        creds_path = _credentials_path()
        scopes = _SCOPES_GMAIL if service == "gmail" else _SCOPES_CALENDAR

        flow = Flow.from_client_secrets_file(str(creds_path), scopes=scopes, state=state)
        flow.redirect_uri = pending["redirect_uri"]
        flow.fetch_token(code=code, code_verifier=pending["code_verifier"])

        token_path = _token_path(service)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(flow.credentials.to_json())
        logger.info("Google token saved", service=service, path=str(token_path))

        return RedirectResponse("/capabilities?google_ok=" + service)

    except Exception as exc:
        logger.exception("Google callback error", service=service, error=str(exc))
        return RedirectResponse("/capabilities?google_error=1")
