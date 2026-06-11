from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from config.settings import settings
from jarvis.capabilities.skills.registry import skill_registry
from jarvis.engine.mission.project_store import WORKSPACE_DIR
from jarvis.kernel.paths import MEMORY_DATA_DIR

router = APIRouter()


def _mem_dir(request: Request) -> Path:  # noqa: ARG001 — request ignoré, conservé pour signature API

    return Path(settings.memory_dir)


@router.get("/api/health")
async def jarvis_doctor() -> dict:
    """Rapport de santé complet de tous les composants Jarvis."""
    import asyncio

    import httpx

    checks: dict[str, dict] = {}
    checks["fastapi"] = {"status": "ok", "detail": "En ligne"}

    async with httpx.AsyncClient(timeout=5) as c:
        try:
            r = await c.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                    "anthropic-version": "2023-06-01",
                },
            )
            checks["anthropic"] = {
                "status": "ok" if r.status_code == 200 else "error",
                "detail": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            }
        except Exception:
            checks["anthropic"] = {"status": "error", "detail": "Inaccessible"}

        try:
            r = await c.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", "")},
            )
            checks["elevenlabs"] = {
                "status": "ok" if r.status_code == 200 else "error",
                "detail": os.getenv("ELEVENLABS_MODEL", "—"),
            }
        except Exception:
            checks["elevenlabs"] = {"status": "error", "detail": "Inaccessible"}

        try:
            r = await c.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY', '')}"},
            )
            checks["deepgram"] = {
                "status": "ok" if r.status_code == 200 else "error",
                "detail": "Nova-2",
            }
        except Exception:
            checks["deepgram"] = {"status": "error", "detail": "Inaccessible"}

    token = os.getenv("MAPBOX_TOKEN", "")
    checks["mapbox"] = {
        "status": "ok" if token else "warning",
        "detail": "Token présent" if token else "MAPBOX_TOKEN manquant",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        checks["docker"] = {
            "status": "ok" if proc.returncode == 0 else "error",
            "detail": "Disponible" if proc.returncode == 0 else "Non disponible",
        }
    except Exception:
        checks["docker"] = {"status": "error", "detail": "Non installé"}


    mem_topics = MEMORY_DATA_DIR / "topics"
    topics = list(mem_topics.glob("*.md")) if mem_topics.exists() else []
    checks["memory"] = {"status": "ok", "detail": f"{len(topics)} topics"}

    try:

        skills = skill_registry.list_installed()
        checks["skills"] = {"status": "ok", "detail": f"{len(skills)} installés"}
    except Exception:
        checks["skills"] = {"status": "warning", "detail": "Registre indisponible"}

    checks["proactive"] = {"status": "ok", "detail": "Actif"}

    overall = "ok" if all(v["status"] == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@router.get("/api/wakeup/status")
async def wakeup_status() -> dict:
    """Retourne si la séquence wake up est activée (contrôlé via WAKEUP_ENABLED dans .env)."""

    return {"enabled": settings.wakeup_enabled, "user_firstname": settings.user_firstname}


@router.get("/api/system/stats")
async def system_stats(request: Request) -> dict:

    mem_dir = _mem_dir(request)
    topics_dir = mem_dir / "topics"
    sessions_dir = mem_dir / "sessions"

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

    topics_count = len(list(topics_dir.glob("*.md"))) if topics_dir.exists() else 0
    topics_size = (
        sum(p.stat().st_size for p in topics_dir.glob("*.md")) if topics_dir.exists() else 0
    )

    sess_files = list(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else []
    sess_total = len(sess_files)
    sess_size = sum(p.stat().st_size for p in sess_files)

    return {
        "projects": {"total": proj_total, "running": proj_running, "done": proj_done},
        "memory": {"topics": topics_count, "size_kb": round(topics_size / 1024, 1)},
        "sessions": {"total": sess_total, "size_mb": round(sess_size / 1024 / 1024, 2)},
        "config": {
            "llm_provider": settings.llm_provider,
            "model": settings.anthropic_model,
            "voice_model": settings.voice_anthropic_model,
            "vision_model": settings.vision_model,
            "tts_provider": settings.tts_provider,
            "whisper_model": settings.whisper_model,
        },
        "workspace": str(WORKSPACE_DIR.resolve()),
    }


@router.get("/api/system/perf")
async def system_perf() -> dict:
    """Métriques temps réel : CPU, RAM, disque, batterie, process Jarvis."""
    import os as _os
    import platform
    import time

    import psutil

    cpu_pct = psutil.cpu_percent(interval=0.15)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    battery = psutil.sensors_battery()
    boot_time = psutil.boot_time()
    uptime_s = int(time.time() - boot_time)

    proc_info: dict = {}
    try:
        p = psutil.Process(_os.getpid())
        with p.oneshot():
            proc_info = {
                "pid": p.pid,
                "cpu_pct": round(p.cpu_percent(interval=None), 1),
                "ram_mb": round(p.memory_info().rss / 1024 / 1024, 1),
                "threads": p.num_threads(),
            }
    except Exception:
        pass

    return {
        "cpu_pct": round(cpu_pct, 1),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_used_gb": round(mem.used / 1024**3, 2),
        "ram_total_gb": round(mem.total / 1024**3, 2),
        "ram_pct": round(mem.percent, 1),
        "disk_used_gb": round(disk.used / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "disk_pct": round(disk.percent, 1),
        "battery_pct": round(battery.percent) if battery else None,
        "battery_charging": battery.power_plugged if battery else None,
        "uptime_s": uptime_s,
        "platform": platform.platform(terse=True),
        "process": proc_info,
    }


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
async def cleanup_done_projects(request: Request) -> dict:  # noqa: ARG001

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
    import os as _os
    import signal

    _os.kill(_os.getpid(), signal.SIGTERM)
    return {"restarting": True}


# ── Conso API ─────────────────────────────────────────────────────────────────


@router.get("/api/conso/session")
async def conso_session(request: Request) -> dict:
    return request.app.state.container.tracker.get_session_summary()


@router.get("/api/conso/daily")
async def conso_daily(request: Request, days: int = 30) -> list[dict]:
    return request.app.state.container.tracker.get_daily_totals(days)


@router.get("/api/conso/providers")
async def conso_providers(request: Request) -> dict:
    summary = request.app.state.container.tracker.get_session_summary()
    return summary.get("providers", {})


@router.get("/api/conso/calls")
async def conso_calls(request: Request) -> list[dict]:
    return request.app.state.container.tracker.get_recent_calls(200)


@router.get("/api/conso/daily_providers")
async def conso_daily_providers(request: Request) -> list[dict]:
    return request.app.state.container.tracker.get_daily_by_provider(7)


@router.get("/api/conso/monthly")
async def conso_monthly(request: Request) -> dict:
    return request.app.state.container.tracker.get_monthly_totals()


@router.get("/api/conso/by_model")
async def conso_by_model(request: Request) -> list[dict]:
    return request.app.state.container.tracker.get_monthly_by_model()


@router.get("/api/conso/hourly")
async def conso_hourly(request: Request) -> list[float]:
    return request.app.state.container.tracker.get_today_hourly()
