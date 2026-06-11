"""Tests des endpoints /api/routines.

Cas couverts :
  - GET /api/routines → liste des routines (store actif / désactivé)
  - GET /api/routines/runs → historique + AuditStep (filtre, limit)
  - GET /api/routines/{name} → détail + dernier run
  - GET /api/routines/{name} 404 si routine inconnue
  - GET /api/routines/{name} 503 si store absent
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# NB : un stub historique remplaçait ici `google.genai` et autres par
# MagicMock dans sys.modules pour les envs CI sans deps installées. Retiré
# en Phase C (étape 2 (a)) car uv sync installe maintenant les deps lourdes
# en CI ; le stub polluait l'ordre des tests (cf. tests gemini dans
# test_llm_tools.py qui font `patch("google.genai.Client")`).
from jarvis.engine.background.routines import (  # noqa: E402
    CatchUpPolicy,
    ConcurrencyPolicy,
    Routine,
    RoutineStore,
    RunStatus,
    TriggerType,
)
from jarvis.interfaces.api.routines import router as routines_router  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_app(store: RoutineStore | None = None) -> FastAPI:
    """Monte le router routines sur une mini-app, avec ou sans store."""
    app = FastAPI()
    app.include_router(routines_router)
    if store is not None:
        app.state.routine_store = store
    return app


def _make_store(tmp_path: Path) -> RoutineStore:
    """Crée un RoutineStore avec une routine et un run complet."""
    store = RoutineStore(path=tmp_path / "routines.json")

    routine = Routine(
        name="daily_check",
        trigger=TriggerType.CRON,
        action_prompt="Vérifier les tâches en retard",
        cron_expr="0 9 * * *",
        concurrency_policy=ConcurrencyPolicy.SKIP_IF_ACTIVE,
        catch_up_policy=CatchUpPolicy.SKIP_MISSED,
    )
    store.register(routine)

    run = store.create_run(routine)
    run.status = RunStatus.SUCCESS
    run.finished_at = datetime.now(UTC).isoformat()
    run.result_summary = "3 tâches vérifiées"
    run.cost_usd = 0.00042
    run.add_step("started", "déclenchement cron 9h00")
    run.add_step("completed", "3 tâches vérifiées, 0 retards")
    store.update_run(run)

    return store


# ── Tests GET /api/routines ───────────────────────────────────────────────────


def test_list_routines_avec_store(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert len(data["routines"]) == 1
    assert data["routines"][0]["name"] == "daily_check"
    assert data["routines"][0]["trigger"] == "cron"


def test_list_routines_sans_store() -> None:
    app = _make_app(None)

    with TestClient(app) as c:
        res = c.get("/api/routines")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["routines"] == []


# ── Tests GET /api/routines/runs ──────────────────────────────────────────────


def test_list_runs_avec_audit_steps(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines/runs")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    runs = data["runs"]
    assert len(runs) >= 1

    run = runs[0]
    assert run["routine_name"] == "daily_check"
    assert run["status"] == "success"
    assert run["cost_usd"] == pytest.approx(0.00042)

    steps = run["audit_log"]
    assert len(steps) >= 2
    events = [s["event"] for s in steps]
    assert "started" in events
    assert "completed" in events
    assert all("ts" in s and "detail" in s for s in steps)


def test_list_runs_filtre_par_routine(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    # Ajoute une deuxième routine distincte
    r2 = Routine(
        name="hourly_ping",
        trigger=TriggerType.INTERVAL,
        action_prompt="Ping",
        interval_seconds=3600,
    )
    store.register(r2)
    run2 = store.create_run(r2)
    run2.status = RunStatus.SUCCESS
    run2.finished_at = datetime.now(UTC).isoformat()
    store.update_run(run2)

    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines/runs?routine=daily_check&limit=10")

    assert res.status_code == 200
    runs = res.json()["runs"]
    assert all(r["routine_name"] == "daily_check" for r in runs)


def test_list_runs_sans_store() -> None:
    app = _make_app(None)

    with TestClient(app) as c:
        res = c.get("/api/routines/runs")

    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["runs"] == []


# ── Tests GET /api/routines/{name} ────────────────────────────────────────────


def test_get_routine_detail(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines/daily_check")

    assert res.status_code == 200
    data = res.json()
    assert data["routine"]["name"] == "daily_check"
    assert data["routine"]["cron_expr"] == "0 9 * * *"

    last = data["last_run"]
    assert last is not None
    assert last["status"] == "success"
    assert last["result_summary"] == "3 tâches vérifiées"
    assert len(last["audit_log"]) >= 2


def test_get_routine_404_si_inconnue(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines/inexistante")

    assert res.status_code == 404
    assert "introuvable" in res.json()["detail"]


def test_get_routine_503_si_store_absent() -> None:
    app = _make_app(None)

    with TestClient(app) as c:
        res = c.get("/api/routines/daily_check")

    assert res.status_code == 503
    assert "désactivées" in res.json()["detail"]


def test_get_routine_last_run_none_si_aucun_run(tmp_path: Path) -> None:
    """Une routine sans aucun run SUCCESS/FAILED retourne last_run: null."""
    store = RoutineStore(path=tmp_path / "routines2.json")
    routine = Routine(
        name="vide",
        trigger=TriggerType.INTERVAL,
        action_prompt="Test",
        interval_seconds=60,
    )
    store.register(routine)
    app = _make_app(store)

    with TestClient(app) as c:
        res = c.get("/api/routines/vide")

    assert res.status_code == 200
    assert res.json()["last_run"] is None
