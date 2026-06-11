"""Endpoints read-only pour le suivi de budget / coûts (BudgetGuard).

Expose deux routes GET sous /api/budget :
  - /status  → snapshot complet (guard.status() ou désactivé)
  - /remaining?scope= → budget restant pour un scope
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/budget/status")
async def budget_status(request: Request) -> dict:
    """Résumé de l'état budgétaire courant.

    Retourne {"enabled": false} si le BudgetGuard n'est pas initialisé.
    """
    container = getattr(request.app.state, "container", None)
    guard = getattr(container, "budget", None) if container is not None else None
    if guard is None:
        return {"enabled": False}
    return guard.status()


@router.get("/api/budget/remaining")
async def budget_remaining(request: Request, scope: str = "global") -> dict:
    """Budget restant pour un scope donné.

    Scopes valides : ``"global"``, ``"project:<id>"``, ``"run:<id>"``.
    Retourne ``remaining_usd: null`` si le scope est illimité ou le guard absent.
    """
    container = getattr(request.app.state, "container", None)
    guard = getattr(container, "budget", None) if container is not None else None
    if guard is None:
        return {"enabled": False, "scope": scope, "remaining_usd": None}
    remaining = guard.remaining(scope)
    return {
        "enabled": True,
        "scope": scope,
        "remaining_usd": None if remaining == float("inf") else round(remaining, 6),
    }
