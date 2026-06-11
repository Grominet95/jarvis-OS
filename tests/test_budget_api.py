"""Tests des endpoints /api/budget.

Cas couverts :
  - GET /api/budget/status quand le guard est actif (guard.status() proxié)
  - GET /api/budget/status quand le guard est None (budget désactivé)
  - GET /api/budget/remaining avec scope connu (valeur bornée)
  - GET /api/budget/remaining scope illimité (remaining_usd: null)
  - GET /api/budget/remaining quand désactivé
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.interfaces.api.budget import router as budget_router

# ── Helpers ───────────────────────────────────────────────────────────────────


def _app_with_guard(guard: object | None) -> FastAPI:
    """Monte le router budget sur une mini-app et installe un Container minimal.

    Phase C — étape 2 (b+c+e) : les endpoints budget lisent `request.app.state
    .container.budget` désormais ; on injecte un Container stub (SimpleNamespace)
    plutôt que de patcher l'ancien singleton `get_budget_guard`.
    """
    app = FastAPI()
    app.include_router(budget_router)
    app.state.container = SimpleNamespace(budget=guard)
    return app


_STATUS_PAYLOAD = {
    "enabled": True,
    "global": {
        "spent_usd": 2.5,
        "limit_usd": 10.0,
        "remaining_usd": 7.5,
        "utilization_pct": 25.0,
        "status": "ok",
    },
    "projects": {
        "proj1": {
            "spent_usd": 0.5,
            "limit_usd": 2.0,
            "remaining_usd": 1.5,
            "status": "ok",
        }
    },
}


# ── Tests /api/budget/status ──────────────────────────────────────────────────


def test_status_quand_guard_actif() -> None:
    guard = MagicMock()
    guard.status.return_value = _STATUS_PAYLOAD
    app = _app_with_guard(guard)

    with TestClient(app) as c:
        res = c.get("/api/budget/status")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["global"]["spent_usd"] == 2.5
    assert "proj1" in data["projects"]
    guard.status.assert_called_once()


def test_status_quand_guard_absent() -> None:
    """Quand container.budget est None, l'endpoint retourne enabled=false."""
    app = _app_with_guard(None)

    with TestClient(app) as c:
        res = c.get("/api/budget/status")

    assert res.status_code == 200
    assert res.json() == {"enabled": False}


# ── Tests /api/budget/remaining ───────────────────────────────────────────────


def test_remaining_scope_global() -> None:
    guard = MagicMock()
    guard.remaining.return_value = 7.5
    app = _app_with_guard(guard)

    with TestClient(app) as c:
        res = c.get("/api/budget/remaining?scope=global")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["scope"] == "global"
    assert data["remaining_usd"] == pytest.approx(7.5)
    guard.remaining.assert_called_once_with("global")


def test_remaining_scope_illimite() -> None:
    """Un scope run: retourne remaining_usd: null (infini non sérialisable)."""
    guard = MagicMock()
    guard.remaining.return_value = float("inf")
    app = _app_with_guard(guard)

    with TestClient(app) as c:
        res = c.get("/api/budget/remaining?scope=run%3Asome-run")

    assert res.status_code == 200
    data = res.json()
    assert data["remaining_usd"] is None


def test_remaining_quand_desactive() -> None:
    app = _app_with_guard(None)

    with TestClient(app) as c:
        res = c.get("/api/budget/remaining?scope=global")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["remaining_usd"] is None
    assert data["scope"] == "global"


def test_remaining_scope_par_defaut_est_global() -> None:
    guard = MagicMock()
    guard.remaining.return_value = 5.0
    app = _app_with_guard(guard)

    with TestClient(app) as c:
        res = c.get("/api/budget/remaining")

    assert res.status_code == 200
    guard.remaining.assert_called_once_with("global")
