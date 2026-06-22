# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import base64
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False


def _load_gmail_creds(credentials_path: Path, token_path: Path) -> Credentials:
    """Charge et rafraîchit les credentials Gmail OAuth2 (bloquant)."""
    if not _HAS_GOOGLE:
        raise RuntimeError("google-api-python-client non installé.")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(f"Credentials Google manquants : {credentials_path}.")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


class GmailListTool(Tool):
    """Liste les emails Gmail non lus ou récents."""

    name = "list_emails"
    description = (
        "Liste les emails Gmail de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur demande ses mails, sa boîte mail, "
        "ses messages non lus."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Nombre d'emails à retourner (défaut : 10)",
            },
            "unread_only": {
                "type": "boolean",
                "description": "Si true, retourne uniquement les non lus (défaut : true)",
            },
        },
        "required": [],
    }

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._creds = credentials_path
        self._token = token_path

    async def execute(
        self, max_results: int = 10, unread_only: bool = True, **_: object
    ) -> ToolResult:
        if not _HAS_GOOGLE:
            return ToolResult(content="google-api-python-client non installé.", is_error=True)

        try:
            creds = await asyncio.to_thread(_load_gmail_creds, self._creds, self._token)
        except Exception as e:
            return ToolResult(content=f"Erreur credentials Gmail : {e}", is_error=True)

        label_ids = ["UNREAD", "INBOX"] if unread_only else ["INBOX"]
        params = {"labelIds": label_ids, "maxResults": max_results}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {"Authorization": f"Bearer {creds.token}"}

                # 1. Lister les IDs
                r = await client.get(f"{_GMAIL_BASE}/messages", headers=headers, params=params)
                r.raise_for_status()
                messages = r.json().get("messages", [])

                if not messages:
                    label = "non lus" if unread_only else "récents"
                    return ToolResult(content=f"Aucun email {label}.")

                # 2. Fetch metadata en parallèle
                async def fetch_meta(msg_id: str) -> dict:
                    resp = await client.get(
                        f"{_GMAIL_BASE}/messages/{msg_id}",
                        headers=headers,
                        params=[
                            ("format", "metadata"),
                            ("metadataHeaders", "From"),
                            ("metadataHeaders", "Subject"),
                            ("metadataHeaders", "Date"),
                        ],
                    )
                    resp.raise_for_status()
                    return resp.json()

                metas = await asyncio.gather(*[fetch_meta(m["id"]) for m in messages])

            lines = []
            for msg in metas:
                hdrs = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender = hdrs.get("From", "?")
                subject = hdrs.get("Subject", "(sans sujet)")
                snippet = msg.get("snippet", "")[:120]
                lines.append(f"De : {sender}\nSujet : {subject}\nAperçu : {snippet}")

            content = "\n\n---\n\n".join(lines)
            logger.debug("Gmail emails listed", count=len(lines))
            return ToolResult(content=content)

        except Exception as e:
            logger.error(f"Gmail list error: {type(e).__name__}: {e}")
            return ToolResult(content=f"Erreur Gmail : {e}", is_error=True)


# ── Send email ────────────────────────────────────────────────────────────────


def _load_gmail_send_creds(credentials_path: Path, token_path: Path):  # noqa: ANN202
    """Réutilise le même token unifié (readonly + send) que _load_gmail_creds."""
    return _load_gmail_creds(credentials_path, token_path)


def _parse_draft(draft_content: str) -> tuple[str, str, str | None, str]:
    """Parse le format de brouillon structuré.

    Retourne (to, subject, thread_id, body).
    """
    lines = draft_content.strip().splitlines()
    headers: dict[str, str] = {}
    thread_id: str | None = None
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if in_body:
            body_lines.append(line)
            continue
        if line.strip() == "---":
            in_body = True
            continue
        if line.startswith("[THREAD_ID:"):
            thread_id = line[len("[THREAD_ID:") :].rstrip("]").strip()
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            headers[key.strip().lower()] = val.strip()

    to = headers.get("à", headers.get("to", ""))
    subject = headers.get("sujet", headers.get("subject", ""))
    body = "\n".join(body_lines).strip()
    return to, subject, thread_id, body


async def send_gmail_draft(
    draft_content: str,
    credentials_path: Path,
    token_path: Path,
) -> str:
    """Parse draft_content et envoie via Gmail REST API. Retourne l'id du message envoyé."""
    to, subject, thread_id, body = _parse_draft(draft_content)
    if not to:
        raise ValueError("Destinataire (À:) introuvable dans le brouillon")

    creds = await asyncio.to_thread(_load_gmail_send_creds, credentials_path, token_path)

    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = "me"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {creds.token}"},
            json=payload,
        )
        resp.raise_for_status()

    sent_id: str = resp.json().get("id", "")
    logger.info("Gmail message sent", to=to, subject=subject, message_id=sent_id)
    return sent_id
