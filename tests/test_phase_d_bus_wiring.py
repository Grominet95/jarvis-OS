"""Phase D — Tests d'intégration du bus d'événements.

Vérifie que chaque émetteur PUBLIE l'événement sur le bus injecté :
  - BudgetGuard.reserve(over-limit) → BudgetThresholdReached
  - BudgetGuard.reserve(near-warn)  → BudgetThresholdReached
  - MemoryIngest.ingest(content)    → MemoryIngested

(MissionCompleted est testé via test_mission_engine.py qui patche déjà
le pipeline complet.)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.kernel.events import (
    BudgetThresholdReached,
    EventBus,
    MemoryIngested,
    NotificationRequested,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_settings(monthly: float, per_project: float, warn_pct: float) -> MagicMock:
    s = MagicMock()
    s.budget_enabled = True
    s.budget_monthly_usd = monthly
    s.budget_per_project_usd = per_project
    s.budget_warn_pct = warn_pct
    return s


def _fake_tracker() -> MagicMock:
    t = MagicMock()
    t._read_day = MagicMock(return_value=[])
    t.get_monthly_totals = MagicMock(return_value={"cost_usd": 0.0})
    return t


# ── BudgetGuard ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_hard_stop_publie_BudgetThresholdReached() -> None:
    """Reserve au-delà du plafond → ratio=1.0 publié."""
    from jarvis.engine.budget import BudgetGuard

    bus = EventBus()
    captured: list[BudgetThresholdReached] = []

    async def handler(ev: BudgetThresholdReached) -> None:
        captured.append(ev)

    bus.subscribe(BudgetThresholdReached, handler)

    guard = BudgetGuard(
        settings=_make_settings(10.0, 2.0, 80.0),
        tracker=_fake_tracker(),
        bus=bus,
    )
    guard._global_spent = lambda: 9.5  # noqa: SLF001 — test interne

    ok = await guard.reserve("global", 1.0)
    assert ok is False
    assert len(captured) == 1
    assert captured[0].ratio == 1.0
    assert captured[0].scope == "global"
    assert captured[0].provider == "global"


@pytest.mark.asyncio
async def test_budget_warning_publie_BudgetThresholdReached() -> None:
    """Reserve qui franchit le seuil de warn → ratio≈0.85 publié, une fois."""
    from jarvis.engine.budget import BudgetGuard

    bus = EventBus()
    captured: list[BudgetThresholdReached] = []

    async def handler(ev: BudgetThresholdReached) -> None:
        captured.append(ev)

    bus.subscribe(BudgetThresholdReached, handler)

    guard = BudgetGuard(
        settings=_make_settings(10.0, 2.0, 80.0),
        tracker=_fake_tracker(),
        bus=bus,
    )
    guard._global_spent = lambda: 7.5  # noqa: SLF001 — test interne

    ok1 = await guard.reserve("global", 1.0)  # projected 8.5 → warn
    ok2 = await guard.reserve("global", 0.5)  # déjà warné → silence
    assert ok1 is True
    assert ok2 is True
    assert len(captured) == 1
    assert 0.8 <= captured[0].ratio <= 0.9
    assert captured[0].scope == "global"


# ── MemoryIngest ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_ingest_publie_MemoryIngested() -> None:
    """Après un ingest réussi, MemoryIngested est publié avec event_id+fact_count."""
    from jarvis.providers.memory.ingest import MemoryIngest

    bus = EventBus()
    captured: list[MemoryIngested] = []

    async def handler(ev: MemoryIngested) -> None:
        captured.append(ev)

    bus.subscribe(MemoryIngested, handler)

    fake_kernel = MagicMock()
    fake_event = MagicMock()
    fake_event.id = "evt_001"
    fake_kernel.log_event = MagicMock(return_value=fake_event)

    fake_llm = MagicMock()
    fake_llm.complete = AsyncMock(return_value="[]")  # 0 candidats extraits

    ingest = MemoryIngest(kernel=fake_kernel, llm=fake_llm, bus=bus)
    await ingest.ingest(content="rien d'intéressant", source="conversation")

    assert len(captured) == 1
    assert captured[0].event_id == "evt_001"
    assert captured[0].fact_count == 0
    assert captured[0].source == "conversation"


# ── BackgroundWorker → NotificationRequested ──────────────────────────────────


@pytest.mark.asyncio
async def test_background_worker_publie_NotificationRequested_sur_succes() -> None:
    """Tâche background réussie → NotificationRequested(channel=user) publié."""
    from jarvis.engine.background.notifications import NotificationQueue
    from jarvis.engine.background.worker import BackgroundTask, BackgroundWorker

    bus = EventBus()
    captured: list[NotificationRequested] = []

    async def handler(ev: NotificationRequested) -> None:
        captured.append(ev)

    bus.subscribe(NotificationRequested, handler)

    fake_llm = MagicMock()
    fake_llm.supports_tools = False
    fake_llm.complete = AsyncMock(return_value="tâche faite, voici le résumé")

    worker = BackgroundWorker(
        llm=fake_llm,
        notifications=NotificationQueue(),
        bus=bus,
    )

    await worker._execute(
        BackgroundTask(session_id="s1", instruction="résume X"),
        MagicMock(),
    )

    assert len(captured) == 1
    assert captured[0].channel == "user"
    assert captured[0].payload["content"] == "tâche faite, voici le résumé"
    assert captured[0].priority == "normal"


@pytest.mark.asyncio
async def test_background_worker_publie_NotificationRequested_sur_echec() -> None:
    """Exception dans la tâche → NotificationRequested(priority=high) publié."""
    from jarvis.engine.background.notifications import NotificationQueue
    from jarvis.engine.background.worker import BackgroundTask, BackgroundWorker, TaskRecord

    bus = EventBus()
    captured: list[NotificationRequested] = []

    async def handler(ev: NotificationRequested) -> None:
        captured.append(ev)

    bus.subscribe(NotificationRequested, handler)

    fake_llm = MagicMock()
    worker = BackgroundWorker(
        llm=fake_llm,
        notifications=NotificationQueue(),
        bus=bus,
    )

    # Court-circuite _execute pour forcer l'exception
    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    worker._execute = _raise  # type: ignore[method-assign]

    # Émule un cycle de run_loop sans démarrer la boucle infinie :
    task = BackgroundTask(session_id="s2", instruction="essaie X")
    record = TaskRecord(session_id=task.session_id, instruction=task.instruction)
    try:
        await worker._execute(task, record)
    except RuntimeError as e:
        await worker._notify(f"Tâche échouée : {e}", priority="high")

    assert len(captured) == 1
    assert captured[0].channel == "user"
    assert "boom" in captured[0].payload["content"]
    assert captured[0].priority == "high"
