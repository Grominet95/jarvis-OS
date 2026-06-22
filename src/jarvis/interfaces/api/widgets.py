# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api")

_NOTION_VERSION = "2022-06-28"
_NOTION_BASE = "https://api.notion.com/v1"


# ── Models ────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    text: str
    done: bool


class TasksResponse(BaseModel):
    tasks: list[Task]


class TaskCreate(BaseModel):
    text: str


class TaskPatch(BaseModel):
    done: bool | None = None
    text: str | None = None


class CalEvent(BaseModel):
    time: str
    name: str
    subtitle: str


class EventsResponse(BaseModel):
    events: list[CalEvent]


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_token.get_secret_value()}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── Notion tasks ──────────────────────────────────────────────


@router.get("/tasks", response_model=TasksResponse)
async def get_tasks() -> TasksResponse:
    token = settings.notion_token.get_secret_value()
    page_id = settings.notion_page_id
    if not token or not page_id:
        return TasksResponse(tasks=[])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_NOTION_BASE}/blocks/{page_id}/children",
                headers=_notion_headers(),
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error("Notion widget error", error=str(e))
        return TasksResponse(tasks=[])

    blocks = resp.json().get("results", [])
    tasks: list[Task] = []
    in_section = False

    for block in blocks:
        btype = block.get("type", "")

        if btype.startswith("heading_"):
            text = "".join(
                rt.get("plain_text", "") for rt in block.get(btype, {}).get("rich_text", [])
            )
            if "Tâches du jour" in text or "tâches du jour" in text.lower():
                in_section = True
            elif in_section:
                break
            continue

        if in_section and btype == "to_do":
            todo = block.get("to_do", {})
            text = "".join(rt.get("plain_text", "") for rt in todo.get("rich_text", [])).strip()
            if text:
                tasks.append(
                    Task(
                        id=block["id"],
                        text=text,
                        done=bool(todo.get("checked", False)),
                    )
                )

    return TasksResponse(tasks=tasks)


async def _find_section_anchor(client: httpx.AsyncClient, page_id: str) -> str | None:
    """Return the ID of the last to_do block in 'Tâches du jour'.

    Falls back to the heading ID if no to_do exists yet.
    """
    resp = await client.get(
        f"{_NOTION_BASE}/blocks/{page_id}/children",
        headers=_notion_headers(),
    )
    resp.raise_for_status()
    blocks = resp.json().get("results", [])

    heading_id: str | None = None
    last_todo_id: str | None = None
    in_section = False

    for block in blocks:
        btype = block.get("type", "")
        if btype.startswith("heading_"):
            heading_text = "".join(
                rt.get("plain_text", "") for rt in block.get(btype, {}).get("rich_text", [])
            )
            if "Tâches du jour" in heading_text or "tâches du jour" in heading_text.lower():
                in_section = True
                heading_id = block["id"]
            elif in_section:
                break
            continue
        if in_section and btype == "to_do":
            last_todo_id = block["id"]

    return last_todo_id or heading_id


@router.post("/tasks", response_model=Task)
async def create_task(body: TaskCreate) -> Task:
    token = settings.notion_token.get_secret_value()
    page_id = settings.notion_page_id
    if not token or not page_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Notion non configuré")

    new_block = {
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": body.text}}],
            "checked": False,
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        anchor = await _find_section_anchor(client, page_id)
        payload: dict = {"children": [new_block]}
        if anchor:
            payload["after"] = anchor

        resp = await client.patch(
            f"{_NOTION_BASE}/blocks/{page_id}/children",
            headers=_notion_headers(),
            json=payload,
        )
        resp.raise_for_status()

    block = resp.json()["results"][0]
    return Task(id=block["id"], text=body.text, done=False)


@router.patch("/tasks/{block_id}", response_model=Task)
async def update_task(block_id: str, body: TaskPatch) -> Task:
    token = settings.notion_token.get_secret_value()
    if not token:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Notion non configuré")

    update: dict = {"to_do": {}}
    if body.done is not None:
        update["to_do"]["checked"] = body.done
    if body.text is not None:
        update["to_do"]["rich_text"] = [{"type": "text", "text": {"content": body.text}}]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(
            f"{_NOTION_BASE}/blocks/{block_id}",
            headers=_notion_headers(),
            json=update,
        )
        resp.raise_for_status()

    block = resp.json()
    todo = block.get("to_do", {})
    text = "".join(rt.get("plain_text", "") for rt in todo.get("rich_text", []))
    return Task(id=block["id"], text=text, done=bool(todo.get("checked", False)))


@router.delete("/tasks/{block_id}")
async def delete_task(block_id: str) -> dict:
    token = settings.notion_token.get_secret_value()
    if not token:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Notion non configuré")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(
            f"{_NOTION_BASE}/blocks/{block_id}",
            headers=_notion_headers(),
        )
        resp.raise_for_status()

    return {"ok": True}


# ── Google Calendar events ────────────────────────────────────

_cal_cache: list[CalEvent] = []
_cal_cache_ts: datetime | None = None
_cal_lock = asyncio.Lock()
_CAL_TTL = 300  # secondes


def _load_calendar_creds(token_path: Path):  # noqa: ANN202
    """Charge et rafraîchit les credentials Calendar OAuth2 (bloquant)."""
    from google.auth.transport.requests import Request as GRequest
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        ["https://www.googleapis.com/auth/calendar.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GRequest())
    return creds


async def _fetch_today_events() -> list[CalEvent]:
    try:
        from google.oauth2.credentials import Credentials  # noqa: F401
    except ImportError:
        logger.warning("google-api-python-client non installé")
        return []

    token_path = Path(settings.google_token_path)
    if not token_path.exists():
        return []

    try:
        creds = await asyncio.to_thread(_load_calendar_creds, token_path)
    except Exception as e:
        logger.error("Calendar widget creds error", error=str(e))
        return []

    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    params = {
        "timeMin": start_of_day.isoformat(),
        "timeMax": end_of_day.isoformat(),
        "maxResults": 15,
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {creds.token}"},
            params=params,
        )
        resp.raise_for_status()

    events: list[CalEvent] = []
    for item in resp.json().get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date", ""))
        if "T" in start:
            dt = datetime.fromisoformat(start)
            time_str = dt.strftime("%H:%M")
        else:
            time_str = "Journée"

        name = item.get("summary", "(sans titre)")
        subtitle = (item.get("location") or "").strip()
        if not subtitle:
            desc = (item.get("description") or "").strip()
            subtitle = desc.split("\n")[0][:40] if desc else ""

        events.append(CalEvent(time=time_str, name=name, subtitle=subtitle))

    return events


@router.get("/events", response_model=EventsResponse)
async def get_events() -> EventsResponse:
    global _cal_cache, _cal_cache_ts

    # Servir le cache si < TTL — évite les appels concurrents à Google API
    now = datetime.now(UTC)
    if _cal_cache_ts and (now - _cal_cache_ts).total_seconds() < _CAL_TTL:
        return EventsResponse(events=_cal_cache)

    # Un seul appel API à la fois — les autres attendent et réutilisent le résultat
    async with _cal_lock:
        # Re-check après avoir acquis le lock (un autre a peut-être déjà rafraîchi)
        if _cal_cache_ts and (now - _cal_cache_ts).total_seconds() < _CAL_TTL:
            return EventsResponse(events=_cal_cache)
        try:
            events = await _fetch_today_events()
            _cal_cache = events
            _cal_cache_ts = datetime.now(UTC)
            return EventsResponse(events=events)
        except Exception as e:
            logger.error("Calendar widget error", error=str(e))
            return EventsResponse(events=_cal_cache)  # retourne le cache périmé si erreur
