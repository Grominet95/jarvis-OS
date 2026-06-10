"""Tests du bus d'événements kernel.events (CDC §A.1.3)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from jarvis.kernel.events import (
    BudgetThresholdReached,
    EventBus,
    MemoryIngested,
    MissionCompleted,
    NotificationRequested,
    bus,
)


@dataclass(frozen=True)
class _OtherEvent:
    payload: str


def test_singleton_bus_is_event_bus() -> None:
    assert isinstance(bus, EventBus)


@pytest.mark.asyncio
async def test_publish_invokes_subscribed_handler() -> None:
    b = EventBus()
    received: list[MissionCompleted] = []

    async def handler(ev: MissionCompleted) -> None:
        received.append(ev)

    b.subscribe(MissionCompleted, handler)
    ev = MissionCompleted(mission_id="m1", verdict="success")
    await b.publish(ev)

    assert received == [ev]


@pytest.mark.asyncio
async def test_publish_skips_other_event_types() -> None:
    """Un handler abonné au type X ne reçoit PAS un événement de type Y."""
    b = EventBus()
    received: list = []

    async def handler(ev: MissionCompleted) -> None:
        received.append(ev)

    b.subscribe(MissionCompleted, handler)
    await b.publish(_OtherEvent(payload="bidon"))

    assert received == []


@pytest.mark.asyncio
async def test_publish_with_no_handlers_is_noop() -> None:
    b = EventBus()
    # Pas d'abonné — ne doit pas lever.
    await b.publish(MemoryIngested(event_id="e1", fact_count=3, source="test"))


@pytest.mark.asyncio
async def test_failing_handler_does_not_block_other_handlers() -> None:
    """Isolation : un handler qui lève n'empêche pas les autres d'être appelés."""
    b = EventBus()
    received: list[str] = []

    async def failing(ev: NotificationRequested) -> None:
        raise RuntimeError("boom")

    async def working_a(ev: NotificationRequested) -> None:
        received.append("a")

    async def working_b(ev: NotificationRequested) -> None:
        received.append("b")

    b.subscribe(NotificationRequested, failing)
    b.subscribe(NotificationRequested, working_a)
    b.subscribe(NotificationRequested, working_b)

    await b.publish(NotificationRequested(channel="ws", payload={"x": 1}))

    assert sorted(received) == ["a", "b"]


@pytest.mark.asyncio
async def test_unsubscribe_removes_handler() -> None:
    b = EventBus()
    received: list = []

    async def handler(ev: BudgetThresholdReached) -> None:
        received.append(ev)

    b.subscribe(BudgetThresholdReached, handler)
    b.unsubscribe(BudgetThresholdReached, handler)
    await b.publish(BudgetThresholdReached(ratio=0.9, provider="anthropic", scope="daily"))

    assert received == []


@pytest.mark.asyncio
async def test_unsubscribe_unknown_handler_is_noop() -> None:
    b = EventBus()

    async def handler(ev: MissionCompleted) -> None:
        pass

    # Ne lève pas même si jamais abonné.
    b.unsubscribe(MissionCompleted, handler)


@pytest.mark.asyncio
async def test_handlers_run_concurrently() -> None:
    """Les handlers async sont gather-és — durée ~= max(handler), pas sum."""
    b = EventBus()

    async def slow_a(ev: MissionCompleted) -> None:
        await asyncio.sleep(0.05)

    async def slow_b(ev: MissionCompleted) -> None:
        await asyncio.sleep(0.05)

    b.subscribe(MissionCompleted, slow_a)
    b.subscribe(MissionCompleted, slow_b)

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await b.publish(MissionCompleted(mission_id="m1", verdict="success"))
    elapsed = loop.time() - t0

    # Concurrence : ~0.05s, pas ~0.10s. Marge confortable pour le CI.
    assert elapsed < 0.09, f"handlers semblent séquentiels (elapsed={elapsed:.3f}s)"


def test_events_are_frozen_dataclasses() -> None:
    """Les événements sont immuables — un handler ne peut pas muter le payload."""
    ev = MissionCompleted(mission_id="m1", verdict="success")
    # FrozenInstanceError hérite de AttributeError (dataclasses, Python 3.11+).
    with pytest.raises(AttributeError):
        ev.mission_id = "m2"  # type: ignore[misc]
