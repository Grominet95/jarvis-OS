"""
EmailCollector — récupère les emails non lus avec le corps complet du thread.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.connectivity import is_offline_mode
from jarvis.kernel.settings import settings

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

LOW_PRIORITY_PATTERNS = [
    "noreply",
    "no-reply",
    "newsletter",
    "notification",
    "donotreply",
    "unsubscribe",
    "automated",
]

HIGH_SUBJECT_KEYWORDS = [
    "urgent",
    "asap",
    "important",
    "deadline",
    "payment",
    "invoice",
    "facture",
    "contrat",
    "partenariat",
]

HIGH_SENDER_DOMAINS = ["@anthropic", "@pcbway", "@nextpcb"]


def _extract_text_body(payload: dict) -> str:
    """Extraction récursive du texte plain depuis un payload MIME Gmail."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            except Exception:
                return ""
    for part in payload.get("parts", []):
        result = _extract_text_body(part)
        if result:
            return result
    return ""


def _load_gmail_creds(credentials_path: Path, token_path: Path):  # noqa: ANN202

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(f"Credentials Google manquants : {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


class EmailCollector(CollectorBase):
    name = "email"

    async def _collect(self) -> list[ContextItem]:
        if is_offline_mode():
            logger.debug("EmailCollector ignoré — mode local")
            return []

        creds_path = Path(settings.google_credentials_path)
        token_path = Path(settings.google_token_path).parent / "google_gmail_token.json"

        try:
            creds = await asyncio.to_thread(_load_gmail_creds, creds_path, token_path)
        except FileNotFoundError as e:
            logger.warning(f"EmailCollector: {e}")
            return []

        return await self._fetch_messages(creds.token)

    async def _fetch_messages(self, access_token: str) -> list[ContextItem]:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{_GMAIL_BASE}/messages",
                headers=headers,
                params={"labelIds": "UNREAD", "maxResults": 15},
            )
            r.raise_for_status()
            messages = r.json().get("messages", [])
            if not messages:
                return []

            async def fetch_full(msg_id: str) -> dict:
                resp = await client.get(
                    f"{_GMAIL_BASE}/messages/{msg_id}",
                    headers=headers,
                    params={"format": "full"},
                )
                resp.raise_for_status()
                return resp.json()

            metas = await asyncio.gather(*[fetch_full(m["id"]) for m in messages])

        items = []
        for msg in metas:
            payload = msg.get("payload", {})
            hdrs = {h["name"]: h["value"] for h in payload.get("headers", [])}
            sender = hdrs.get("From", "")
            subject = hdrs.get("Subject", "Sans sujet")
            date = hdrs.get("Date", "")
            msg_id = hdrs.get("Message-ID", "")
            thread_id = msg.get("threadId", "")
            snippet = msg.get("snippet", "")

            # Corps complet du message (limité pour le contexte)
            body = _extract_text_body(payload)[:1500]

            sender_lower = sender.lower()
            if any(p in sender_lower for p in LOW_PRIORITY_PATTERNS):
                continue

            priority = self._assess_priority(subject, sender_lower)

            raw = (
                f"De: {sender}\nSujet: {subject}\nDate: {date}\n"
                f"Message-ID: {msg_id}\nThread-ID: {thread_id}\n\n"
                f"{body or snippet}"
            )

            items.append(
                ContextItem(
                    type=ItemType.EMAIL,
                    title=subject,
                    summary=snippet[:200],
                    raw=raw,
                    source="gmail",
                    timestamp=datetime.now(),
                    priority=priority,
                    metadata={
                        "from": sender,
                        "date": date,
                        "id": msg.get("id", ""),
                        "thread_id": thread_id,
                        "message_id": msg_id,
                    },
                )
            )

        return items

    def _assess_priority(self, subject: str, sender_lower: str) -> Priority:
        if any(kw in subject.lower() for kw in HIGH_SUBJECT_KEYWORDS):
            return Priority.HIGH
        if any(d in sender_lower for d in HIGH_SENDER_DOMAINS):
            return Priority.HIGH
        return Priority.MEDIUM
