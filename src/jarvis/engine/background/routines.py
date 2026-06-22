# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
background/routines.py — Moteur de routines planifiées de Jarvis.

Modèles : Routine, RoutineRun, AuditStep.
Store   : RoutineStore (mémoire + JSON).
Helpers : fire_routine, apply_catch_up, next_cron_datetime.

Le flag ROUTINES_ENABLED est lu depuis la variable d'env ROUTINES_ENABLED
(pas depuis config/settings.py pour rester dans le périmètre autorisé).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from loguru import logger

# ── Flag module ───────────────────────────────────────────────────────────────
# Lu depuis l'env — default OFF pour ne pas impacter les installations existantes.
ROUTINES_ENABLED: bool = os.getenv("ROUTINES_ENABLED", "false").lower() == "true"

_STORE_PATH: Path = Path(os.getenv("ROUTINES_STORE_PATH", "data/routines.json"))
_CATCH_UP_MAX: int = int(os.getenv("ROUTINES_CATCH_UP_MAX", "3"))
_RUNS_HISTORY: int = 200


# ── Enums ─────────────────────────────────────────────────────────────────────


class TriggerType(StrEnum):
    CRON = "cron"
    INTERVAL = "interval"
    WEBHOOK = "webhook"


class ConcurrencyPolicy(StrEnum):
    """Comportement quand un run est déjà actif au déclenchement."""

    SKIP_IF_ACTIVE = "skip_if_active"
    COALESCE = "coalesce"  # fusionne dans le run actif
    ALWAYS_ENQUEUE = "always_enqueue"


class CatchUpPolicy(StrEnum):
    """Comportement pour les runs manqués pendant une indisponibilité."""

    SKIP_MISSED = "skip_missed"
    ENQUEUE_MISSED = "enqueue_missed_with_cap"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Modèles ───────────────────────────────────────────────────────────────────


@dataclass
class AuditStep:
    """Étape tracée dans le journal d'un RoutineRun."""

    ts: str
    event: str
    detail: str = ""


@dataclass
class Routine:
    """Définition déclarative d'une routine planifiée."""

    name: str
    trigger: TriggerType
    action_prompt: str
    target_channel: str = "notification"
    concurrency_policy: ConcurrencyPolicy = ConcurrencyPolicy.SKIP_IF_ACTIVE
    catch_up_policy: CatchUpPolicy = CatchUpPolicy.SKIP_MISSED
    enabled: bool = True
    # cron trigger : expression 5-champs standard, ex. "0 9 * * *"
    cron_expr: str | None = None
    # interval trigger : secondes entre deux exécutions
    interval_seconds: int | None = None


@dataclass
class RoutineRun:
    """Enregistrement tracé et auditable d'une exécution de Routine."""

    id: str
    routine_name: str
    trigger_type: str
    started_at: str
    finished_at: str | None = None
    status: RunStatus = RunStatus.PENDING
    cost_usd: float | None = None
    result_summary: str | None = None
    audit_log: list[AuditStep] = field(default_factory=list)

    def add_step(self, event: str, detail: str = "") -> None:
        """Ajoute une étape d'audit horodatée (UTC)."""
        self.audit_log.append(
            AuditStep(ts=datetime.now(UTC).isoformat(), event=event, detail=detail)
        )


# ── Store ─────────────────────────────────────────────────────────────────────


class RoutineStore:
    """Registre persistant des Routines et de leurs RoutineRun.

    Stocke en mémoire et sérialise dans un fichier JSON à chaque mutation.
    Les 200 derniers runs sont conservés (vieux runs silencieusement tronqués).
    """

    def __init__(self, path: Path = _STORE_PATH) -> None:
        self._path = path
        self._routines: dict[str, Routine] = {}
        self._runs: list[RoutineRun] = []
        self._load()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data: dict = json.loads(self._path.read_text())
            for r in data.get("routines", []):
                obj = Routine(
                    name=r["name"],
                    trigger=TriggerType(r["trigger"]),
                    action_prompt=r["action_prompt"],
                    target_channel=r.get("target_channel", "notification"),
                    concurrency_policy=ConcurrencyPolicy(
                        r.get("concurrency_policy", "skip_if_active")
                    ),
                    catch_up_policy=CatchUpPolicy(r.get("catch_up_policy", "skip_missed")),
                    enabled=r.get("enabled", True),
                    cron_expr=r.get("cron_expr"),
                    interval_seconds=r.get("interval_seconds"),
                )
                self._routines[obj.name] = obj
            for rd in data.get("runs", [])[-_RUNS_HISTORY:]:
                steps = [AuditStep(**s) for s in rd.pop("audit_log", [])]
                run = RoutineRun(
                    id=rd["id"],
                    routine_name=rd["routine_name"],
                    trigger_type=rd["trigger_type"],
                    started_at=rd["started_at"],
                    finished_at=rd.get("finished_at"),
                    status=RunStatus(rd.get("status", "pending")),
                    cost_usd=rd.get("cost_usd"),
                    result_summary=rd.get("result_summary"),
                )
                run.audit_log = steps
                self._runs.append(run)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"RoutineStore: échec du chargement : {exc}")

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data: dict = {
                "routines": [asdict(r) for r in self._routines.values()],
                "runs": [asdict(r) for r in self._runs[-_RUNS_HISTORY:]],
            }
            self._path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"RoutineStore: échec de la sauvegarde : {exc}")

    # ── CRUD Routines ─────────────────────────────────────────────────────────

    def register(self, routine: Routine) -> None:
        self._routines[routine.name] = routine
        self._save()

    def get_routine(self, name: str) -> Routine | None:
        return self._routines.get(name)

    def list_routines(self) -> list[Routine]:
        return list(self._routines.values())

    # ── Runs ──────────────────────────────────────────────────────────────────

    def create_run(self, routine: Routine) -> RoutineRun:
        """Crée et persiste un nouveau RoutineRun pour la routine."""
        run = RoutineRun(
            id=f"run_{uuid.uuid4().hex[:12]}",
            routine_name=routine.name,
            trigger_type=str(routine.trigger),
            started_at=datetime.now(UTC).isoformat(),
            status=RunStatus.PENDING,
        )
        run.add_step("created", f"Routine '{routine.name}' déclenchée")
        self._runs.append(run)
        self._save()
        logger.info(f"RoutineRun créé : {run.id} pour '{routine.name}'")
        return run

    def update_run(self, run: RoutineRun) -> None:
        """Persiste l'état courant d'un run existant."""
        self._save()

    def active_run_for(self, routine_name: str) -> RoutineRun | None:
        """Retourne le run PENDING/RUNNING pour cette routine, s'il existe."""
        for r in reversed(self._runs):
            if r.routine_name == routine_name and r.status in (
                RunStatus.RUNNING,
                RunStatus.PENDING,
            ):
                return r
        return None

    def last_finished_run(self, routine_name: str) -> RoutineRun | None:
        """Retourne le dernier run SUCCESS/FAILED pour cette routine."""
        for r in reversed(self._runs):
            if r.routine_name == routine_name and r.status in (
                RunStatus.SUCCESS,
                RunStatus.FAILED,
            ):
                return r
        return None

    def list_runs(
        self,
        routine_name: str | None = None,
        limit: int = 50,
    ) -> list[RoutineRun]:
        runs = [r for r in self._runs if routine_name is None or r.routine_name == routine_name]
        return list(reversed(runs[-limit:]))


# ── Fonctions de déclenchement (indépendantes du Scheduler, testables) ────────


async def fire_routine(
    routine: Routine,
    store: RoutineStore,
    broadcast: Callable[[dict], None],
    wake_engine: Callable[[], None] | None = None,
    *,
    catch_up: bool = False,
) -> RoutineRun | None:
    """Tente de déclencher un run en respectant les politiques configurées.

    Retourne le RoutineRun créé (ou coalesced), ou un run SKIPPED si la
    politique de concurrence l'impose.
    """
    active = store.active_run_for(routine.name)

    if active is not None:
        if routine.concurrency_policy == ConcurrencyPolicy.SKIP_IF_ACTIVE:
            skipped = store.create_run(routine)
            skipped.status = RunStatus.SKIPPED
            skipped.add_step(
                "skipped",
                f"Run actif {active.id} — politique skip_if_active",
            )
            skipped.finished_at = datetime.now(UTC).isoformat()
            store.update_run(skipped)
            logger.info(
                f"Routine '{routine.name}': skip (run actif={active.id}, "
                "concurrency=skip_if_active)"
            )
            return skipped

        if routine.concurrency_policy == ConcurrencyPolicy.COALESCE:
            active.add_step("coalesced", "Déclenchement fusionné dans le run actif")
            store.update_run(active)
            logger.info(f"Routine '{routine.name}': coalesced dans run actif {active.id}")
            return active

        # ALWAYS_ENQUEUE : on crée un nouveau run même si un autre tourne

    run = store.create_run(routine)
    run.status = RunStatus.RUNNING
    run.add_step(
        "started",
        "rattrapage (catch_up)" if catch_up else "déclenchement normal",
    )
    store.update_run(run)

    if wake_engine is not None:
        wake_engine()

    broadcast(
        {
            "type": "routine_triggered",
            "run_id": run.id,
            "routine": routine.name,
            "action_prompt": routine.action_prompt,
            "catch_up": catch_up,
        }
    )

    run.status = RunStatus.SUCCESS
    run.result_summary = f"Action dispatchée : {routine.action_prompt[:80]}"
    run.finished_at = datetime.now(UTC).isoformat()
    run.add_step("completed", run.result_summary or "")
    store.update_run(run)

    logger.info(
        f"Routine '{routine.name}': run {run.id} terminé (status={run.status}, catch_up={catch_up})"
    )
    return run


async def apply_catch_up(
    routine: Routine,
    store: RoutineStore,
    broadcast: Callable[[dict], None],
    wake_engine: Callable[[], None] | None = None,
) -> list[RoutineRun]:
    """Rejoue les runs manqués pendant une indisponibilité.

    Limité à ROUTINES_CATCH_UP_MAX runs (défaut 3) pour éviter les rafales.
    Ne s'applique qu'aux routines INTERVAL (le cron recalcule sa prochaine
    exécution directement depuis l'expression).
    """
    if routine.catch_up_policy == CatchUpPolicy.SKIP_MISSED:
        return []
    if routine.trigger != TriggerType.INTERVAL or not routine.interval_seconds:
        return []

    last_run = store.last_finished_run(routine.name)
    if last_run is None:
        return []

    interval = routine.interval_seconds
    last_time = datetime.fromisoformat(last_run.started_at)
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - last_time).total_seconds()
    missed = int(elapsed // interval) - 1  # -1 : on ne compte pas le run en cours

    if missed <= 0:
        return []

    count = min(missed, _CATCH_UP_MAX)
    logger.info(
        f"Routine '{routine.name}': {missed} runs manqués, "
        f"rattrapage de {count} (cap={_CATCH_UP_MAX})"
    )

    result: list[RoutineRun] = []
    for i in range(count):
        run = await fire_routine(routine, store, broadcast, wake_engine, catch_up=True)
        if run and run.status != RunStatus.SKIPPED:
            run.add_step("catch_up_index", f"Rattrapage {i + 1}/{count}")
            store.update_run(run)
            result.append(run)
    return result


# ── Parser cron minimal (pas de dépendance externe) ───────────────────────────


def next_cron_datetime(expr: str, after: datetime) -> datetime:
    """Calcule la prochaine exécution pour une expression cron 5-champs.

    Supporte les valeurs fixes et '*'.
    Exemples : "0 9 * * *" → 9h00 chaque jour, "30 * * * *" → :30 chaque heure.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expression cron invalide (5 champs requis) : {expr!r}")

    min_f, hour_f, dom_f, mon_f, dow_f = parts

    def _matches(field: str, value: int) -> bool:
        return field == "*" or int(field) == value

    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Cherche sur 366 jours maximum (525 600 minutes)
    for _ in range(525_601):
        if (
            _matches(mon_f, candidate.month)
            and _matches(dom_f, candidate.day)
            and _matches(dow_f, candidate.weekday())
            and _matches(hour_f, candidate.hour)
            and _matches(min_f, candidate.minute)
        ):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(f"Aucune prochaine exécution trouvée pour : {expr!r}")
