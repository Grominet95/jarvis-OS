from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger as _log
from pydantic import BaseModel

from jarvis.capabilities.tools.gmail import send_gmail_draft
from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
from jarvis.engine.proactive.schemas import InitiativeType
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.kernel.settings import settings as _s

router = APIRouter()


class RectifyBody(BaseModel):
    correction: str


class ConfirmBody(BaseModel):
    draft_content: str | None = None


# ── Initiatives API ───────────────────────────────────────────────────────────


@router.get("/api/initiatives")
async def get_initiatives() -> list[dict]:
    """Initiatives en attente (mode VALIDATE).

    Réponse étendue PHASE 6 avec les 7 champs §10.1 (autonomy_level,
    permission_required, cost_max_usd, risk, deadline, next_action,
    requires_validation) — consommée par dashboard.js pour afficher le
    badge "NIVEAU 5 — VALIDATION FORCÉE" et le bloc gouvernance.
    Ajout rétro-compatible : aucun champ historique retiré.
    """

    store = InitiativeStore()
    initiatives = store.load_pending_all(days=7)
    return [
        {
            "id": i.id,
            "type": i.type,
            "title": i.title,
            "context": i.context,
            "reasoning": i.reasoning,
            "action": i.action,
            "priority": i.priority,
            "execution_mode": i.execution_mode,
            "draft_content": i.draft_content,
            "created_at": i.created_at.isoformat(),
            # ── PHASE 6 §10.1 — champs gouvernance ──
            "autonomy_level": int(i.autonomy_level),
            "permission_required": i.permission_required,
            "cost_max_usd": i.cost_max_usd,
            "risk": i.risk,
            "deadline": i.deadline.isoformat() if i.deadline else None,
            "next_action": i.next_action,
            "requires_validation": i.requires_validation,
        }
        for i in initiatives
    ]


@router.post("/api/initiatives/{initiative_id}/approve")
async def approve_initiative(initiative_id: str, request: Request) -> dict:
    import asyncio

    store = InitiativeStore()
    init = store.get_by_id(initiative_id)
    if not init:
        raise HTTPException(404, "Initiative introuvable")

    result: dict = {"status": "approved", "type": str(init.type)}

    try:
        if init.type == InitiativeType.DRAFT_RESPONSE:
            msg_id = await send_gmail_draft(
                draft_content=init.draft_content or "",
                credentials_path=Path(_s.google_credentials_path),
                token_path=Path(_s.google_token_path).parent / "google_gmail_token.json",
            )
            result["message_id"] = msg_id
            _to = init.draft_content[:40] if init.draft_content else ""
            _log.info(f"Initiative {initiative_id}: email envoyé", to=_to)

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

    InitiativeStore().update_status(initiative_id, "rejected")
    return {"status": "rejected"}


@router.post("/api/initiatives/{initiative_id}/rectify")
async def rectify_initiative(initiative_id: str, body: RectifyBody, request: Request) -> dict:

    store = InitiativeStore()
    init = store.get_by_id(initiative_id)
    if not init:
        raise HTTPException(404, "Initiative introuvable")

    generator = InitiativeGenerator(llm=request.app.state.container.background_llm)
    new_init = await generator.rectify(init, body.correction)
    if not new_init:
        raise HTTPException(500, "Régénération échouée")

    store.update_initiative(
        initiative_id,
        {
            "title": new_init.title,
            "context": new_init.context,
            "reasoning": new_init.reasoning,
            "action": new_init.action,
            "priority": new_init.priority,
            "execution_mode": new_init.execution_mode,
            "draft_content": new_init.draft_content,
            "mission_description": new_init.mission_description,
        },
    )

    return {
        "id": initiative_id,
        "type": new_init.type,
        "title": new_init.title,
        "context": new_init.context,
        "reasoning": new_init.reasoning,
        "action": new_init.action,
        "priority": new_init.priority,
        "execution_mode": new_init.execution_mode,
        "draft_content": new_init.draft_content,
        "mission_description": new_init.mission_description,
        "created_at": init.created_at.isoformat(),
    }


# ── Proactive initiatives v2 (executor) ──────────────────────────────────────


@router.get("/api/proactive/initiatives")
async def list_proactive_initiatives(
    days: int = Query(default=7, ge=1, le=30),
    status: str | None = Query(default=None),
) -> list[dict]:
    """Liste les initiatives récentes (multi-jours).

    status=pending|done|dismissed|… ou absent=tous.
    """

    store = InitiativeStore()
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    items = store.list_recent(days=days, statuses=statuses)
    return [
        {
            "id": i.id,
            "type": i.type,
            "title": i.title,
            "context": i.context,
            "reasoning": i.reasoning,
            "action": i.action,
            "priority": i.priority,
            "execution_mode": i.execution_mode,
            "draft_content": i.draft_content,
            "mission_description": i.mission_description,
            "status": i.status,
            "created_at": i.created_at.isoformat(),
        }
        for i in items
    ]


@router.post("/api/proactive/initiatives/{initiative_id}/run")
async def run_initiative(initiative_id: str, request: Request) -> dict:
    """Déclenche l'exécution pilotée d'une initiative (étape 1/2 pour les actions sensibles)."""
    executor = getattr(request.app.state, "initiative_executor", None)
    if not executor:
        raise HTTPException(503, "InitiativeExecutor non disponible")
    return await executor.run(initiative_id)


@router.post("/api/proactive/initiatives/{initiative_id}/confirm")
async def confirm_initiative(initiative_id: str, body: ConfirmBody, request: Request) -> dict:
    """2e confirmation pour les actions sensibles (envoi mail après brouillon prêt)."""
    executor = getattr(request.app.state, "initiative_executor", None)
    if not executor:
        raise HTTPException(503, "InitiativeExecutor non disponible")
    return await executor.confirm(initiative_id, body.draft_content)


@router.post("/api/proactive/initiatives/{initiative_id}/dismiss")
async def dismiss_initiative(initiative_id: str) -> dict:
    """Marque l'initiative comme ignorée (dismissed)."""

    store = InitiativeStore()
    init = store.get_by_id(initiative_id)
    if not init:
        raise HTTPException(404, "Initiative introuvable")
    store.update_status(initiative_id, "dismissed")
    return {"status": "dismissed"}


# ── Proactive engine API ──────────────────────────────────────────────────────


@router.post("/api/proactive/run")
async def run_proactive_now(request: Request) -> dict:
    """Force un cycle proactif immédiat."""
    import asyncio

    engine = getattr(request.app.state, "proactive_engine", None)
    if not engine:
        raise HTTPException(503, "ProactiveEngine non disponible")
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
        "running": engine._running,
        "interval_s": engine._interval,
        "last_run": last_run,
    }
