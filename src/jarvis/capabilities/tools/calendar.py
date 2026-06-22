# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_CAL_BASE = "https://www.googleapis.com/calendar/v3"

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False


def _load_creds(token_path: Path, credentials_path: Path) -> Credentials:
    """Charge et rafraîchit les credentials OAuth2 (bloquant — exécuté dans un thread)."""
    if not _HAS_GOOGLE:
        raise RuntimeError("google-api-python-client non installé.")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                token_path.unlink(missing_ok=True)
                creds = None

        if not creds or not creds.valid:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Credentials Google manquants : {credentials_path}. "
                    "Télécharge-les depuis Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), _SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return creds


class CalendarListTool(Tool):
    """Liste les prochains événements Google Calendar."""

    name = "list_calendar_events"
    description = (
        "Liste les prochains événements du Google Calendar de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur demande son agenda, son planning ou ses rendez-vous."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Nombre de jours à afficher (défaut : 7)",
            },
        },
        "required": [],
    }

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._creds = credentials_path
        self._token = token_path

    async def execute(self, days_ahead: int = 7, **_: object) -> ToolResult:
        if not _HAS_GOOGLE:
            return ToolResult(content="google-api-python-client non installé.", is_error=True)

        try:
            creds = await asyncio.to_thread(_load_creds, self._token, self._creds)
        except Exception as e:
            return ToolResult(content=f"Erreur credentials : {e}", is_error=True)

        now_iso = datetime.now(UTC).isoformat()
        params = {
            "timeMin": now_iso,
            "maxResults": days_ahead * 5,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    f"{_CAL_BASE}/calendars/primary/events",
                    headers={"Authorization": f"Bearer {creds.token}"},
                    params=params,
                )
                resp.raise_for_status()

            events = resp.json().get("items", [])
            if not events:
                return ToolResult(content="Aucun événement prévu.")

            lines = []
            for e in events:
                start = e["start"].get("dateTime", e["start"].get("date", "?"))
                lines.append(f"- {start} : {e.get('summary', '(sans titre)')}")

            content = "\n".join(lines)
            logger.debug("Calendar events listed", count=len(lines))
            return ToolResult(content=content)

        except Exception as e:
            logger.error(f"Calendar list error: {type(e).__name__}: {e}")
            return ToolResult(content=f"Erreur Calendar : {e}", is_error=True)


class CalendarCreateTool(Tool):
    """Crée un événement dans Google Calendar."""

    name = "create_calendar_event"
    description = (
        "Crée un nouvel événement dans le Google Calendar de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur veut ajouter un rendez-vous ou un rappel."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre de l'événement"},
            "start": {
                "type": "string",
                "description": "Début ISO 8601 : 2024-01-15T14:00:00",
            },
            "end": {
                "type": "string",
                "description": "Fin ISO 8601 : 2024-01-15T15:00:00",
            },
            "description": {"type": "string", "description": "Description optionnelle"},
        },
        "required": ["title", "start", "end"],
    }

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._creds = credentials_path
        self._token = token_path

    async def execute(
        self, title: str, start: str, end: str, description: str = "", **_: object
    ) -> ToolResult:
        if not _HAS_GOOGLE:
            return ToolResult(content="google-api-python-client non installé.", is_error=True)

        try:
            creds = await asyncio.to_thread(_load_creds, self._token, self._creds)
        except Exception as e:
            return ToolResult(content=f"Erreur credentials : {e}", is_error=True)

        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": "Europe/Paris"},
            "end": {"dateTime": end, "timeZone": "Europe/Paris"},
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{_CAL_BASE}/calendars/primary/events",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()

            created = resp.json()
            logger.info("Calendar event created", title=title, event_id=created.get("id"))
            return ToolResult(content=f"Événement créé : {created.get('htmlLink', title)}")

        except Exception as e:
            logger.error(f"Calendar create error: {type(e).__name__}: {e}")
            return ToolResult(content=f"Erreur Calendar : {e}", is_error=True)
