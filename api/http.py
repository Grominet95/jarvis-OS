from __future__ import annotations

import json
import os
import shutil
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.permissions import permissions as _perm_store

# ── In-memory log ring buffer (sink ajouté dans main.py) ─────────────────────
_log_buffer: deque[str] = deque(maxlen=120)

def _log_sink(message) -> None:  # loguru message object
    _log_buffer.append(str(message).strip())

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/command", include_in_schema=False)
async def command_center_ui() -> FileResponse:
    return FileResponse("ui/static/command.html")


def _versioned_html(html_path: Path, assets: list[tuple[str, str]]) -> str:
    """Inject cache-busting ?v=<mtime> into HTML asset references."""
    from fastapi.responses import Response as FastResponse  # noqa: F401 (used by callers)
    content = html_path.read_text(encoding="utf-8")
    for src_attr, asset_path in assets:
        try:
            v = int(Path(asset_path).stat().st_mtime)
            # href="…" or src="…" without existing ?v=
            import re
            content = re.sub(
                r'((?:href|src)=["\'])(' + re.escape(src_attr) + r')(["\'])',
                lambda m: m.group(1) + m.group(2) + "?v=" + str(v) + m.group(3),
                content,
            )
        except OSError:
            pass
    return content


@router.get("/dashboard", include_in_schema=False)
async def dashboard_ui():
    from fastapi.responses import Response as FastResponse
    content = _versioned_html(
        Path("ui/static/dashboard.html"),
        [
            ("/_shared.css",    "ui/static/_shared.css"),
            ("/dashboard.css",  "ui/static/dashboard.css"),
            ("/_shared.js",     "ui/static/_shared.js"),
            ("/dashboard.js",   "ui/static/dashboard.js"),
        ],
    )
    return FastResponse(content=content, media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@router.get("/settings", include_in_schema=False)
async def settings_ui():
    from fastapi.responses import Response as FastResponse
    content = _versioned_html(
        Path("ui/static/settings.html"),
        [
            ("/_shared.css",          "ui/static/_shared.css"),
            ("/settings.css",         "ui/static/settings.css"),
            ("/_shared.js",           "ui/static/_shared.js"),
            ("/settings-charts.js",   "ui/static/settings-charts.js"),
            ("/settings.js",          "ui/static/settings.js"),
        ],
    )
    return FastResponse(content=content, media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Point de contrôle — vérifie que le serveur est up."""
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/api/wakeup/status")
async def wakeup_status() -> dict:
    """Retourne si la séquence wake up est activée (contrôlé via WAKEUP_ENABLED dans .env)."""
    from config.settings import settings
    return {"enabled": settings.wakeup_enabled, "user_firstname": settings.user_firstname}


@router.post("/api/vision/verify-face")
async def verify_face() -> dict:
    """
    Retourne le résultat de la reconnaissance faciale.
    Utilise le FaceRecognizer du daemon vision si actif,
    sinon tente une capture directe (fallback).
    """
    import asyncio

    from vision.daemon import get_face_recognizer
    recognizer = get_face_recognizer()

    if recognizer is not None and recognizer._available:
        # Daemon actif — utiliser le dernier résultat (2fps en continu)
        result = recognizer._last_result
        if result is None:
            await asyncio.sleep(0.6)          # attendre un frame daemon
            result = recognizer._last_result
        if result is not None:
            return {
                "recognized": result.recognized,
                "name": result.name,
                "confidence": round(result.confidence, 2),
            }

    # Fallback : capture OpenCV indépendante
    loop = asyncio.get_event_loop()

    def _capture_direct() -> dict:
        try:
            import cv2
        except ImportError:
            return {"recognized": False, "name": "error", "confidence": 0.0}
        cap = cv2.VideoCapture(0)
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return {"recognized": False, "name": "error", "confidence": 0.0}
        from vision.face_recognizer import FaceRecognizer
        res = FaceRecognizer().process(frame)
        return {"recognized": res.recognized, "name": res.name, "confidence": round(res.confidence, 2)}

    return await loop.run_in_executor(None, _capture_direct)


@router.post("/api/voice/speak")
async def voice_speak(body: dict) -> dict:
    """
    Synthétise un texte en audio via TTS et retourne les bytes en base64.
    Le frontend joue l'audio directement avec Web Audio API.
    """
    import base64

    text = body.get("text", "").strip()
    if not text:
        return {"status": "error", "audio_b64": None}

    from audio.tts import tts_engine
    audio_bytes = await tts_engine.synthesize(text)
    return {
        "status": "ok",
        "audio_b64": base64.b64encode(audio_bytes).decode() if audio_bytes else None,
    }


# ── Skills API ────────────────────────────────────────────────────────────────

@router.get("/api/skills/catalog")
async def get_skills_catalog() -> dict:
    """Catalogue des skills disponibles (GitHub + état installé)."""
    from skills.installer import skill_installer
    skills = await skill_installer.fetch_catalog()
    offline = any(s.get("offline") for s in skills)
    return {"skills": skills, "offline": offline}


@router.get("/api/skills/installed")
async def get_installed_skills() -> dict:
    """Liste des skills installés, enrichie avec env_status et configured."""
    from skills.registry import skill_registry
    from dotenv import dotenv_values
    env_values = dotenv_values(".env")
    enriched = []
    for s in skill_registry.list_installed():
        requires_env = s.get("requires_env", [])
        env_status = {k: bool(env_values.get(k, "").strip()) for k in requires_env}
        env_vals = {k: env_values.get(k, "") for k in requires_env}
        configured = all(env_status.values()) if requires_env else True
        enriched.append({**s, "env_status": env_status, "env_values": env_vals, "configured": configured})
    return {"skills": enriched}


@router.post("/api/skills/install/{skill_name}")
async def install_skill(skill_name: str, request: Request) -> dict:
    """Installe un skill depuis le repo jarvis-skills."""
    from skills.installer import skill_installer
    from skills.registry import skill_registry
    result = await skill_installer.install(skill_name)
    if result.get("success"):
        tool_registry = getattr(request.app.state, "tool_registry", None)
        if tool_registry:
            tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
    return result


@router.delete("/api/skills/uninstall/{skill_name}")
async def uninstall_skill(skill_name: str, request: Request) -> dict:
    """Désinstalle un skill."""
    from skills.installer import skill_installer
    from skills.registry import skill_registry
    result = skill_installer.uninstall(skill_name)
    if result.get("success"):
        tool_registry = getattr(request.app.state, "tool_registry", None)
        if tool_registry:
            tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
    return result


@router.post("/api/skills/reload")
async def reload_skills(request: Request) -> dict:
    """Recharge les skills et leurs outils sans redémarrer Jarvis."""
    from skills.registry import skill_registry
    skill_registry.reload()
    tool_registry = getattr(request.app.state, "tool_registry", None)
    if tool_registry:
        tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
    return {
        "success": True,
        "loaded": len(skill_registry.get_all()),
    }


@router.get("/api/settings/env-status")
async def get_env_status(keys: str = Query("")) -> dict:
    """Retourne True/False par clé env — jamais les valeurs."""
    from dotenv import dotenv_values
    env_values = dotenv_values(".env")
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    return {k: bool(env_values.get(k, "").strip()) for k in key_list}


# ── Permissions API ───────────────────────────────────────────────────────────


class PermissionPatch(BaseModel):
    enabled: bool


@router.get("/api/permissions")
async def get_permissions() -> dict[str, bool]:
    """Retourne l'état courant des permissions runtime."""
    return _perm_store.all()


@router.patch("/api/permissions/{key}")
async def patch_permission(key: str, body: PermissionPatch) -> dict[str, object]:
    """Active ou désactive une permission runtime (screen, camera, files)."""
    _perm_store.set(key, body.enabled)
    return {"key": key, "enabled": body.enabled}


# ── Sessions API ─────────────────────────────────────────────────────────────

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
        result.append({
            "id":            session_id,
            "date":          date_str,
            "preview":       default_preview,
            "title":         titles.get(session_id) or default_preview,
            "message_count": msg_count,
        })
    return result


class _TitleBody(BaseModel):
    title: str


@router.put("/api/sessions/{session_id}/title")
async def rename_session(session_id: str, body: _TitleBody, request: Request) -> dict:
    """Renomme une session (stocké dans session_titles.json)."""
    if not body.title.strip():
        raise HTTPException(400, "Le titre ne peut pas être vide.")
    titles = _load_titles(request)
    titles[session_id] = body.title.strip()
    _save_titles(request, titles)
    return {"id": session_id, "title": body.title.strip()}


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


# ── Shared models ─────────────────────────────────────────────────────────────

class _ContentBody(BaseModel):
    content: str


# ── Memory API ────────────────────────────────────────────────────────────────

def _mem_dir(request: Request) -> Path:
    from config.settings import settings
    return Path(settings.memory_dir)


@router.get("/api/memory/index")
async def get_memory_index(request: Request) -> dict:
    p = _mem_dir(request) / "MEMORY.md"
    return {"content": p.read_text(encoding="utf-8") if p.exists() else ""}


@router.put("/api/memory/index")
async def put_memory_index(body: _ContentBody, request: Request) -> dict:
    p = _mem_dir(request) / "MEMORY.md"
    p.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.get("/api/memory/topics")
async def list_memory_topics(request: Request) -> list[dict]:
    topics_dir = _mem_dir(request) / "topics"
    if not topics_dir.exists():
        return []
    result = []
    for p in sorted(topics_dir.glob("*.md")):
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        result.append({
            "name": p.name,
            "size": stat.st_size,
            "mtime": mtime.isoformat(),
        })
    return result


@router.get("/api/memory/topics/{name}")
async def get_memory_topic(name: str, request: Request) -> dict:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Nom invalide")
    p = _mem_dir(request) / "topics" / name
    if not p.exists():
        raise HTTPException(404, "Fichier introuvable")
    return {"name": name, "content": p.read_text(encoding="utf-8")}


@router.put("/api/memory/topics/{name}")
async def put_memory_topic(name: str, body: _ContentBody, request: Request) -> dict:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Nom invalide")
    p = _mem_dir(request) / "topics" / name
    if not p.exists():
        raise HTTPException(404, "Fichier introuvable")
    p.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.post("/api/memory/autodream")
async def trigger_autodream(request: Request) -> dict:
    import asyncio
    auto_dream = getattr(request.app.state, "auto_dream", None)
    session_manager = getattr(request.app.state, "session_manager", None)
    if not auto_dream:
        raise HTTPException(503, "AutoDream non disponible")
    asyncio.create_task(auto_dream._run_micro_safe(user_message="[trigger manuel]", assistant_message=""), name="autodream-manual")
    return {"triggered": True}


# ── Tools API ─────────────────────────────────────────────────────────────────

@router.get("/api/tools")
async def list_tools_endpoint(request: Request) -> list[dict]:
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        return []
    return [
        {"name": s.get("name", ""), "description": s.get("description", "")}
        for s in registry.core_schemas()
    ]


# ── System API ────────────────────────────────────────────────────────────────

@router.get("/api/system/stats")
async def system_stats(request: Request) -> dict:
    from agent.project_store import WORKSPACE_DIR
    from config.settings import settings

    mem_dir = _mem_dir(request)
    topics_dir = mem_dir / "topics"
    sessions_dir = mem_dir / "sessions"

    # Projects
    proj_files = list(WORKSPACE_DIR.glob("*/.jarvis/state.json")) if WORKSPACE_DIR.exists() else []
    proj_total = len(proj_files)
    proj_running = proj_done = 0
    for f in proj_files:
        try:
            d = json.loads(f.read_text())
            s = d.get("status", "")
            if s == "running":
                proj_running += 1
            elif s == "done":
                proj_done += 1
        except Exception:
            pass

    # Memory
    topics_count = len(list(topics_dir.glob("*.md"))) if topics_dir.exists() else 0
    topics_size = sum(p.stat().st_size for p in topics_dir.glob("*.md")) if topics_dir.exists() else 0

    # Sessions
    sess_files = list(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else []
    sess_total = len(sess_files)
    sess_size = sum(p.stat().st_size for p in sess_files)

    return {
        "projects": {"total": proj_total, "running": proj_running, "done": proj_done},
        "memory":   {"topics": topics_count, "size_kb": round(topics_size / 1024, 1)},
        "sessions": {"total": sess_total, "size_mb": round(sess_size / 1024 / 1024, 2)},
        "config": {
            "llm_provider":  settings.llm_provider,
            "model":         settings.anthropic_model,
            "voice_model":   settings.voice_anthropic_model,
            "vision_model":  settings.vision_model,
            "tts_provider":  settings.tts_provider,
            "whisper_model": settings.whisper_model,
        },
        "workspace": str(WORKSPACE_DIR.resolve()),
    }


@router.get("/api/system/logs")
async def system_logs() -> list[str]:
    return list(_log_buffer)


@router.post("/api/projects/{project_id}/retry")
async def retry_project(project_id: str, request: Request) -> dict:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrateur non disponible")
    project = await orchestrator.retry_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")
    return {"ok": True, "project_id": project.id, "status": project.status}


@router.delete("/api/system/projects/done")
async def cleanup_done_projects(request: Request) -> dict:
    from agent.project_store import WORKSPACE_DIR
    orch = getattr(request.app.state, "orchestrator", None)
    removed = 0
    for state_file in list(WORKSPACE_DIR.glob("*/.jarvis/state.json")):
        try:
            d = json.loads(state_file.read_text())
            if d.get("status") in ("done", "failed", "killed"):
                workspace = state_file.parent.parent
                shutil.rmtree(workspace, ignore_errors=True)
                removed += 1
        except Exception:
            pass
    return {"removed": removed}


@router.post("/api/system/restart")
async def restart_jarvis() -> dict:
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)
    return {"restarting": True}


# ── Proactive / Command Center ────────────────────────────────────────────────

@router.get("/api/initiatives")
async def get_initiatives() -> list[dict]:
    """Initiatives en attente (mode VALIDATE)."""
    from proactive.store import InitiativeStore
    store = InitiativeStore()
    initiatives = store.load_pending()
    return [
        {
            "id":           i.id,
            "type":         i.type,
            "title":        i.title,
            "context":      i.context,
            "reasoning":    i.reasoning,
            "action":       i.action,
            "priority":     i.priority,
            "execution_mode": i.execution_mode,
            "draft_content": i.draft_content,
            "created_at":   i.created_at.isoformat(),
        }
        for i in initiatives
    ]


class RectifyBody(BaseModel):
    correction: str


@router.post("/api/initiatives/{initiative_id}/approve")
async def approve_initiative(initiative_id: str, request: Request) -> dict:
    import asyncio
    from proactive.schemas import InitiativeType
    from proactive.store import InitiativeStore
    from loguru import logger as _log

    store = InitiativeStore()
    init  = store.get_by_id(initiative_id)
    if not init:
        raise HTTPException(404, "Initiative introuvable")

    result: dict = {"status": "approved", "type": str(init.type)}

    try:
        if init.type == InitiativeType.DRAFT_RESPONSE:
            from config.settings import settings as _s
            from tools.gmail import send_gmail_draft
            msg_id = await send_gmail_draft(
                draft_content=init.draft_content or "",
                credentials_path=Path(_s.google_credentials_path),
                token_path=Path(_s.google_token_path).parent / "google_gmail_token.json",
            )
            result["message_id"] = msg_id
            _log.info(f"Initiative {initiative_id}: email envoyé", to=init.draft_content[:40] if init.draft_content else "")

        elif init.type == InitiativeType.AUTO_TASK:
            orchestrator = getattr(request.app.state, "orchestrator", None)
            if orchestrator:
                mission = init.mission_description or init.action
                asyncio.create_task(
                    orchestrator.create_and_run(mission),
                    name=f"initiative-{initiative_id[:8]}",
                )
                result["mission_launched"] = True
                _log.info(f"Initiative {initiative_id}: mission lancée", mission=mission[:60])
            else:
                result["warning"] = "Orchestrateur non disponible"

        else:
            _log.info(f"Initiative {initiative_id} approuvée", type=init.type, title=init.title)

    except Exception as e:
        _log.error(f"Initiative approve error ({init.type}): {e}")
        result["error"] = str(e)

    store.update_status(initiative_id, "approved")
    return result


@router.post("/api/initiatives/{initiative_id}/reject")
async def reject_initiative(initiative_id: str) -> dict:
    from proactive.store import InitiativeStore
    InitiativeStore().update_status(initiative_id, "rejected")
    return {"status": "rejected"}


@router.post("/api/initiatives/{initiative_id}/rectify")
async def rectify_initiative(initiative_id: str, body: RectifyBody) -> dict:
    from proactive.initiative_generator import InitiativeGenerator
    from proactive.store import InitiativeStore

    store = InitiativeStore()
    init  = store.get_by_id(initiative_id)
    if not init:
        raise HTTPException(404, "Initiative introuvable")

    generator = InitiativeGenerator()
    new_init  = await generator.rectify(init, body.correction)
    if not new_init:
        raise HTTPException(500, "Régénération échouée")

    store.update_initiative(initiative_id, {
        "title":               new_init.title,
        "context":             new_init.context,
        "reasoning":           new_init.reasoning,
        "action":              new_init.action,
        "priority":            new_init.priority,
        "execution_mode":      new_init.execution_mode,
        "draft_content":       new_init.draft_content,
        "mission_description": new_init.mission_description,
    })

    return {
        "id":                  initiative_id,
        "type":                new_init.type,
        "title":               new_init.title,
        "context":             new_init.context,
        "reasoning":           new_init.reasoning,
        "action":              new_init.action,
        "priority":            new_init.priority,
        "execution_mode":      new_init.execution_mode,
        "draft_content":       new_init.draft_content,
        "mission_description": new_init.mission_description,
        "created_at":          init.created_at.isoformat(),
    }


@router.post("/api/proactive/run")
async def run_proactive_now(request: Request) -> dict:
    """Force un cycle proactif immédiat."""
    engine = getattr(request.app.state, "proactive_engine", None)
    if not engine:
        raise HTTPException(503, "ProactiveEngine non disponible")
    import asyncio
    asyncio.create_task(engine.run_now(), name="proactive-manual")
    return {"triggered": True}


@router.get("/api/proactive/status")
async def proactive_status(request: Request) -> dict:
    """Statut du moteur proactif (dernière exécution, prochaine)."""
    engine = getattr(request.app.state, "proactive_engine", None)
    if not engine:
        return {"running": False}
    last_run = engine._last_run.isoformat() if engine._last_run else None
    return {
        "running":    engine._running,
        "interval_s": engine._interval,
        "last_run":   last_run,
    }


# ── Vision webhooks ───────────────────────────────────────────────────────────


class ObjectDetectedPayload(BaseModel):
    new_objects: list[str]
    all_objects: list[str] = []


@router.post("/api/webhooks/object_detected")
async def webhook_object_detected(body: ObjectDetectedPayload, request: Request) -> dict:
    """Reçoit les détections d'objets du daemon vision (YOLOv8n)."""
    if not body.new_objects:
        return {"status": "ignored"}

    notifications = request.app.state.notifications
    objects_str = ", ".join(body.new_objects)
    notifications.add(
        f"Nouveaux objets détectés devant la caméra : {objects_str}. "
        "Mentionne-le discrètement si c'est pertinent pour la conversation en cours, sinon ignore."
    )
    return {"status": "ok", "new_objects": body.new_objects}


class FaceRecognitionPayload(BaseModel):
    recognized: bool
    name: str = "unknown"
    confidence: float = 0.0


@router.post("/api/webhooks/face_recognition")
async def webhook_face_recognition(body: FaceRecognitionPayload, request: Request) -> dict:
    """Reçoit les changements d'état de reconnaissance faciale du daemon vision."""
    proactive = request.app.state.proactive_queue
    proactive.broadcast_event({
        "type": "face_recognition",
        "recognized": body.recognized,
        "name": body.name,
        "confidence": body.confidence,
    })
    if body.recognized:
        notifications = request.app.state.notifications
        notifications.add(
            f"Barth est détecté devant la caméra (confiance {body.confidence:.0%}). Mode normal actif."
        )
    return {"status": "ok"}


# ── Approvals API ────────────────────────────────────────────────────────────


@router.get("/api/approvals/config")
async def get_approvals_config() -> dict:
    """Retourne la configuration courante des approbations."""
    from config.approvals import approval_config
    from dataclasses import asdict
    return asdict(approval_config)


class ApprovalCategoryUpdate(BaseModel):
    mode: str  # "always" | "ask" | "never"


@router.patch("/api/approvals/config/{category}")
async def update_approval_category(category: str, body: ApprovalCategoryUpdate) -> dict:
    """Met à jour le mode d'une catégorie d'approbation."""
    from config.approvals import ApprovalMode, approval_config, save_approval_config
    if not hasattr(approval_config, category):
        raise HTTPException(404, f"Catégorie inconnue: {category}")
    try:
        mode = ApprovalMode(body.mode)
    except ValueError:
        raise HTTPException(400, f"Mode invalide: {body.mode}. Valeurs: always, ask, never")
    object.__setattr__(approval_config, category, mode)
    save_approval_config(approval_config)
    return {"category": category, "mode": body.mode}


class ApprovalResolveBody(BaseModel):
    approved: bool


@router.post("/api/approvals/{action_id}/resolve")
async def resolve_approval(action_id: str, body: ApprovalResolveBody, request: Request) -> dict:
    """Résout une demande d'approbation en attente."""
    checker = getattr(request.app.state, "approval_checker", None)
    if checker is None:
        raise HTTPException(503, "ApprovalChecker non disponible")
    checker.resolve(action_id, body.approved)
    return {"status": "ok", "approved": body.approved}


@router.post("/api/vision/faces/add")
async def add_face(request: Request) -> dict:
    """Ajoute un visage de référence à chaud. Body: {name: str, path: str}"""
    data = await request.json()
    name = data.get("name", "").strip()
    path = data.get("path", "").strip()

    if not name or not path:
        raise HTTPException(400, "name et path requis")

    from vision.daemon import get_face_recognizer
    recognizer = get_face_recognizer()
    if recognizer is None:
        raise HTTPException(503, "FaceRecognizer non actif (FACE_RECOGNITION_ENABLED=false ?)")

    ok = recognizer.add_face(name, path)
    return {"success": ok, "name": name}


# ── LiveKit Voice Agent bridge ────────────────────────────────────────────────


class ToolExecuteRequest(BaseModel):
    tool: str
    params: dict = {}


# ── Conso API ─────────────────────────────────────────────────────────────────

@router.get("/api/conso/session")
async def conso_session() -> dict:
    from core.tracking import tracker
    return tracker.get_session_summary()


@router.get("/api/conso/daily")
async def conso_daily() -> list[dict]:
    from core.tracking import tracker
    return tracker.get_daily_totals(7)


@router.get("/api/conso/providers")
async def conso_providers() -> dict:
    from core.tracking import tracker
    summary = tracker.get_session_summary()
    return summary.get("providers", {})


@router.get("/api/conso/calls")
async def conso_calls() -> list[dict]:
    from core.tracking import tracker
    return tracker.get_recent_calls(200)


@router.get("/api/conso/daily_providers")
async def conso_daily_providers() -> list[dict]:
    from core.tracking import tracker
    return tracker.get_daily_by_provider(7)


@router.get("/api/conso/monthly")
async def conso_monthly() -> dict:
    from core.tracking import tracker
    return tracker.get_monthly_totals()


# ── Settings API ──────────────────────────────────────────────────────────────

_ENV_PATH = Path(".env")

_SENSITIVE_KEYS = {
    "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID",
    "OPENAI_API_KEY", "DEEPGRAM_API_KEY", "GOOGLE_API_KEY",
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    "NOTION_TOKEN", "MISTRAL_API_KEY", "AISSTREAM_KEY",
    "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET",
}

# Keys that require a restart to take effect
_RESTART_KEYS = {
    "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    "LLM_PROVIDER", "ANTHROPIC_MODEL", "VOICE_ANTHROPIC_MODEL",
    "TTS_PROVIDER", "ELEVENLABS_MODEL",
}

_SETTINGS_FIELD_MAP: dict[str, str] = {
    "TTS_PROVIDER":               "tts_provider",
    "ELEVENLABS_MODEL":           "elevenlabs_model",
    "WHISPER_MODEL":              "whisper_model",
    "LLM_PROVIDER":               "llm_provider",
    "ANTHROPIC_MODEL":            "anthropic_model",
    "VOICE_ANTHROPIC_MODEL":      "voice_anthropic_model",
    "VISION_MODEL":               "vision_model",
    "DOCKER_ENABLED":             "docker_enabled",
    "DOCKER_BASE_IMAGE":          "docker_base_image",
    "DOCKER_MEMORY_LIMIT":        "docker_memory_limit",
    "DOCKER_CPU_LIMIT":           "docker_cpu_limit",
    "DOCKER_TIMEOUT_SECONDS":     "docker_timeout_seconds",
    "VISION_OBJECT_DETECTION":    "vision_object_detection",
    "VISION_WEBCAM_INDEX":        "vision_webcam_index",
    "VISION_YOLO_CONFIDENCE":     "vision_yolo_confidence",
    "LOG_LEVEL":                  "log_level",
    "BRIEFING_HOUR":              "briefing_hour",
    "CALENDAR_REMINDER_MINUTES":  "calendar_reminder_minutes",
    "QUEBEC_MODE":                "quebec_mode",
}


def _mask(value: str) -> str:
    if not value or value.startswith("..."):
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return value[:4] + "•" * min(len(value) - 4, 24)


def _read_env() -> dict[str, str]:
    if not _ENV_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(updates: dict[str, str]) -> None:
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines() if _ENV_PATH.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@router.get("/api/settings")
async def get_settings_endpoint() -> dict:
    from config.settings import settings as _s
    env = _read_env()

    def _env_val(key: str) -> str:
        return env.get(key, os.getenv(key, ""))

    api_keys_masked = {k: _mask(_env_val(k)) for k in sorted(_SENSITIVE_KEYS)}

    return {
        "audio": {
            "tts_provider":      _s.tts_provider,
            "elevenlabs_model":  _s.elevenlabs_model,
            "whisper_model":     _s.whisper_model,
        },
        "llm": {
            "llm_provider":          _s.llm_provider,
            "anthropic_model":       _s.anthropic_model,
            "voice_anthropic_model": _s.voice_anthropic_model,
            "vision_model":          _s.vision_model,
        },
        "api_keys": api_keys_masked,
        "docker": {
            "docker_enabled":         _s.docker_enabled,
            "docker_base_image":      _s.docker_base_image,
            "docker_memory_limit":    _s.docker_memory_limit,
            "docker_cpu_limit":       _s.docker_cpu_limit,
            "docker_timeout_seconds": _s.docker_timeout_seconds,
        },
        "proactive": {
            "briefing_hour":             _s.briefing_hour,
            "calendar_reminder_minutes": _s.calendar_reminder_minutes,
        },
        "vision": {
            "vision_object_detection": _s.vision_object_detection,
            "vision_webcam_index":     _s.vision_webcam_index,
            "vision_yolo_confidence":  _s.vision_yolo_confidence,
        },
        "memory": {
            "memory_dir": _s.memory_dir,
        },
        "jarvis": {
            "log_level":   _s.log_level,
            "environment": _s.environment,
            "quebec_mode": _s.quebec_mode,
        },
        "approvals": __import__('dataclasses').asdict(__import__('config.approvals', fromlist=['approval_config']).approval_config),
    }


class SettingUpdateBody(BaseModel):
    key: str
    value: str


@router.post("/api/settings/update")
async def update_setting(body: SettingUpdateBody) -> dict:
    from config.settings import settings as _s
    env_key = body.key.upper()
    _write_env({env_key: body.value})

    field_name = _SETTINGS_FIELD_MAP.get(env_key)
    if field_name and hasattr(_s, field_name):
        fields = type(_s).model_fields
        field = fields.get(field_name)
        annotation = field.annotation if field else None
        try:
            if annotation is bool:
                converted: Any = body.value.lower() in ("true", "1", "yes", "on")
            elif annotation is int:
                converted = int(body.value)
            elif annotation is float:
                converted = float(body.value)
            else:
                converted = body.value
            object.__setattr__(_s, field_name, converted)
        except (ValueError, TypeError):
            object.__setattr__(_s, field_name, body.value)

    needs_restart = env_key in _RESTART_KEYS
    return {"ok": True, "key": body.key, "needs_restart": needs_restart}


@router.get("/api/settings/devices")
async def get_devices() -> list:
    import platform
    import subprocess
    import psutil

    devices: list[dict] = []
    sys_name = platform.system()

    # ── Machine locale ────────────────────────────────────────────────────────
    cpu_pct = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    ram_used = round(mem.used / (1024 ** 3), 1)
    ram_total = round(mem.total / (1024 ** 3), 1)
    battery = psutil.sensors_battery()

    if sys_name == "Darwin":
        try:
            model = subprocess.check_output(
                ["sysctl", "-n", "hw.model"], text=True, timeout=3
            ).strip()
        except Exception:
            model = platform.node().replace(".local", "") or "Mac"
        chip = platform.processor() or platform.machine()
        host_id = f"mac · {chip}"
    elif sys_name == "Windows":
        model = platform.node()
        host_id = f"windows · {platform.machine()}"
    else:
        model = platform.node().replace(".local", "") or "Linux"
        host_id = f"linux · {platform.machine()}"

    devices.append({
        "name": model,
        "id": host_id,
        "status": "Active",
        "col": "green",
        "a": ["CPU", f"{cpu_pct}%"],
        "b": ["Battery", f"{int(battery.percent)}%"] if battery else ["RAM", f"{ram_used} / {ram_total} GB"],
        "type": "host",
    })

    try:
        from keypad.usb import usb_status

        st = usb_status()
        hid = bool(st.get("hidPresent"))
        boot = bool(st.get("bootloaderPresent"))
        if hid:
            mp_status = "Connected"
            mp_col = "green"
            a_pair = ("Mode", "HID")
            b_pair = ("Firmware", "Keypad Studio")
        elif boot:
            mp_status = "Nearby"
            mp_col = "accent"
            a_pair = ("Mode", "Bootloader")
            b_pair = ("Flash", "USB prêt")
        else:
            mp_status = "Nearby"
            mp_col = "muted"
            a_pair = ("Mode", "—")
            b_pair = ("Studio", "Ajouter via Keypad")
        devices.insert(1, {
            "name": "Macropad 2K",
            "id": "macropad · Le Labo",
            "status": mp_status,
            "col": mp_col,
            "a": list(a_pair),
            "b": list(b_pair),
            "type": "macropad",
        })
    except Exception:
        pass

    # ── Bluetooth ─────────────────────────────────────────────────────────────
    if sys_name == "Darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPBluetoothDataType"], text=True, timeout=6
            )
            _parse_bt_macos(out, devices)
        except Exception:
            pass
    elif sys_name == "Windows":
        try:
            _parse_bt_windows(devices)
        except Exception:
            pass

    return devices


_BT_ID_MAP = {
    "headphones": "audio · BT",
    "headset":    "audio · BT",
    "mouse":      "mouse · BT",
    "keyboard":   "keyboard · BT",
    "gamepad":    "gamepad · BT",
    "joystick":   "gamepad · BT",
}


def _parse_bt_macos(out: str, devices: list) -> None:
    import re
    section: str | None = None
    cur: dict | None = None

    def _flush(d: dict | None) -> None:
        if not d:
            return
        name = d["_name"]
        if re.fullmatch(r"[0-9A-Fa-f:]+", name):
            return  # bare MAC address — skip
        bt_type = d["_type"] or "Device"
        connected = d["_connected"]
        devices.append({
            "name": name,
            "id": _BT_ID_MAP.get(bt_type.lower(), "bluetooth · BT"),
            "status": "Connected" if connected else "Nearby",
            "col": "green" if connected else "muted",
            "a": ["Type", bt_type],
            "b": ["Vendor", d["_vendor"] or "—"],
            "type": "bluetooth",
        })

    for line in out.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 6 and stripped.endswith(":"):
            _flush(cur)
            cur = None
            if "Not Connected" in stripped:
                section = "not_connected"
            elif "Connected" in stripped:
                section = "connected"
            else:
                section = None
            continue

        if section is None:
            continue

        if indent == 10 and stripped.endswith(":"):
            _flush(cur)
            cur = {
                "_name": stripped[:-1],
                "_connected": section == "connected",
                "_type": None,
                "_vendor": None,
            }
            continue

        if cur and indent >= 14 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if key == "Minor Type":
                cur["_type"] = val
            elif key == "Vendor ID" and "004C" in val:
                cur["_vendor"] = "Apple"

    _flush(cur)


def _parse_bt_windows(devices: list) -> None:
    import json as _json
    import re
    import subprocess

    skip = re.compile(
        r"(?i)enumerator|microsoft\s+bluetooth|^\s*intel\(r\)\s+wireless\s+bluetooth|"
        r"realtek\s+bluetooth|broadcom\s+bluetooth|virtual|rfcomm|"
        r"generic\s+attribute|device\s+association|le\s+audio|"
        r"^bluetooth\s+device\s*\("
    )
    ps = (
        "Get-PnpDevice -Class 'Bluetooth' -PresentOnly | "
        "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps],
        text=True,
        timeout=12,
    )
    items = _json.loads(out)
    if isinstance(items, dict):
        items = [items]
    seen: set[str] = set()
    for item in items:
        name = (item.get("FriendlyName") or "").strip() or "Unknown"
        if skip.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        status = (item.get("Status") or "Unknown").strip()
        ok = status == "OK"
        nl = name.lower()
        if "mouse" in nl:
            bt_id = _BT_ID_MAP["mouse"]
        elif "keyboard" in nl:
            bt_id = _BT_ID_MAP["keyboard"]
        elif "headphone" in nl or "headset" in nl or "airpods" in nl or "buds" in nl:
            bt_id = _BT_ID_MAP["headphones"]
        elif "gamepad" in nl or "controller" in nl or "xbox" in nl or "dualshock" in nl:
            bt_id = _BT_ID_MAP["gamepad"]
        else:
            bt_id = "bluetooth · BT"
        devices.append({
            "name": name,
            "id": bt_id,
            "status": "Connected" if ok else "Nearby",
            "col": "green" if ok else "muted",
            "a": ["Type", "Bluetooth"],
            "b": ["État", status],
            "type": "bluetooth",
        })


@router.get("/api/settings/connectors")
async def get_connectors() -> list:
    import json as _json
    from datetime import timezone

    env = _read_env()

    def _env_ok(*keys: str) -> bool:
        def _valid(v: str) -> bool:
            v = v.strip()
            return bool(v) and not v.startswith("...") and v != "—"
        return all(_valid(env.get(k) or os.getenv(k, "")) for k in keys)

    def _token_status(path: str) -> str:
        p = Path(path)
        if not p.exists():
            return "off"
        try:
            data = _json.loads(p.read_text())
            expiry = data.get("expiry") or data.get("expires_at")
            if expiry:
                from datetime import datetime as _dt
                exp = _dt.fromisoformat(expiry.replace("Z", "+00:00"))
                if exp < _dt.now(timezone.utc):
                    return "expired"
            return "on"
        except Exception:
            return "on"

    from config.settings import settings as _s

    connectors = [
        {
            "name": "Gmail",
            "sub": "OAuth · lecture + envoi",
            "status": _token_status(_s.google_credentials_path.replace("credentials", "gmail_token")),
        },
        {
            "name": "Google Calendar",
            "sub": "OAuth · lecture + écriture",
            "status": _token_status(_s.google_token_path),
        },
        {
            "name": "Spotify",
            "sub": "OAuth · lecture musicale",
            "status": (
                "on" if _token_status(_s.spotify_token_path) == "on" and _env_ok("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
                else "expired" if _token_status(_s.spotify_token_path) == "expired"
                else "off"
            ),
        },
        {
            "name": "Notion",
            "sub": "token intégration · workspace",
            "status": "on" if _env_ok("NOTION_TOKEN") else "off",
        },
        {
            "name": "Anthropic (Claude)",
            "sub": "LLM principal",
            "status": "on" if _env_ok("ANTHROPIC_API_KEY") else "off",
        },
        {
            "name": "ElevenLabs",
            "sub": "TTS — voix de Jarvis",
            "status": "on" if _env_ok("ELEVENLABS_API_KEY") else "off",
        },
        {
            "name": "OpenAI",
            "sub": "Whisper STT / fallback LLM",
            "status": "on" if _env_ok("OPENAI_API_KEY") else "off",
        },
        {
            "name": "Google (API Key)",
            "sub": "Gemini · autres services Google",
            "status": "on" if _env_ok("GOOGLE_API_KEY") else "off",
        },
        {
            "name": "LiveKit",
            "sub": "agent vocal temps réel",
            "status": "on" if _env_ok("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET") else "off",
        },
        {
            "name": "Deepgram",
            "sub": "STT alternatif",
            "status": "on" if _env_ok("DEEPGRAM_API_KEY") else "off",
        },
        {
            "name": "Mistral",
            "sub": "LLM alternatif",
            "status": "on" if _env_ok("MISTRAL_API_KEY") else "off",
        },
        {
            "name": "Keypad Studio",
            "sub": "Firmware CH552 · /keypad",
            "status": "on",
        },
    ]
    return connectors


@router.get("/api/settings/voices")
async def get_voices() -> list[dict]:
    import httpx
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": key},
            )
        if r.status_code == 200:
            voices = r.json().get("voices", [])
            return [{"id": v["voice_id"], "name": v["name"]} for v in voices]
    except Exception:
        pass
    return []


class TestKeyBody(BaseModel):
    provider: str
    key: str


@router.post("/api/settings/test-key")
async def test_api_key(body: TestKeyBody) -> dict:
    import httpx
    provider = body.provider.lower()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if provider == "anthropic":
                r = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": body.key, "anthropic-version": "2023-06-01"},
                )
                return {"ok": r.status_code == 200}
            if provider == "elevenlabs":
                r = await client.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": body.key},
                )
                return {"ok": r.status_code == 200}
            if provider == "openai":
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {body.key}"},
                )
                return {"ok": r.status_code == 200}
            if provider == "deepgram":
                r = await client.get(
                    "https://api.deepgram.com/v1/projects",
                    headers={"Authorization": f"Token {body.key}"},
                )
                return {"ok": r.status_code == 200}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "Provider inconnu"}


@router.post("/api/tools/execute")
async def execute_tool(body: ToolExecuteRequest, request: Request) -> dict:
    """Bridge générique — le voice agent LiveKit appelle les outils Jarvis via cet endpoint."""
    registry = request.app.state.tool_registry
    result = await registry.call(body.tool, body.params)
    return {
        "success": not result.is_error,
        "result": result.content,
    }


class VoiceGenerateRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/api/voice/generate")
async def voice_generate(body: VoiceGenerateRequest, request: Request):
    """Bridge voix → gateway Jarvis.
    Même pipeline que le chat texte (Claude + outils + mémoire).
    Partage la session si session_id fourni.
    """
    import asyncio
    from fastapi.responses import StreamingResponse as _SR

    from background.worker import BackgroundTask
    from core.router import RouteEnum

    gateway = request.app.state.voice_gateway
    worker = request.app.state.worker
    orchestrator = getattr(request.app.state, "orchestrator", None)
    consolidation = request.app.state.consolidation
    auto_dream = request.app.state.auto_dream

    # Hint vocal : réponse courte sans markdown
    voice_msg = f"{body.message}\n[voix]"

    session, route, response = await gateway.handle(
        message=voice_msg,
        session_id=body.session_id,
        stream=True,
    )

    message_original = body.message

    async def _stream():
        full = ""
        try:
            if isinstance(response, str):
                full = response
                yield response
            else:
                async for chunk in response:
                    full += chunk
                    yield chunk
        except Exception as e:
            from loguru import logger as _log
            _log.error("Voice generate stream error", error=str(e))
            full = "Désolé, j'ai eu un souci."
            yield full

        session.add_message("assistant", full)

        # Routing BG / PROJECT (lancé après stream)
        if route is RouteEnum.BACKGROUND:
            worker.submit(BackgroundTask(
                session_id=str(session.id), instruction=message_original
            ))
        elif route is RouteEnum.PROJECT and orchestrator:
            asyncio.create_task(
                orchestrator.create_and_run(message_original),
                name=f"voice-project-{str(session.id)[:8]}",
            )

        # Consolidation mémoire (non-bloquant)
        asyncio.create_task(
            consolidation._run_safe(
                user_message=message_original, assistant_message=full
            ),
            name="voice-consolidation",
        )
        asyncio.create_task(
            auto_dream._run_micro_safe(
                user_message=message_original, assistant_message=full
            ),
            name="voice-autodream",
        )

    return _SR(_stream(), media_type="text/plain")


@router.get("/api/voice/token")
async def get_voice_token(session_id: str | None = None) -> dict:
    """Génère un token LiveKit et dispatche l'agent jarvis dans la room."""
    import os
    import uuid
    from livekit.api import (
        AccessToken, VideoGrants,
        LiveKitAPI, CreateRoomRequest, CreateAgentDispatchRequest,
    )

    api_key    = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")

    room_name = f"jarvis-{uuid.uuid4().hex[:8]}"

    async with LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret) as lkapi:
        await lkapi.room.create_room(CreateRoomRequest(name=room_name))
        await lkapi.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(room=room_name, agent_name="jarvis")
        )

    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity("barth")
        .with_name("Barth")
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        .to_jwt()
    )

    return {"token": token, "url": livekit_url}


# ── Analytics API ─────────────────────────────────────────────────────────────

@router.get("/api/analytics/jarvis")
async def analytics_jarvis(days: int = 30) -> dict:
    from api.analytics import get_jarvis_stats
    return await get_jarvis_stats(days)


@router.get("/api/analytics/youtube")
async def analytics_youtube(days: int = 7) -> dict:
    from api.analytics import get_youtube_stats
    return await get_youtube_stats(days)


@router.get("/api/analytics/summary")
async def analytics_summary() -> dict:
    from api.analytics import get_analytics_summary
    return await get_analytics_summary()
