from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from config.settings import settings

router = APIRouter()


def _mem_dir(request: Request) -> Path:  # noqa: ARG001

    return Path(settings.memory_dir)


def _session_titles_path(request: Request) -> Path:
    return _mem_dir(request) / "session_titles.json"


def _load_titles(request: Request) -> dict[str, str]:
    p = _session_titles_path(request)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_titles(request: Request, titles: dict[str, str]) -> None:
    p = _session_titles_path(request)
    p.write_text(json.dumps(titles, ensure_ascii=False, indent=2), encoding="utf-8")


class _TitleBody(BaseModel):
    title: str


@router.get("/api/sessions")
async def list_sessions(request: Request) -> list[dict]:
    """Liste les sessions récentes (jusqu'à 20), triées par activité."""
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        return []
    titles = _load_titles(request)
    files = store.list_recent(20)
    result = []
    for f in files:
        stem = f.stem  # YYYY-MM-DD_<uuid>
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        date_str, session_id = parts
        lines = []
        try:
            lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            pass
        first_user: str | None = None
        msg_count = 0
        for line in lines:
            try:
                e = json.loads(line)
                msg_count += 1
                if first_user is None and e.get("role") == "user":
                    first_user = (e.get("content") or "")[:60]
            except (json.JSONDecodeError, KeyError):
                pass
        default_preview = first_user or f"Session {date_str}"
        result.append(
            {
                "id": session_id,
                "date": date_str,
                "preview": default_preview,
                "title": titles.get(session_id) or default_preview,
                "message_count": msg_count,
            }
        )
    return result


@router.put("/api/sessions/{session_id}/title")
async def rename_session(session_id: str, body: _TitleBody, request: Request) -> dict:
    """Renomme une session (stocké dans session_titles.json)."""
    if not body.title.strip():
        raise HTTPException(400, "Le titre ne peut pas être vide.")
    titles = _load_titles(request)
    titles[session_id] = body.title.strip()
    _save_titles(request, titles)
    return {"id": session_id, "title": body.title.strip()}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    """Supprime une session (fichier JSONL + titre associé)."""
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(503, "Session store unavailable.")
    path = store._find(session_id)
    if path is None:
        raise HTTPException(404, "Session introuvable.")
    filename = path.name
    path.unlink(missing_ok=True)
    titles = _load_titles(request)
    if session_id in titles:
        del titles[session_id]
        _save_titles(request, titles)

    # Retire la session des indices FTS + vectoriel si disponibles
    fts_index = getattr(request.app.state, "fts_index", None)
    vector_index = getattr(request.app.state, "vector_index", None)
    if fts_index is not None or vector_index is not None:

        async def _remove_from_indices() -> None:
            if fts_index is not None:
                await fts_index.remove(filename)
            if vector_index is not None:
                async with vector_index._lock:
                    vector_index._remove_doc_locked(f"transcript:{filename}")
                await vector_index.persist()

        asyncio.create_task(_remove_from_indices(), name=f"indices-remove-{session_id}")

    return {"deleted": session_id}


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    limit: int = Query(default=30, le=100),
) -> list[dict]:
    """Retourne les derniers messages d'une session."""
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        return []
    messages = store.load(session_id)
    return messages[-limit:]
