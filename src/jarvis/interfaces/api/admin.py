from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.scheduler import Scheduler
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.kernel.paths import PROJECT_ROOT, UI_STATIC_DIR
from jarvis.kernel.settings import settings
from jarvis.providers.memory.sessions import SessionStore

_PROJECT_ROOT = PROJECT_ROOT

router = APIRouter(prefix="/admin/api")
_ui_router = APIRouter()


@_ui_router.get("/admin", include_in_schema=False)
async def admin_ui() -> FileResponse:
    return FileResponse(str(UI_STATIC_DIR / "admin.html"))


# ── Models ────────────────────────────────────────────────────


class ContentBody(BaseModel):
    content: str


class SessionMeta(BaseModel):
    session_id: str
    name: str
    date: str
    message_count: int


class SessionMessage(BaseModel):
    role: str
    content: str
    ts: str


class TopicMeta(BaseModel):
    name: str
    mtime: str
    size: int


class MemoryOverview(BaseModel):
    index: str
    user_prefs: str
    topics: list[TopicMeta]


# ── Helpers ───────────────────────────────────────────────────


def _memory_dir(request: Request) -> Path:

    return Path(settings.memory_dir)


# ── Sessions ──────────────────────────────────────────────────


@router.get("/sessions", response_model=list[SessionMeta])
async def list_sessions(request: Request) -> list[SessionMeta]:

    store: SessionStore = SessionStore(_memory_dir(request) / "sessions")
    result = []
    for path in store.list_recent(50):
        parts = path.stem.split("_", 1)
        date = parts[0] if len(parts) == 2 else "?"
        session_id = parts[1] if len(parts) == 2 else path.stem
        try:
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            count = len(lines)
        except OSError:
            count = 0
        result.append(
            SessionMeta(
                session_id=session_id,
                name=path.stem,
                date=date,
                message_count=count,
            )
        )
    return result


@router.get("/sessions/{session_id}", response_model=list[SessionMessage])
async def get_session(session_id: str, request: Request) -> list[SessionMessage]:

    store: SessionStore = SessionStore(_memory_dir(request) / "sessions")
    path = store._find(session_id)  # noqa: SLF001
    if not path:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    messages: list[SessionMessage] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            messages.append(
                SessionMessage(
                    role=entry.get("role", "?"),
                    content=entry.get("content", ""),
                    ts=entry.get("ts", ""),
                )
            )
        except json.JSONDecodeError:
            continue
    return messages


# ── Mémoire ───────────────────────────────────────────────────


@router.get("/memory", response_model=MemoryOverview)
async def get_memory(request: Request) -> MemoryOverview:
    mem_dir = _memory_dir(request)
    index_path = mem_dir / "MEMORY.md"
    prefs_path = mem_dir / "user_prefs.md"
    topics_dir = mem_dir / "topics"

    index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    prefs = prefs_path.read_text(encoding="utf-8") if prefs_path.exists() else ""

    topics: list[TopicMeta] = []
    if topics_dir.exists():
        for p in sorted(topics_dir.glob("*.md")):
            stat = p.stat()
            import datetime as dt

            mtime = dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            topics.append(TopicMeta(name=p.name, mtime=mtime, size=stat.st_size))

    return MemoryOverview(index=index, user_prefs=prefs, topics=topics)


@router.get("/memory/index")
async def get_memory_index(request: Request) -> dict:
    path = _memory_dir(request) / "MEMORY.md"
    return {"content": path.read_text(encoding="utf-8") if path.exists() else ""}


@router.put("/memory/index")
async def put_memory_index(body: ContentBody, request: Request) -> dict:
    path = _memory_dir(request) / "MEMORY.md"
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.get("/memory/prefs")
async def get_memory_prefs(request: Request) -> dict:
    path = _memory_dir(request) / "user_prefs.md"
    return {"content": path.read_text(encoding="utf-8") if path.exists() else ""}


@router.put("/memory/prefs")
async def put_memory_prefs(body: ContentBody, request: Request) -> dict:
    path = _memory_dir(request) / "user_prefs.md"
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.get("/memory/topics/{filename}")
async def get_topic(filename: str, request: Request) -> dict:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
    path = _memory_dir(request) / "topics" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return {"content": path.read_text(encoding="utf-8")}


@router.put("/memory/topics/{filename}")
async def put_topic(filename: str, body: ContentBody, request: Request) -> dict:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
    path = _memory_dir(request) / "topics" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.delete("/memory/topics/{filename}")
async def delete_topic(filename: str, request: Request) -> dict:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
    path = _memory_dir(request) / "topics" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    path.unlink()
    return {"ok": True}


# ── Tasks ─────────────────────────────────────────────────────


@router.get("/tasks")
async def get_tasks(request: Request) -> dict:

    scheduler: Scheduler = request.app.state.scheduler
    worker: BackgroundWorker = request.app.state.worker

    history = [
        {
            "session_id": r.session_id,
            "instruction": r.instruction,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "result": r.result,
            "error": r.error,
        }
        for r in worker.history()
    ]
    return {"scheduler": scheduler.status(), "history": history}


# ── Mise à jour ───────────────────────────────────────────────


async def _run(cmd: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_PROJECT_ROOT),
    )
    out, err = await proc.communicate()
    return proc.returncode, (out + err).decode().strip()


@router.post("/system/update")
async def system_update() -> dict:
    """git pull + uv sync sans toucher aux données locales (.env, memory, skills, config)."""
    steps: list[dict] = []

    # 1. Stash les éventuelles modifs locales non committées
    code, detail = await _run("git stash")
    stashed = code == 0 and "No local changes" not in detail
    steps.append({"step": "stash", "ok": True, "detail": detail})

    # 2. Pull
    code, detail = await _run("git pull origin main --ff-only")
    if code != 0:
        if stashed:
            await _run("git stash pop")
        return {"ok": False, "error": detail, "steps": steps}
    already_up_to_date = "Already up to date" in detail
    steps.append({"step": "pull", "ok": True, "detail": detail})

    # 3. Restaurer le stash si besoin
    if stashed:
        code, detail = await _run("git stash pop")
        steps.append({"step": "restore", "ok": code == 0, "detail": detail})

    # 4. Sync dépendances (uv)
    code, detail = await _run("uv sync --quiet")
    steps.append({"step": "deps", "ok": code == 0, "detail": detail or "ok"})

    return {
        "ok": True,
        "already_up_to_date": already_up_to_date,
        "restart_required": not already_up_to_date,
        "steps": steps,
    }


# ── Notifications ─────────────────────────────────────────────


@router.get("/notifications")
async def get_notifications(request: Request) -> dict:

    queue: NotificationQueue = request.app.state.notifications
    return {
        "pending": [
            {"content": n.content, "created_at": n.created_at.isoformat()}
            for n in queue._pending  # noqa: SLF001
        ]
    }
