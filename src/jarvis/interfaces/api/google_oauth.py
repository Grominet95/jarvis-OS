"""Google OAuth2 web flow — Gmail + Calendar."""

from __future__ import annotations

import base64
import hashlib
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

# In-memory state store (single-user JARVIS)
_pending: dict[str, dict] = {}


def _redirect_uri(request: Request, service: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/google/callback/{service}"


def _credentials_path() -> Path:
    return Path(settings.google_credentials_path)


def _token_path(service: str) -> Path:
    base = Path(settings.google_token_path)
    if service == "gmail":
        return base.parent / "google_gmail_token.json"
    return base  # calendar uses google_token.json


@router.get("/auth/{service}")
async def google_auth(service: str, request: Request) -> RedirectResponse:
    if service not in ("gmail", "calendar"):
        return RedirectResponse("/capabilities?error=unknown_service")

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
