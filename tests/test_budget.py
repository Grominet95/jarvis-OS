# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests du système de budget / contrôle de coût.

Couvre :
  - reserve/record : comportement de base
  - hard-stop : déclenche pause + notification
  - warn : déclenche notification warn (une seule fois)
  - claim atomique : empêche la double-exécution
  - reprise d'un projet en pause budgétaire
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_settings(
    enabled: bool = True,
    monthly_usd: float = 10.0,
    per_project: float = 2.0,
    warn_pct: float = 80.0,
) -> MagicMock:
    s = MagicMock()
    s.budget_enabled = enabled
    s.budget_monthly_usd = monthly_usd
    s.budget_per_project_usd = per_project
    s.budget_warn_pct = warn_pct
    return s


def _make_fake_tracker() -> MagicMock:
    """Fake UsageTracker — historique JSONL vide, pas de lecture disque."""
    tracker = MagicMock()
    tracker._read_day = MagicMock(return_value=[])
    tracker.get_monthly_totals = MagicMock(return_value={"cost_usd": 0.0})
    return tracker


def make_guard(
    monthly_usd: float = 10.0,
    per_project: float = 2.0,
    warn_pct: float = 80.0,
    enabled: bool = True,
    notify: list[dict] | None = None,
) -> tuple[object, list[dict]]:
    """Fabrique un BudgetGuard isolé.

    Phase D : la notif passe par le bus d'événements
    `BudgetThresholdReached`. Le helper capture les événements publiés
    dans la liste `notifications` — la forme est convertie en dict pour
    rester compatible avec les assertions existantes (`type`, `scope`, …).
    """
    notifications: list[dict] = [] if notify is None else notify
    settings_mock = _make_settings(enabled, monthly_usd, per_project, warn_pct)

    from jarvis.engine.budget import BudgetGuard
    from jarvis.kernel.events import BudgetThresholdReached, EventBus

    bus = EventBus()

    async def _capture(event: BudgetThresholdReached) -> None:
        notifications.append(
            {
                "type": "budget_hard_stop" if event.ratio >= 1.0 else "budget_warning",
                "scope": event.scope,
                "ratio": event.ratio,
                "provider": event.provider,
            }
        )

    bus.subscribe(BudgetThresholdReached, _capture)

    guard = BudgetGuard(
        settings=settings_mock,
        tracker=_make_fake_tracker(),
        bus=bus,
    )

    return guard, notifications


# ── Tests reserve / record ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reserve_ok_quand_sous_budget() -> None:
    guard, _ = make_guard(monthly_usd=10.0)
    guard._global_spent = lambda: 0.0

    ok = await guard.reserve("global", 1.0)
    assert ok is True


@pytest.mark.asyncio
async def test_reserve_ok_projet_sous_budget() -> None:
    guard, _ = make_guard(per_project=2.0)
    guard._project_spent["proj1"] = 0.5

    ok = await guard.reserve("project:proj1", 1.0)
    assert ok is True


@pytest.mark.asyncio
async def test_reserve_hard_stop_global() -> None:
    notifications: list[dict] = []
    guard, _ = make_guard(monthly_usd=5.0, notify=notifications)
    guard._global_spent = lambda: 4.9  # quasi-plein

    ok = await guard.reserve("global", 0.2)  # 4.9 + 0.2 > 5.0 → stop
    assert ok is False
    assert any(n["type"] == "budget_hard_stop" for n in notifications)


@pytest.mark.asyncio
async def test_reserve_hard_stop_projet() -> None:
    notifications: list[dict] = []
    guard, _ = make_guard(per_project=1.0, notify=notifications)
    guard._project_spent["projX"] = 0.95

    ok = await guard.reserve("project:projX", 0.1)  # 0.95 + 0.1 > 1.0 → stop
    assert ok is False
    assert any(
        n["type"] == "budget_hard_stop" and n["scope"] == "project:projX" for n in notifications
    )


@pytest.mark.asyncio
async def test_reserve_disabled_toujours_ok() -> None:
    guard, _ = make_guard(enabled=False)
    guard._global_spent = lambda: 9999.0

    ok = await guard.reserve("global", 9999.0)
    assert ok is True


def test_record_accumule_projet() -> None:
    guard, _ = make_guard()
    guard.record("project:p1", 0.30)
    guard.record("project:p1", 0.15)
    assert abs(guard._project_spent.get("p1", 0) - 0.45) < 1e-9


def test_record_accumule_run() -> None:
    guard, _ = make_guard()
    guard.record("run:r1", 0.05)
    guard.record("run:r1", 0.03)
    assert abs(guard._run_spent.get("r1", 0) - 0.08) < 1e-9


def test_record_ignore_global() -> None:
    """record('global', …) ne doit pas lever et ne stocke rien in-memory."""
    guard, _ = make_guard()
    guard.record("global", 1.0)
    assert "global" not in guard._project_spent


def test_remaining_projet() -> None:
    guard, _ = make_guard(per_project=2.0)
    guard._project_spent["p2"] = 1.20
    assert abs(guard.remaining("project:p2") - 0.80) < 1e-6


def test_remaining_illimite_pour_run() -> None:
    guard, _ = make_guard()
    assert guard.remaining("run:anyrun") == float("inf")


# ── Tests warn threshold ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warn_declenche_notification_une_fois() -> None:
    notifications: list[dict] = []
    guard, _ = make_guard(per_project=1.0, warn_pct=80.0, notify=notifications)
    guard._project_spent["pw"] = 0.78

    # Première réservation : projette à 0.83 → 83 % > 80 % → warn
    ok1 = await guard.reserve("project:pw", 0.05)
    assert ok1 is True
    warn_notifs = [n for n in notifications if n["type"] == "budget_warning"]
    assert len(warn_notifs) == 1

    # Deuxième appel : pas de doublon
    ok2 = await guard.reserve("project:pw", 0.05)
    assert ok2 is True
    warn_notifs2 = [n for n in notifications if n["type"] == "budget_warning"]
    assert len(warn_notifs2) == 1


@pytest.mark.asyncio
async def test_warn_pas_declenche_sous_seuil() -> None:
    notifications: list[dict] = []
    guard, _ = make_guard(per_project=1.0, warn_pct=80.0, notify=notifications)
    guard._project_spent["pw2"] = 0.0

    ok = await guard.reserve("project:pw2", 0.50)  # 50 % → ok
    assert ok is True
    assert not any(n["type"] == "budget_warning" for n in notifications)


# ── Tests claim atomique ──────────────────────────────────────────────────────


def test_claim_step_premier_worker_gagne() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            (Path(tmpdir) / "proj1" / ".jarvis").mkdir(parents=True, exist_ok=True)
            from jarvis.engine.mission.project_store import ProjectStore

            store = ProjectStore()

            ok1 = store.claim_step("proj1", "step-A", "worker-1")
            ok2 = store.claim_step("proj1", "step-A", "worker-2")

            assert ok1 is True
            assert ok2 is False  # déjà pris
        finally:
            ps_mod.WORKSPACE_DIR = original


def test_claim_step_deux_etapes_differentes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            (Path(tmpdir) / "proj2" / ".jarvis").mkdir(parents=True, exist_ok=True)
            from jarvis.engine.mission.project_store import ProjectStore

            store = ProjectStore()

            ok_a = store.claim_step("proj2", "step-A", "w1")
            ok_b = store.claim_step("proj2", "step-B", "w2")
            assert ok_a is True
            assert ok_b is True
        finally:
            ps_mod.WORKSPACE_DIR = original


def test_release_step_claim_permet_re_claim() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            (Path(tmpdir) / "proj3" / ".jarvis").mkdir(parents=True, exist_ok=True)
            from jarvis.engine.mission.project_store import ProjectStore

            store = ProjectStore()

            store.claim_step("proj3", "step-X", "w1")
            store.release_step_claim("proj3", "step-X")
            ok = store.claim_step("proj3", "step-X", "w2")
            assert ok is True  # libéré → re-claimable
        finally:
            ps_mod.WORKSPACE_DIR = original


# ── Tests pause / reprise budget ─────────────────────────────────────────────


def _make_project(tmpdir: str, project_id: str = "proj_test", n_steps: int = 3) -> object:
    from jarvis.engine.mission.schemas import Project, ProjectStatus, Step, StepStatus

    workspace = str(Path(tmpdir) / project_id)
    steps = [Step(id=f"s{i}", title=f"Step {i}", description=f"desc {i}") for i in range(n_steps)]
    steps[0].status = StepStatus.DONE
    steps[1].status = StepStatus.RUNNING
    # steps[2] reste PENDING
    return Project(
        id=project_id,
        title="Test project",
        mission="test",
        status=ProjectStatus.RUNNING,
        steps=steps,
        workspace_path=workspace,
    )


def test_pause_for_budget_met_running_en_pending() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            project = _make_project(tmpdir, "proj_pause")
            ws = Path(project.workspace_path)
            (ws / ".jarvis").mkdir(parents=True, exist_ok=True)

            from jarvis.engine.mission.project_store import ProjectStore
            from jarvis.engine.mission.schemas import ProjectStatus, StepStatus

            store = ProjectStore()

            store.claim_step("proj_pause", "s1", "w1")
            store.pause_for_budget(project, "s1")

            assert project.status == ProjectStatus.PAUSED
            assert project.steps[0].status == StepStatus.DONE
            assert project.steps[1].status == StepStatus.PENDING  # réinitialisé
            assert project.steps[2].status == StepStatus.PENDING

            # Le claim doit avoir été libéré
            ok_reclaim = store.claim_step("proj_pause", "s1", "w_new")
            assert ok_reclaim is True
        finally:
            ps_mod.WORKSPACE_DIR = original


def test_is_resumable_vrai_si_paused_avec_pending() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            project = _make_project(tmpdir, "proj_res")
            ws = Path(project.workspace_path)
            (ws / ".jarvis").mkdir(parents=True, exist_ok=True)

            from jarvis.engine.mission.project_store import ProjectStore

            store = ProjectStore()
            store.pause_for_budget(project, "s1")

            assert store.is_resumable(project) is True
        finally:
            ps_mod.WORKSPACE_DIR = original


def test_is_resumable_faux_si_running() -> None:
    import jarvis.engine.mission.project_store as ps_mod
    from jarvis.engine.mission.schemas import ProjectStatus

    project = _make_project("/tmp", "proj_run")
    project.status = ProjectStatus.RUNNING

    store = ps_mod.ProjectStore.__new__(ps_mod.ProjectStore)
    assert store.is_resumable(project) is False


def test_projet_pause_reprise_reprend_etapes_pending() -> None:
    """Un worker qui reprend un projet PAUSED doit sauter DONE et traiter PENDING."""
    from jarvis.engine.mission.schemas import StepStatus

    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvis.engine.mission.project_store as ps_mod

        original = ps_mod.WORKSPACE_DIR
        ps_mod.WORKSPACE_DIR = Path(tmpdir)
        try:
            project = _make_project(tmpdir, "proj_rep")
            ws = Path(project.workspace_path)
            (ws / ".jarvis").mkdir(parents=True, exist_ok=True)

            from jarvis.engine.mission.project_store import ProjectStore

            store = ProjectStore()
            store.pause_for_budget(project, "s1")

            # Simulation de la logique run() : skip DONE/SKIPPED
            pending_steps = [
                s for s in project.steps if s.status not in (StepStatus.DONE, StepStatus.SKIPPED)
            ]
            assert len(pending_steps) == 2  # s1 (reset PENDING) + s2 (était déjà PENDING)
            assert all(s.status == StepStatus.PENDING for s in pending_steps)
        finally:
            ps_mod.WORKSPACE_DIR = original
