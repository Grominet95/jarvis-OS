from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from loguru import logger

from background.notifications import ProactiveQueue
from background.routines import (
    ROUTINES_ENABLED,
    CatchUpPolicy,
    Routine,
    RoutineStore,
    TriggerType,
    apply_catch_up,
    fire_routine,
    next_cron_datetime,
)
from config.settings import settings
from memory.auto_dream import AutoDream
from tools.calendar import CalendarListTool


def _next_datetime(hour: int) -> datetime:
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _seconds_until(hour: int) -> float:
    return (_next_datetime(hour) - datetime.now()).total_seconds()


class Scheduler:
    """Planifie les boucles asyncio : briefing 9h, rappels calendrier, autoDream, routines."""

    def __init__(
        self,
        proactive: ProactiveQueue,
        auto_dream: AutoDream,
        calendar_tool: CalendarListTool,
    ) -> None:
        self._proactive = proactive
        self._auto_dream = auto_dream
        self._calendar_tool = calendar_tool
        self._tasks: list[asyncio.Task] = []
        self._routine_tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._briefing_loop(), name="scheduler-briefing"),
            asyncio.create_task(self._calendar_loop(), name="scheduler-calendar"),
            asyncio.create_task(self._autodream_loop(), name="scheduler-autodream"),
        ]
        logger.info("Scheduler started", tasks=len(self._tasks))

    def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._routine_tasks:
            t.cancel()

    def start_routines(
        self,
        routines: list[Routine],
        store: RoutineStore,
        wake_engine: Callable[[], None] | None = None,
    ) -> None:
        """Démarre une boucle asyncio par routine activée.

        Ne fait rien si ROUTINES_ENABLED=false ou si la liste est vide.
        """
        if not ROUTINES_ENABLED:
            logger.info("Scheduler: routines désactivées (ROUTINES_ENABLED=false)")
            return

        started = 0
        for routine in routines:
            if not routine.enabled:
                continue
            if routine.trigger == TriggerType.INTERVAL and routine.interval_seconds:
                t = asyncio.create_task(
                    self._routine_interval_loop(routine, store, wake_engine),
                    name=f"routine-interval-{routine.name}",
                )
                self._routine_tasks.append(t)
                started += 1
            elif routine.trigger == TriggerType.CRON and routine.cron_expr:
                t = asyncio.create_task(
                    self._routine_cron_loop(routine, store, wake_engine),
                    name=f"routine-cron-{routine.name}",
                )
                self._routine_tasks.append(t)
                started += 1
            else:
                logger.debug(
                    f"Routine '{routine.name}': trigger {routine.trigger} ignoré "
                    "(webhook géré par API)"
                )
        logger.info(f"Scheduler: {started} routine(s) démarrée(s)")

    def status(self) -> list[dict]:
        return [
            {
                "name": "Briefing matinal",
                "description": f"Agenda + tâches Notion à {settings.briefing_hour}h00",
                "next_run": _next_datetime(settings.briefing_hour).isoformat(),
                "interval": "quotidien",
            },
            {
                "name": "Rappels calendrier",
                "description": (
                    f"Rappel {settings.calendar_reminder_minutes} min avant chaque event"
                ),
                "next_run": None,
                "interval": "toutes les 60s",
            },
            {
                "name": "AutoDream deep",
                "description": "Analyse nocturne des sessions",
                "next_run": _next_datetime(3).isoformat(),
                "interval": "quotidien",
            },
        ]

    # ── Routines ──────────────────────────────────────────────

    async def _routine_interval_loop(
        self,
        routine: Routine,
        store: RoutineStore,
        wake_engine: Callable[[], None] | None,
    ) -> None:
        """Boucle d'exécution pour une routine à intervalle fixe."""
        interval = routine.interval_seconds or 3600

        # Rattrapage au démarrage si des runs ont été manqués
        if routine.catch_up_policy == CatchUpPolicy.ENQUEUE_MISSED:
            await apply_catch_up(routine, store, self._proactive.broadcast_event, wake_engine)

        while True:
            await asyncio.sleep(interval)
            await fire_routine(
                routine, store, self._proactive.broadcast_event, wake_engine
            )

    async def _routine_cron_loop(
        self,
        routine: Routine,
        store: RoutineStore,
        wake_engine: Callable[[], None] | None,
    ) -> None:
        """Boucle d'exécution pour une routine à expression cron."""
        expr = routine.cron_expr or "0 * * * *"
        while True:
            now = datetime.now(UTC)
            try:
                next_run = next_cron_datetime(expr, after=now)
            except ValueError as exc:
                logger.error(
                    f"Routine '{routine.name}': expression cron invalide — {exc}"
                )
                await asyncio.sleep(3600)
                continue

            delay = (next_run - datetime.now(UTC)).total_seconds()
            logger.debug(
                f"Routine '{routine.name}' (cron): prochaine exécution "
                f"dans {delay:.0f}s ({next_run.isoformat()})"
            )
            await asyncio.sleep(max(delay, 0))
            await fire_routine(
                routine, store, self._proactive.broadcast_event, wake_engine
            )

    # ── Briefing matinal ─────────────────────────────────────

    async def _briefing_loop(self) -> None:
        while True:
            delay = _seconds_until(settings.briefing_hour)
            logger.debug("Briefing planifié", seconds=int(delay))
            await asyncio.sleep(delay)
            await self._send_briefing()

    async def _send_briefing(self) -> None:
        parts: list[str] = []

        try:
            result = await self._calendar_tool.execute(days_ahead=1)
            agenda = result.content if not result.is_error else "Agenda indisponible."
            parts.append(f"Agenda : {agenda}")
        except Exception as e:
            parts.append(f"Agenda indisponible ({e}).")

        try:
            from tools.notion import NotionTasksTool
            tasks_result = await NotionTasksTool().execute()
            if not tasks_result.is_error and tasks_result.content:
                parts.append(f"Tâches du jour :\n{tasks_result.content}")
        except Exception as e:
            logger.debug("Briefing Notion error", error=str(e))

        self._proactive.broadcast("Briefing matinal — " + " | ".join(parts))
        logger.info("Briefing matinal envoyé")

    # ── Rappels calendrier ────────────────────────────────────

    async def _calendar_loop(self) -> None:
        seen: set[str] = set()
        await asyncio.sleep(10)  # court délai initial — calendrier pas encore auth au démarrage
        while True:
            await self._check_reminders(seen)
            await asyncio.sleep(60)

    # Format renvoyé par CalendarListTool : "- 2024-01-15T14:00:00+01:00 : Titre"
    _ISO_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})")

    async def _check_reminders(self, seen: set[str]) -> None:
        try:
            result = await self._calendar_tool.execute(days_ahead=2)
            if result.is_error:
                logger.debug("Calendar reminder: tool error", content=result.content[:80])
                return
            now = datetime.now(UTC)
            cutoff = settings.calendar_reminder_minutes
            lines = [ln.strip() for ln in result.content.splitlines() if ln.strip()]
            logger.debug("Calendar reminder check", events=len(lines), cutoff_min=cutoff)
            for line in lines:
                fingerprint = line[:80]
                if fingerprint in seen:
                    continue
                iso_match = self._ISO_RE.search(line)
                if not iso_match:
                    continue
                try:
                    event_time = datetime.fromisoformat(iso_match.group(1))
                except ValueError:
                    continue
                delta_min = (event_time - now).total_seconds() / 60
                logger.debug("Calendar event delta", delta_min=round(delta_min, 1), event=line[:60])
                if 0 < delta_min <= cutoff:
                    seen.add(fingerprint)
                    self._proactive.broadcast(
                        f"Rappel dans {int(delta_min)} min : {line}"
                    )
                    logger.info("Rappel calendrier envoyé", event=line[:60])
        except Exception:
            logger.exception("Calendar reminder error")

    # ── AutoDream nocturne ────────────────────────────────────

    async def _autodream_loop(self) -> None:
        while True:
            delay = _seconds_until(3)
            logger.debug("AutoDream deep planifié", seconds=int(delay))
            await asyncio.sleep(delay)
            logger.info("AutoDream deep démarré")
            await self._auto_dream.deep_analyze()
