from __future__ import annotations

from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException, Request

from jarvis.capabilities.skills.app_checker import check_all_apps
from jarvis.capabilities.skills.executor import PresetExecutor
from jarvis.capabilities.skills.installer import skill_installer
from jarvis.capabilities.skills.lifecycle import SkillStatus
from jarvis.capabilities.skills.registry import skill_registry
from jarvis.engine.background.notifications import broadcast_event
from jarvis.kernel.paths import SKILLS_INSTALLED_DIR, UI_STATIC_DIR
from jarvis.providers.audio.tts import tts_engine

router = APIRouter()


# ── Skill Lab API (PHASE 4) ──────────────────────────────────────────────────


def _lab(request: Request):  # noqa: ANN202 — type circulaire
    lab = getattr(request.app.state, "skill_lab", None)
    if lab is None:
        raise HTTPException(503, "SkillLab non disponible — main.py n'a pas câblé.")
    return lab


def _lifecycle(request: Request):  # noqa: ANN202
    lc = getattr(request.app.state, "skill_lifecycle", None)
    if lc is None:
        raise HTTPException(503, "SkillLifecycle non disponible.")
    return lc


def _record_to_dict(record) -> dict:  # noqa: ANN001
    return {
        "name": record.name,
        "status": record.status.value,
        "confidence": record.confidence,
        "support_count": record.support_count,
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
        "source_event_id": record.source_event_id,
        "sandbox_notes": record.sandbox_notes,
        "created_at": record.created_at.isoformat(),
        "promoted_at": record.promoted_at.isoformat() if record.promoted_at else None,
        "archived_at": record.archived_at.isoformat() if record.archived_at else None,
        "updated_at": record.updated_at.isoformat(),
    }


@router.get("/api/skills/lab/candidates")
async def list_lab_candidates(
    request: Request,
    status: str | None = None,
) -> list[dict]:
    """Liste les SkillRecord du lifecycle, filtrable par status.

    status ∈ {candidate, sandboxed_pass, sandboxed_fail, active, stale,
    archived, rejected}.
    """

    lc = _lifecycle(request)
    if status is None:
        records = lc.list_all()
    else:
        try:
            s = SkillStatus(status)
        except ValueError:
            raise HTTPException(400, f"Status invalide : {status}") from None
        records = lc.list_by_status(s)
    return [_record_to_dict(r) for r in records]


@router.post("/api/skills/lab/{name}/promote")
async def promote_lab_skill(name: str, request: Request) -> dict:
    """Validation humaine : installe la skill candidate.

    Refuse 409 si la skill n'est pas en SANDBOXED_PASS.
    """
    lab = _lab(request)
    record = lab.promote(name)
    if record is None:
        raise HTTPException(
            409,
            f"Promotion refusée pour '{name}' : skill inconnue, non en "
            "SANDBOXED_PASS, ou collision avec une skill installée.",
        )
    return {"ok": True, "record": _record_to_dict(record)}


@router.post("/api/skills/lab/{name}/reject")
async def reject_lab_skill(
    name: str,
    request: Request,
    reason: str = "",
    delete_files: bool = False,
) -> dict:
    """Validation humaine refusée. delete_files=true supprime aussi le dossier."""
    lab = _lab(request)
    record = lab.reject(name, reason=reason, delete_files=delete_files)
    if record is None:
        raise HTTPException(404, f"Skill '{name}' inconnue.")
    return {"ok": True, "record": _record_to_dict(record)}


@router.post("/api/skills/lab/scan")
async def trigger_lab_scan(request: Request) -> dict:
    """Déclenche un scan polling du Kernel à la demande (outil d'observation).

    Équivalent du /api/memory/trigger-deep du MOUVEMENT 2 PHASE 3 : permet
    d'itérer rapidement sur la pipeline sans attendre le passage nocturne.
    """
    lab = _lab(request)
    result = await lab.scan_kernel()
    return {
        "events_examined": result.events_examined,
        "candidates_generated": result.candidates_generated,
        "sandbox_passed": result.sandbox_passed,
        "sandbox_failed": result.sandbox_failed,
        "skipped_already_handled": result.skipped_already_handled,
        "errors": result.errors,
    }


# ── Skills API ────────────────────────────────────────────────────────────────


@router.get("/api/skills/catalog")
async def get_skills_catalog() -> dict:
    """Catalogue des skills disponibles (GitHub + état installé)."""

    skills = await skill_installer.fetch_catalog()
    offline = any(s.get("offline") for s in skills)
    return {"skills": skills, "offline": offline}


@router.get("/api/skills/installed")
async def get_installed_skills() -> dict:
    """Liste des skills installés, enrichie avec env_status, apps_status et capabilities."""


    env_values = dotenv_values(".env")
    enriched = []
    for s in skill_registry.list_installed():
        skill_obj = skill_registry.get(s["name"])
        metadata = skill_obj.metadata if skill_obj else {}
        requires_env = metadata.get("requires_env", s.get("requires_env", []))
        requires_apps = metadata.get("requires_apps", [])
        capabilities = metadata.get("capabilities", [])

        if requires_env and isinstance(requires_env[0], dict):
            env_status = {
                e["name"]: bool(env_values.get(e["name"], "").strip()) for e in requires_env
            }
            env_vals = {e["name"]: env_values.get(e["name"], "") for e in requires_env}
        else:
            env_status = {k: bool(env_values.get(k, "").strip()) for k in requires_env}
            env_vals = {k: env_values.get(k, "") for k in requires_env}

        apps_status = check_all_apps(requires_apps)

        configured = (all(env_status.values()) if env_status else True) and apps_status[
            "all_required_installed"
        ]

        enriched.append(
            {
                **s,
                "capabilities": capabilities,
                "requires_env_detail": requires_env,
                "env_status": env_status,
                "env_values": env_vals,
                "requires_apps_status": apps_status["apps"],
                "all_apps_ok": apps_status["all_required_installed"],
                "configured": configured,
            }
        )
    return {"skills": enriched}


@router.post("/api/skills/install/{skill_name}")
async def install_skill(skill_name: str, request: Request) -> dict:
    """Installe un skill depuis le repo jarvis-skills."""

    result = await skill_installer.install(skill_name)
    if result.get("success"):
        tool_registry = getattr(request.app.state, "tool_registry", None)
        if tool_registry:
            tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
        broadcast_event({"type": "reload_views"})
    return result


@router.delete("/api/skills/uninstall/{skill_name}")
async def uninstall_skill(skill_name: str, request: Request) -> dict:
    """Désinstalle un skill."""

    result = skill_installer.uninstall(skill_name)
    if result.get("success"):
        tool_registry = getattr(request.app.state, "tool_registry", None)
        if tool_registry:
            tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
        broadcast_event({"type": "reload_views"})
    return result


@router.get("/api/skills/view-scripts")
async def get_view_scripts() -> dict:
    """Retourne les JS/CSS des skills installés dont type=view (hash MD5 pour cache-busting)."""
    import hashlib

    import yaml


    base = UI_STATIC_DIR / "skills"
    installed = SKILLS_INSTALLED_DIR
    scripts, styles = [], []
    if not base.exists():
        return {"scripts": scripts, "styles": styles}

    for skill_static in sorted(base.iterdir()):
        if not skill_static.is_dir():
            continue
        name = skill_static.name
        yaml_path = installed / name / "skill.yaml"
        if not yaml_path.exists():
            continue
        try:
            meta = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            continue
        if meta.get("type") != "view":
            continue
        for f in sorted(skill_static.iterdir()):
            v = hashlib.md5(f.read_bytes()).hexdigest()[:8]
            if f.suffix == ".js":
                scripts.append(f"/skills/{name}/{f.name}?v={v}")
            elif f.suffix == ".css":
                styles.append(f"/skills/{name}/{f.name}?v={v}")
    return {"scripts": scripts, "styles": styles}


@router.post("/api/skills/reload")
async def reload_skills(request: Request) -> dict:
    """Recharge les skills et leurs outils sans redémarrer Jarvis."""

    skill_registry.reload()
    tool_registry = getattr(request.app.state, "tool_registry", None)
    if tool_registry:
        tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
    return {
        "success": True,
        "loaded": len(skill_registry.get_all()),
    }


# ── Presets API ───────────────────────────────────────────────────────────────


@router.get("/api/presets")
async def get_presets() -> dict:
    """Liste tous les presets installés."""

    presets = skill_registry.get_presets()
    return {
        "presets": [
            {
                "name": r.name,
                "label": r.label,
                "description": r.description,
                "triggers": r.get_triggers(),
                "platforms": r.get_platforms(),
                "steps_count": len(r.get_steps()),
            }
            for r in presets.values()
        ]
    }


@router.post("/api/presets/{preset_name}/execute")
async def execute_preset_endpoint(preset_name: str, request: Request) -> dict:
    """Lance un preset depuis l'UI (bouton ▶)."""

    preset = skill_registry.get_preset(preset_name)
    if not preset:
        return {"success": False, "message": f"Preset '{preset_name}' introuvable"}

    container = request.app.state.container
    executor = PresetExecutor(
        tool_registry=container.tool_registry,
        tts_engine=tts_engine,
    )
    results = await executor.execute(preset, broadcast_fn=broadcast_event)
    return results
