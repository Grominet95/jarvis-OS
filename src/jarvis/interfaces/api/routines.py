"""Endpoints read-only pour le journal des routines planifiées (RoutineStore).

Expose trois routes GET sous /api/routines :
  - /api/routines           → liste des routines enregistrées
  - /api/routines/runs      → historique des runs avec AuditStep
  - /api/routines/{name}    → détail d'une routine + son dernier run terminé

Le RoutineStore est lu depuis ``request.app.state.routine_store`` (injecté par
main.py au démarrage si ROUTINES_ENABLED=true). Si absent, les endpoints
retournent ``{"enabled": false}`` ou 503 selon le cas.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _get_store(request: Request) -> object:
    """Retourne le RoutineStore depuis l'état applicatif, ou None si désactivé."""
    return getattr(request.app.state, "routine_store", None)


@router.get("/api/routines")
async def list_routines(request: Request) -> dict:
    """Liste des routines enregistrées dans le RoutineStore."""
    store = _get_store(request)
    if store is None:
        return {"enabled": False, "routines": []}
    return {
        "enabled": True,
        "routines": [asdict(r) for r in store.list_routines()],
    }


@router.get("/api/routines/runs")
async def list_runs(
    request: Request,
    routine: str | None = None,
    limit: int = 50,
) -> dict:
    """Historique des runs tracés, avec leurs AuditStep.

    Paramètres :
      - ``routine`` : filtre par nom de routine (optionnel)
      - ``limit``   : nombre maximum de runs retournés (défaut 50)
    """
    store = _get_store(request)
    if store is None:
        return {"enabled": False, "runs": []}
    runs = store.list_runs(routine_name=routine, limit=limit)
    return {
        "enabled": True,
        "runs": [asdict(r) for r in runs],
    }


@router.get("/api/routines/{name}")
async def get_routine(name: str, request: Request) -> dict:
    """Détail d'une routine et son dernier run terminé (SUCCESS ou FAILED)."""
    store = _get_store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="Routines désactivées")
    routine = store.get_routine(name)
    if routine is None:
        raise HTTPException(status_code=404, detail=f"Routine '{name}' introuvable")
    last_run = store.last_finished_run(name)
    return {
        "routine": asdict(routine),
        "last_run": asdict(last_run) if last_run else None,
    }
