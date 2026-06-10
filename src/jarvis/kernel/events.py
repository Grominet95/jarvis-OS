"""Bus d'événements pub/sub asyncio — CDC §A.1.3.

Bus minimaliste : enregistre des handlers async par type d'événement, publie
en gather() avec isolation des exceptions (un handler qui lève ne casse pas
les autres, l'erreur est loguée).

Personne ne s'y abonne en Phase A — le branchement effectif est en Phase D
(casser le CYCLE 4 engine ← background).

Les événements sont des dataclasses figées (frozen) pour garantir l'immuabilité
des payloads en transit.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

# Type alias pour la signature d'un handler.
EventHandler = Callable[[Any], Awaitable[None]]


# ── Événements du noyau (premiers candidats — CDC §A.1.3) ──────────────────────


@dataclass(frozen=True)
class MissionCompleted:
    """Une mission du Mission Engine s'est terminée (succès ou échec)."""

    mission_id: str
    verdict: str  # "success" | "failure" | "killed"
    artifacts: dict = field(default_factory=dict)
    completed_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class MemoryIngested:
    """Un fact (ou un batch) vient d'être ingéré dans la mémoire."""

    event_id: str
    fact_count: int
    source: str
    ingested_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class NotificationRequested:
    """Une couche basse demande qu'une notification soit envoyée à l'utilisateur."""

    channel: str  # "websocket" | "telegram" | …
    payload: dict
    priority: str = "normal"  # "low" | "normal" | "high"


@dataclass(frozen=True)
class BudgetThresholdReached:
    """Un seuil de budget LLM a été franchi (ratio sur le plafond de la mission/jour)."""

    ratio: float  # 0.0 → 1.0
    provider: str
    scope: str  # "mission" | "daily" | …


# ── Bus ──────────────────────────────────────────────────────────────────────


class EventBus:
    """Bus pub/sub asyncio.

    Usage :
        bus = EventBus()
        async def on_mission(ev: MissionCompleted) -> None: ...
        bus.subscribe(MissionCompleted, on_mission)
        await bus.publish(MissionCompleted(mission_id="abc", verdict="success"))
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Enregistre un handler async pour un type d'événement."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: EventHandler) -> None:
        """Retire un handler. No-op s'il n'était pas enregistré."""
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Any) -> None:  # noqa: ANN401 — type d'événement dispatché dynamiquement
        """Publie un événement vers tous les handlers de son type.

        Les handlers sont exécutés concurremment via asyncio.gather. Toute
        exception levée par un handler est loguée mais NE casse PAS les autres
        handlers (return_exceptions=True).
        """
        event_type = type(event)
        handlers = list(self._handlers.get(event_type, []))
        if not handlers:
            return
        results = await asyncio.gather(
            *(handler(event) for handler in handlers), return_exceptions=True
        )
        for handler, result in zip(handlers, results, strict=True):
            if isinstance(result, Exception):
                logger.error(
                    "EventBus handler error",
                    event=event_type.__name__,
                    handler=getattr(handler, "__qualname__", repr(handler)),
                    error=str(result),
                )


# Singleton module — branché par bootstrap.py en Phase C.
bus = EventBus()
