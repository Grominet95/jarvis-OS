"""Permissions runtime + Approvals API — Phase E §E.1.3."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jarvis.kernel.approvals import ApprovalMode, approval_config, save_approval_config
from jarvis.kernel.permissions import permissions as _perm_store

router = APIRouter()


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


# ── Approvals API ─────────────────────────────────────────────────────────────


@router.get("/api/approvals/config")
async def get_approvals_config() -> dict:
    """Retourne la configuration courante des approbations."""
    return asdict(approval_config)


class ApprovalCategoryUpdate(BaseModel):
    mode: str  # "always" | "ask" | "never"


@router.patch("/api/approvals/config/{category}")
async def update_approval_category(category: str, body: ApprovalCategoryUpdate) -> dict:
    """Met à jour le mode d'une catégorie d'approbation."""
    if not hasattr(approval_config, category):
        raise HTTPException(404, f"Catégorie inconnue: {category}")
    try:
        mode = ApprovalMode(body.mode)
    except ValueError:
        msg = f"Mode invalide: {body.mode}. Valeurs: always, ask, never"
        raise HTTPException(400, msg) from None
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
