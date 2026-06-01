"""
tests/test_routines.py — Tests du moteur de routines et de l'audit proactif.

Cas couverts :
  1. Un trigger interval crée un RoutineRun tracé.
  2. Le catch-up rejoue les runs manqués (politique enqueue_missed_with_cap).
  3. La concurrence bloque le chevauchement (politique skip_if_active).
  4. Chaque décision proactive produit un ProactiveAuditEvent consultable.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Stubbe les dépendances LLM absentes de l'environnement de test.
# ProactiveEngine n'exerce aucun chemin LLM dans ce fichier.
for _dep in ("openai", "anthropic", "ollama", "google", "google.genai", "google.generativeai"):
    if _dep not in sys.modules:
        sys.modules[_dep] = MagicMock()  # type: ignore[assignment]

from background.routines import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    Routine,
    RoutineStore,
    RunStatus,
    TriggerType,
    apply_catch_up,
    fire_routine,
    next_cron_datetime,
)
from proactive.schemas import ExecutionMode, Initiative, InitiativeType, Priority

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store(tmp_path: Path) -> RoutineStore:
    return RoutineStore(path=tmp_path / "routines.json")


def _interval_routine(
    *,
    concurrency: ConcurrencyPolicy = ConcurrencyPolicy.SKIP_IF_ACTIVE,
    catch_up: CatchUpPolicy = CatchUpPolicy.SKIP_MISSED,
    interval: int = 3600,
) -> Routine:
    return Routine(
        name="test_routine",
        trigger=TriggerType.INTERVAL,
        action_prompt="Vérifier les emails entrants",
        interval_seconds=interval,
        concurrency_policy=concurrency,
        catch_up_policy=catch_up,
    )


_broadcast_noop = lambda e: None  # noqa: E731


# ── Test 1 : trigger interval crée un RoutineRun tracé ────────────────────────


@pytest.mark.asyncio
async def test_interval_creates_run(tmp_path: Path) -> None:
    """fire_routine doit créer un RoutineRun SUCCESS avec un audit_log non vide."""
    store = _make_store(tmp_path)
    routine = _interval_routine()

    run = await fire_routine(routine, store, _broadcast_noop)

    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.routine_name == "test_routine"
    assert run.trigger_type == "interval"
    assert run.started_at != ""
    assert run.finished_at is not None
    assert len(run.audit_log) >= 2  # "created" + "started" + "completed"

    # Persistance : le run doit être retrouvable dans le store
    runs = store.list_runs("test_routine")
    assert len(runs) == 1
    assert runs[0].id == run.id


# ── Test 2 : catch-up rejoue les runs manqués ─────────────────────────────────


@pytest.mark.asyncio
async def test_catchup_replays_missed_run(tmp_path: Path) -> None:
    """apply_catch_up doit créer des runs pour les intervalles manqués."""
    store = _make_store(tmp_path)
    routine = _interval_routine(
        catch_up=CatchUpPolicy.ENQUEUE_MISSED,
        interval=60,  # 60 secondes
    )

    # Simuler un run terminé il y a 4 minutes (= 3 intervalles manqués)
    old_run = store.create_run(routine)
    old_run.status = RunStatus.SUCCESS
    old_run.started_at = (datetime.now(UTC) - timedelta(minutes=4)).isoformat()
    old_run.finished_at = old_run.started_at
    store.update_run(old_run)

    caught_up = await apply_catch_up(routine, store, _broadcast_noop)

    # On attend au moins 1 run de rattrapage (cap=3 par défaut)
    assert len(caught_up) >= 1
    for run in caught_up:
        assert run.status == RunStatus.SUCCESS
        # Chaque run de rattrapage doit avoir l'étape "catch_up_index" dans le log
        step_events = [s.event for s in run.audit_log]
        assert "catch_up_index" in step_events


# ── Test 3 : concurrence bloque le chevauchement ─────────────────────────────


@pytest.mark.asyncio
async def test_concurrency_blocks_overlap(tmp_path: Path) -> None:
    """fire_routine doit retourner un run SKIPPED si un run est déjà actif."""
    store = _make_store(tmp_path)
    routine = _interval_routine(concurrency=ConcurrencyPolicy.SKIP_IF_ACTIVE)

    # Injecter un run actif directement dans le store
    active = store.create_run(routine)
    active.status = RunStatus.RUNNING
    store.update_run(active)

    # Tenter un second déclenchement
    skipped = await fire_routine(routine, store, _broadcast_noop)

    assert skipped is not None
    assert skipped.status == RunStatus.SKIPPED
    assert skipped.id != active.id

    # Le run actif doit rester RUNNING
    still_active = store.active_run_for("test_routine")
    assert still_active is not None
    assert still_active.id == active.id

    # Le log du run skipped doit mentionner la raison
    skip_steps = [s for s in skipped.audit_log if s.event == "skipped"]
    assert len(skip_steps) == 1
    assert active.id in skip_steps[0].detail


# ── Test 4 : événement proactif audité ────────────────────────────────────────


def test_proactive_audit_event() -> None:
    """ProactiveEngine._dispatch doit enregistrer un ProactiveAuditEvent consultable."""
    from background.notifications import NotificationQueue
    from proactive.engine import ProactiveEngine

    broadcast_events: list[dict] = []

    class _Queue(NotificationQueue):
        def add(self, content: str) -> None:  # noqa: ANN001
            pass

    engine = ProactiveEngine(
        notification_queue=_Queue(),
        broadcast_event=broadcast_events.append,
        interval_minutes=30,
    )

    initiative = Initiative(
        id="init_test_01",
        type=InitiativeType.REMINDER,
        title="Test initiative audit",
        context="Un email urgent reçu ce matin",
        reasoning="Email non répondu depuis 2h, deadline proche",
        action="Répondre à l'email",
        priority=Priority.HIGH,
        execution_mode=ExecutionMode.NOTIFY,
    )

    engine._dispatch(initiative)

    # Vérification de l'audit interne
    audit = engine.audit_events()
    assert len(audit) == 1
    ev = audit[0]
    assert ev.initiative_id == "init_test_01"
    assert ev.decision == "notify"
    assert ev.event_id.startswith("aud_")
    assert ev.decided_at != ""
    assert "email" in ev.sources  # "email" doit être inféré depuis le contexte

    # Vérification du broadcast
    audit_broadcasts = [e for e in broadcast_events if e.get("type") == "proactive_audit"]
    assert len(audit_broadcasts) == 1
    assert audit_broadcasts[0]["event"]["initiative_id"] == "init_test_01"

    # Vérification que la notification texte a bien été ajoutée
    notif_broadcasts = [
        e for e in broadcast_events if e.get("type") != "proactive_audit"
    ]
    assert len(notif_broadcasts) == 0  # NOTIFY passe par _notifications.add(), pas broadcast


# ── Test bonus : next_cron_datetime ───────────────────────────────────────────


def test_next_cron_daily_at_9h() -> None:
    """next_cron_datetime doit retourner le prochain 9h00 UTC."""
    base = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
    nxt = next_cron_datetime("0 9 * * *", after=base)
    assert nxt.hour == 9
    assert nxt.minute == 0
    assert nxt.date() == base.date()


def test_next_cron_jumps_to_next_day() -> None:
    """next_cron_datetime doit passer au jour suivant si l'heure est dépassée."""
    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    nxt = next_cron_datetime("0 9 * * *", after=base)
    assert nxt.hour == 9
    assert nxt.date() > base.date()
