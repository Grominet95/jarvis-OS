from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


# ── Analytics API (legacy) ────────────────────────────────────────────────────


@router.get("/api/analytics/jarvis")
async def analytics_jarvis(days: int = 30) -> dict:
    from jarvis.interfaces.api.analytics import get_jarvis_stats

    return await get_jarvis_stats(days)


@router.get("/api/analytics/youtube")
async def analytics_youtube(days: int = 7) -> dict:
    from jarvis.interfaces.api.analytics import get_youtube_stats

    return await get_youtube_stats(days)


@router.get("/api/analytics/summary")
async def analytics_summary() -> dict:
    from jarvis.interfaces.api.analytics import get_analytics_summary

    return await get_analytics_summary()


# ── Analytics Widget System ───────────────────────────────────────────────────


@router.get("/api/analytics/catalog")
async def get_analytics_catalog() -> dict:
    """Catalogue de tous les widgets disponibles."""
    from jarvis.analytics.registry import analytics_registry

    return {"widgets": analytics_registry.get_catalog()}


@router.get("/api/analytics/data")
async def get_analytics_data() -> dict:
    """Fetch les données de tous les widgets actifs."""
    from jarvis.analytics.registry import analytics_registry

    data = await analytics_registry.fetch_all()
    return {
        "widgets": {
            wid: {
                "success": wd.success,
                "data": wd.data,
                "error": wd.error,
                "cached": wd.cached,
            }
            for wid, wd in data.items()
        }
    }


@router.get("/api/analytics/active")
async def get_active_widgets() -> dict:
    """Liste des widgets actifs avec leurs manifests."""
    from jarvis.analytics.registry import analytics_registry

    return {"widgets": [w.to_manifest() for w in analytics_registry.get_active()]}


@router.post("/api/analytics/add/{widget_id}")
async def add_widget(widget_id: str, request: Request) -> dict:
    """Active un widget."""
    from jarvis.analytics.registry import analytics_registry

    try:
        body = await request.json()
    except Exception:
        body = {}
    return analytics_registry.add(widget_id, settings=body)


@router.delete("/api/analytics/remove/{widget_id}")
async def remove_widget(widget_id: str) -> dict:
    """Désactive un widget."""
    from jarvis.analytics.registry import analytics_registry

    return analytics_registry.remove(widget_id)


@router.post("/api/analytics/refresh")
async def refresh_analytics() -> dict:
    """Force le refresh des données analytics."""
    from jarvis.analytics.registry import analytics_registry

    data = await analytics_registry.fetch_all()
    return {"refreshed": len(data)}


@router.post("/api/analytics/reorder")
async def reorder_widgets(request: Request) -> dict:
    """Sauvegarde le nouvel ordre des widgets."""
    from jarvis.analytics.registry import analytics_registry

    body = await request.json()
    return analytics_registry.reorder(body.get("order", []))
