from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()


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
    """Liste des skills installés, enrichie avec env_status, apps_status et capabilities."""
    from dotenv import dotenv_values

    from skills.app_checker import check_all_apps
    from skills.registry import skill_registry

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
    from background.notifications import broadcast_event
    from skills.installer import skill_installer
    from skills.registry import skill_registry

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
    from background.notifications import broadcast_event
    from skills.installer import skill_installer
    from skills.registry import skill_registry

    result = skill_installer.uninstall(skill_name)
    if result.get("success"):
        tool_registry = getattr(request.app.state, "tool_registry", None)
        if tool_registry:
            tool_registry.replace_skill_tools(*skill_registry.get_all_tools())
        broadcast_event({"type": "reload_views"})
    return result


@router.get("/api/skills/view-scripts")
async def get_view_scripts() -> dict:
    """Retourne les chemins JS/CSS des skills de type vue installés, avec hash de contenu."""
    import hashlib

    base = Path("ui/static/skills")
    scripts, styles = [], []
    if base.exists():
        for skill_static in sorted(base.iterdir()):
            if not skill_static.is_dir():
                continue
            name = skill_static.name
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
    from skills.registry import skill_registry

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
    from skills.registry import skill_registry

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
    from audio.tts import tts_engine
    from background.notifications import broadcast_event
    from core.gateway import get_tool_registry
    from skills.executor import PresetExecutor
    from skills.registry import skill_registry

    preset = skill_registry.get_preset(preset_name)
    if not preset:
        return {"success": False, "message": f"Preset '{preset_name}' introuvable"}

    executor = PresetExecutor(
        tool_registry=get_tool_registry(),
        tts_engine=tts_engine,
    )
    results = await executor.execute(preset, broadcast_fn=broadcast_event)
    return results
