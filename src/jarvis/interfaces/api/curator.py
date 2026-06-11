"""Endpoints Curator + Command Center (CDC §10).

GET  /api/curator/latest          — dernier rapport JSON
POST /api/curator/scan            — déclenche un scan à la demande (équivalent
                                    de /api/memory/trigger-deep — outil
                                    d'observation pour itérer sans attendre 3h10).
POST /api/curator/patches/{idx}/apply — refuse en MVP, renvoie un message clair
                                          expliquant que l'application est manuelle
                                          via les endpoints des phases respectives.

GET  /api/command-center/snapshot — vue agrégée initiatives + missions + budget
                                    + skills + heartbeat (lecture seule).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from jarvis.engine.proactive.curator import _report_to_dict

router = APIRouter()


def _curator(request: Request):  # noqa: ANN202
    cur = getattr(request.app.state, "curator", None)
    if cur is None:
        raise HTTPException(503, "Curator non disponible — main.py n'a pas câblé.")
    return cur


def _command_center(request: Request):  # noqa: ANN202
    cc = getattr(request.app.state, "command_center", None)
    if cc is None:
        raise HTTPException(503, "Command Center non disponible.")
    return cc


# ── Curator ──────────────────────────────────────────────────────────────────


@router.get("/api/curator/latest")
async def curator_latest_report(request: Request) -> dict:
    """Renvoie le dernier rapport Curator (sérialisé JSON). 404 si jamais lancé."""

    cur = _curator(request)
    report = cur.latest_report()
    if report is None:
        raise HTTPException(404, "Aucun rapport Curator disponible.")
    return _report_to_dict(report)


@router.post("/api/curator/scan")
async def curator_scan(request: Request) -> dict:
    """Déclenche un scan Curator immédiat (outil d'observation).

    Lecture seule : le scan ne modifie RIEN, il produit un rapport. Pas de
    flag à activer — le Curator n'a pas de mode auto-apply en MVP, son
    pire effet est de générer un rapport.
    """

    cur = _curator(request)
    report = await cur.scan()
    return {
        "ok": True,
        "patches_proposed": len(report.patches),
        "refused_protected": len(report.refused_protected_patches),
        "duration_s": report.duration_seconds,
        "report": _report_to_dict(report),
    }


@router.post("/api/curator/patches/{patch_index}/apply")
async def curator_apply_patch(patch_index: int, request: Request) -> dict:
    """PHASE 6 MVP : RENVOIE TOUJOURS 403. Le Curator ne s'auto-applique pas.

    Pour appliquer un patch, utiliser les endpoints des phases respectives :
    - facts → POST /api/memory/correct (memory_correction event)
    - skills SANDBOXED_PASS → POST /api/skills/lab/{name}/promote
    - skills à archiver → endpoint humain (non câblé MVP, à scripter manuellement)

    L'endpoint existe pour matérialiser la règle : aucune route auto.
    """

    cur = _curator(request)
    report = cur.latest_report()
    if report is None:
        raise HTTPException(404, "Aucun rapport disponible.")
    applied, reason = cur.apply_patch(patch_index, report)
    if applied:
        # En MVP, apply_patch retourne TOUJOURS False — ce code path est mort
        # pour l'instant mais reste défensif pour PHASE 6.x.
        return {"applied": True, "reason": reason}
    # Refus systématique en MVP — code HTTP 403 (forbidden) plutôt que 409
    # pour signifier "interdit par politique", pas "conflit d'état".
    raise HTTPException(
        403,
        f"Application refusée par politique PHASE 6 MVP. {reason} "
        "Pour appliquer effectivement, utiliser les endpoints des phases "
        "respectives (memory/skills/lab/etc.). "
        f"Patches actuels dans le rapport : {len(report.patches)}",
    )


# ── Command Center ───────────────────────────────────────────────────────────


@router.get("/api/command-center/snapshot")
async def command_center_snapshot(request: Request, days: int = 7) -> dict:
    """Vue agrégée initiatives + missions + budget + skills + heartbeat."""
    cc = _command_center(request)
    snap = cc.snapshot(days=days)
    return asdict(snap)
