# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
ProactiveEngine — orchestrateur principal.
Tourne en background toutes les 30 minutes.
Dispatche les initiatives selon leur mode d'exécution.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from loguru import logger

from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.proactive.context_builder import ContextBuilder
from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
from jarvis.engine.proactive.schemas import ExecutionMode, Initiative, Priority
from jarvis.engine.proactive.store import InitiativeStore

_AUDIT_MAXLEN = 200


# ── Audit ─────────────────────────────────────────────────────────────────────


@dataclass
class ProactiveAuditEvent:
    """Événement auditable émis pour chaque décision proactive."""

    event_id: str
    initiative_id: str
    initiative_title: str
    decision: str  # "notify" | "validate" | "auto"
    reasoning: str
    sources: list[str]
    decided_at: str  # ISO UTC


def _extract_sources(initiative: Initiative) -> list[str]:
    """Infère les sources d'information utilisées pour cette initiative."""
    text = f"{initiative.context} {initiative.reasoning}".lower()
    keywords: dict[str, list[str]] = {
        "email": ["email", "mail", "inbox"],
        "calendrier": ["calendar", "agenda", "event", "rdv"],
        "notion": ["notion", "tâche", "task"],
        "météo": ["météo", "weather", "pluie", "soleil"],
        "mémoire": ["memory", "mémoire", "session"],
    }
    found = [k for k, words in keywords.items() if any(w in text for w in words)]
    return found or ["proactive_context"]


class ProactiveEngine:
    """Phase C : `builder`, `generator`, `store` injectés (auparavant
    `ContextBuilder()`, `InitiativeGenerator()`, `InitiativeStore()`
    instanciés en interne). Les 3 helpers sont des objets simples
    sans déps, mais l'injection rend le ProactiveEngine testable
    (fakes pour builder/generator) sans patch global.
    """

    def __init__(
        self,
        notification_queue: NotificationQueue,
        broadcast_event: Callable,  # ProactiveQueue.broadcast_event(dict) sync
        builder: ContextBuilder,
        generator: InitiativeGenerator,
        store: InitiativeStore,
        interval_minutes: int = 30,
    ) -> None:
        self._notifications = notification_queue
        self._broadcast_event = broadcast_event
        self._interval = interval_minutes * 60
        self._builder = builder
        self._generator = generator
        self._store = store
        self._running = False
        self._last_run: datetime | None = None
        self._last_user_activity: datetime | None = None
        self._cycle_lock = asyncio.Lock()  # un seul cycle à la fois
        self._audit_log: deque[ProactiveAuditEvent] = deque(maxlen=_AUDIT_MAXLEN)

    def signal_user_activity(self) -> None:
        """Appelé par le WebSocket à chaque message entrant."""
        self._last_user_activity = datetime.now()

    def _user_idle_seconds(self) -> float:
        """Secondes écoulées depuis le dernier message utilisateur."""
        if self._last_user_activity is None:
            return float("inf")
        return (datetime.now() - self._last_user_activity).total_seconds()

    async def start(self) -> None:
        """Lance la boucle de proactivité en background."""
        self._running = True
        logger.info(f"ProactiveEngine started (interval: {self._interval // 60}min)")

        # Restaure les initiatives pending avant d'attendre le premier cycle
        await self._restore_pending()

        # Premier run dans 2 minutes — pas immédiatement au boot
        await asyncio.sleep(120)

        while self._running:
            await self._run_cycle()
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def _restore_pending(self) -> None:
        """Recharge les initiatives pending et signal le Command Center en un seul event."""
        pending = self._store.load_pending_all(days=7)
        if not pending:
            return
        # Un seul événement groupé — évite N rechargements UI en cascade
        self._broadcast_event({"type": "initiatives_restored", "count": len(pending)})
        logger.info(f"ProactiveEngine: {len(pending)} initiatives pending restaurées")

    async def run_now(self) -> list[Initiative]:
        """Force un cycle immédiatement (debug ou bouton manuel)."""
        return await self._run_cycle()

    def audit_events(self, limit: int = 50) -> list[ProactiveAuditEvent]:
        """Retourne les derniers événements d'audit (plus récent en premier)."""
        return list(reversed(list(self._audit_log)))[:limit]

    async def _run_cycle(self) -> list[Initiative]:
        """Un cycle complet : collecte → build → generate → dispatch."""
        if self._cycle_lock.locked():
            logger.info("ProactiveEngine: cycle already running, skipping")
            return []

        async with self._cycle_lock:
            return await self.__run_cycle_locked()

    async def __run_cycle_locked(self) -> list[Initiative]:
        logger.info("ProactiveEngine: starting cycle")
        self._last_run = datetime.now()

        try:
            state = await self._builder.build()

            # Même pattern que le websocket existant (sleep(2) avant background LLM) :
            # attendre que l'utilisateur soit inactif avant de faire l'appel LLM lourd.
            _COOLDOWN_S = 120  # 2 minutes d'inactivité requises
            idle = self._user_idle_seconds()
            if idle < _COOLDOWN_S:
                wait = _COOLDOWN_S - idle
                logger.info(
                    f"ProactiveEngine: user active {idle:.0f}s ago, "
                    f"waiting {wait:.0f}s before LLM call"
                )
                await asyncio.sleep(wait)

            initiatives = await self._generator.generate(state)

            if not initiatives:
                logger.info("ProactiveEngine: no initiatives generated")
                return []

            for initiative in initiatives:
                self._store.save(initiative)

            for initiative in initiatives:
                self._dispatch(initiative)

            high_count = sum(1 for i in initiatives if i.priority == Priority.HIGH)
            logger.info(
                f"ProactiveEngine: cycle complete — "
                f"{len(initiatives)} initiatives, {high_count} HIGH"
            )

            self._broadcast_event(
                {
                    "type": "proactive_update",
                    "count": len(initiatives),
                    "high_priority": high_count,
                }
            )

            return initiatives

        except Exception as e:
            logger.error(f"ProactiveEngine cycle error: {e}")
            return []

    def _dispatch(self, initiative: Initiative) -> None:
        """Dispatche une initiative selon son mode d'exécution."""
        audit = ProactiveAuditEvent(
            event_id=f"aud_{uuid.uuid4().hex[:8]}",
            initiative_id=initiative.id,
            initiative_title=initiative.title,
            decision=str(initiative.execution_mode),
            reasoning=(initiative.reasoning or initiative.action)[:200],
            sources=_extract_sources(initiative),
            decided_at=datetime.now(UTC).isoformat(),
        )
        self._audit_log.append(audit)
        self._broadcast_event({"type": "proactive_audit", "event": asdict(audit)})
        logger.info(
            f"ProactiveEngine AUDIT [{audit.decision}] {audit.initiative_title!r} "
            f"— {audit.reasoning[:80]} | sources={audit.sources}"
        )

        if initiative.execution_mode == ExecutionMode.AUTO:
            # Auto-exécution réservée à la Phase 2
            logger.info(f"ProactiveEngine AUTO (logged): {initiative.title}")

        elif initiative.execution_mode == ExecutionMode.NOTIFY:
            # Injecter comme notification texte dans la prochaine conversation
            msg = f"[Jarvis proactif] {initiative.title} — {initiative.action}"
            self._notifications.add(msg)
            logger.info(f"ProactiveEngine NOTIFY: {initiative.title}")

        elif initiative.execution_mode == ExecutionMode.VALIDATE:
            # Envoyer au Command Center pour validation
            self._broadcast_event(
                {
                    "type": "initiative_pending",
                    "initiative": {
                        "id": initiative.id,
                        "type": initiative.type,
                        "title": initiative.title,
                        "context": initiative.context,
                        "reasoning": initiative.reasoning,
                        "action": initiative.action,
                        "priority": initiative.priority,
                        "draft_content": initiative.draft_content,
                        "created_at": initiative.created_at.isoformat(),
                    },
                }
            )
            logger.info(f"ProactiveEngine VALIDATE: {initiative.title}")
