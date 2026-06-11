"""API REST pour les projets agent worker."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis.engine.mission.project_store import WORKSPACE_DIR

router = APIRouter()


def _orch(request: Request) -> object:
    return request.app.state.orchestrator


# ── Schemas ───────────────────────────────────────────────────────────────────


class ApprovalBody(BaseModel):
    step_id: str
    approved: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/projects")
async def list_projects(request: Request) -> list[dict]:
    orch = _orch(request)
    projects = orch.list_projects()
    return [
        {
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "steps_done": sum(1 for s in p.steps if s.status == "done"),
            "steps_total": len(p.steps),
            "created_at": p.created_at.isoformat(),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "files_created": len(p.files_created),
        }
        for p in projects
    ]


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request) -> dict:
    orch = _orch(request)
    project = orch.get_project(project_id)
    if not project:
        raise HTTPException(404, f"Projet non trouvé : {project_id}")
    return orch._project_summary(project)


@router.get("/api/projects/{project_id}/logs")
async def get_logs(project_id: str, request: Request) -> list[dict]:
    orch = _orch(request)
    logs = orch.get_logs(project_id)
    return [
        {
            "ts": e.timestamp.isoformat(),
            "level": e.level,
            "msg": e.message,
            "step_id": e.step_id,
            "data": e.data,
        }
        for e in logs
    ]


@router.post("/api/projects/{project_id}/kill")
async def kill_project(project_id: str, request: Request) -> dict:
    orch = _orch(request)
    ok = orch.kill(project_id)
    if not ok:
        raise HTTPException(404, f"Worker actif non trouvé : {project_id}")
    return {"killed": True}


@router.post("/api/projects/{project_id}/retry")
async def retry_project(project_id: str, request: Request) -> dict:
    orch = _orch(request)
    project = await orch.retry_project(project_id)
    if not project:
        raise HTTPException(404, f"Projet non trouvé : {project_id}")
    return {"ok": True, "project_id": project.id, "status": project.status}


class ResetStepsBody(BaseModel):
    step_ids: list[str]


@router.post("/api/projects/{project_id}/reset-steps")
async def reset_steps(project_id: str, body: ResetStepsBody, request: Request) -> dict:
    """Remet des étapes spécifiques en pending (sans relancer le worker)."""
    import json

    state_file = WORKSPACE_DIR / project_id / ".jarvis" / "state.json"
    if not state_file.exists():
        raise HTTPException(404, f"Projet non trouvé : {project_id}")
    d = json.loads(state_file.read_text(encoding="utf-8"))
    reset = []
    for s in d["steps"]:
        if s["id"] in body.step_ids:
            s["status"] = "pending"
            s["output"] = None
            s["error"] = None
            s["started_at"] = None
            s["completed_at"] = None
            reset.append(s["id"])
    state_file.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return {"reset": reset}


@router.post("/api/projects/{project_id}/approve")
async def approve_step(project_id: str, body: ApprovalBody, request: Request) -> dict:
    orch = _orch(request)
    ok = orch.resolve_approval(project_id, body.step_id, body.approved)
    return {"resolved": ok, "approved": body.approved}


@router.get("/api/projects/{project_id}/files")
async def list_files(project_id: str, request: Request) -> list[str]:
    orch = _orch(request)
    return orch.get_workspace_files(project_id)


@router.get("/api/projects/{project_id}/files/{path:path}")
async def read_file(project_id: str, path: str, request: Request) -> dict:
    orch = _orch(request)
    try:
        content = orch.read_workspace_file(project_id, path)
        return {"path": path, "content": content}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(403, str(e)) from e


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request) -> dict:
    import shutil

    orch = _orch(request)
    project = orch.get_project(project_id)
    if not project:
        raise HTTPException(404, f"Projet non trouvé : {project_id}")
    orch.kill(project_id)
    workspace = Path(project.workspace_path)
    if workspace.exists():
        shutil.rmtree(workspace)
    return {"deleted": True}
