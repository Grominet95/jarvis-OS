"""BudgetGuard — contrôle de budget multi-scope avec seuil d'alerte et hard-stop.

Scopes :
  "global"          → plafond mensuel global (lu depuis les fichiers tracking JSONL)
  "project:<id>"    → plafond par run de projet agent (accumulateur in-memory, seedé au démarrage)
  "run:<id>"        → suivi sans limite par défaut (extensible)

Patterns inspirés de Paperclip (MIT) — voir notices/budget-cost.md.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Literal

from loguru import logger

from jarvis.engine.tracking import UsageTracker
from jarvis.kernel.events import BudgetThresholdReached, EventBus
from jarvis.kernel.settings import Settings

BudgetStatus = Literal["ok", "warning", "hard_stop"]


class BudgetGuard:
    """Garde-fou budgétaire injecté dans le worker agentique.

    Phase C : `settings` et `tracker` sont injectés par le constructeur
    (auparavant `from config.settings import settings` en local et
    instanciation interne de `UsageTracker()` à chaque appel). Plus
    aucune instanciation interne, plus aucun import différé inter-couches.
    """

    def __init__(
        self,
        settings: Settings,
        tracker: UsageTracker,
        bus: EventBus | None = None,
    ) -> None:
        self._enabled = settings.budget_enabled
        self._monthly_usd = settings.budget_monthly_usd
        self._per_project = settings.budget_per_project_usd
        self._warn_ratio = settings.budget_warn_pct / 100.0
        self._tracker = tracker
        self._bus = bus
        self._lock = asyncio.Lock()

        # Accumulateurs in-memory (projet et run)
        self._project_spent: dict[str, float] = {}
        self._run_spent: dict[str, float] = {}

        # Scopes ayant déjà déclenché l'alerte warn (pour ne pas spammer)
        self._warned: set[str] = set()

        # Amorçage depuis l'historique du mois courant
        self._seed_from_history()

    # ── Amorçage ──────────────────────────────────────────────────────────────

    def _seed_from_history(self) -> None:
        """Recharge les dépenses mission du mois courant depuis les fichiers JSONL."""
        try:
            today = date.today()
            d = today.replace(day=1)
            while d <= today:
                for e in self._tracker._read_day(d):
                    ctx = e.get("context") or ""
                    if ctx.startswith("mission:"):
                        pid = ctx.split(":", 1)[1]
                        cost = e.get("cost_usd", 0.0)
                        self._project_spent[pid] = self._project_spent.get(pid, 0.0) + cost
                d += timedelta(days=1)
            logger.debug("BudgetGuard amorcé", projects=len(self._project_spent))
        except Exception as exc:
            logger.warning("BudgetGuard: impossible de charger l'historique", error=str(exc))

    # ── Lecture des dépenses ──────────────────────────────────────────────────

    def _global_spent(self) -> float:
        """Coût mensuel global lu depuis les fichiers JSONL (source de vérité)."""
        try:
            return self._tracker.get_monthly_totals()["cost_usd"]
        except Exception:
            return 0.0

    def _spent(self, scope: str) -> float:
        if scope == "global":
            return self._global_spent()
        if scope.startswith("project:"):
            return self._project_spent.get(scope[8:], 0.0)
        if scope.startswith("run:"):
            return self._run_spent.get(scope[4:], 0.0)
        return 0.0

    def _limit(self, scope: str) -> float:
        if scope == "global":
            return self._monthly_usd
        if scope.startswith("project:"):
            return self._per_project
        return float("inf")

    def _scope_status(self, scope: str, spent: float) -> BudgetStatus:
        limit = self._limit(scope)
        if limit == float("inf") or limit <= 0:
            return "ok"
        if spent >= limit:
            return "hard_stop"
        if spent >= limit * self._warn_ratio:
            return "warning"
        return "ok"

    # ── API publique ──────────────────────────────────────────────────────────

    async def reserve(self, scope: str, estimated_usd: float) -> bool:
        """Vérifie si on peut dépenser estimated_usd sur ce scope.

        Retourne False (hard-stop) si le budget est épuisé ou serait dépassé.
        Émet une notification warn si on approche du seuil.
        """
        if not self._enabled:
            return True

        async with self._lock:
            spent = self._spent(scope)
            limit = self._limit(scope)
            projected = spent + estimated_usd

            if limit != float("inf") and projected > limit:
                logger.warning(
                    "BudgetGuard hard-stop",
                    scope=scope,
                    spent=round(spent, 4),
                    limit=limit,
                    estimated=estimated_usd,
                )
                if self._bus is not None:
                    await self._bus.publish(
                        BudgetThresholdReached(
                            ratio=1.0,
                            provider="mission" if scope.startswith("project:") else "global",
                            scope=scope,
                        )
                    )
                return False

            # Alerte warn (une seule fois par scope par session)
            if self._scope_status(scope, projected) == "warning" and scope not in self._warned:
                self._warned.add(scope)
                if self._bus is not None:
                    await self._bus.publish(
                        BudgetThresholdReached(
                            ratio=projected / limit if limit > 0 else 0.0,
                            provider="mission" if scope.startswith("project:") else "global",
                            scope=scope,
                        )
                    )
                logger.info(
                    "BudgetGuard: alerte warn",
                    scope=scope,
                    pct=f"{projected / limit * 100:.1f}%",
                )

            return True

    def record(self, scope: str, actual_usd: float) -> None:
        """Enregistre une dépense réelle sur un scope (in-memory uniquement)."""
        if not self._enabled or actual_usd <= 0:
            return
        if scope.startswith("project:"):
            pid = scope[8:]
            self._project_spent[pid] = self._project_spent.get(pid, 0.0) + actual_usd
        elif scope.startswith("run:"):
            rid = scope[4:]
            self._run_spent[rid] = self._run_spent.get(rid, 0.0) + actual_usd
        # "global" : lu depuis disque, pas d'accumulation in-memory nécessaire

    def remaining(self, scope: str) -> float:
        """Budget restant pour ce scope (float('inf') si illimité)."""
        limit = self._limit(scope)
        if limit == float("inf"):
            return float("inf")
        return max(0.0, limit - self._spent(scope))

    def status(self) -> dict:
        """Résumé complet de l'état budgétaire."""
        global_spent = self._global_spent()
        limit_m = self._monthly_usd

        projects: dict[str, dict] = {}
        for pid, spent in self._project_spent.items():
            scope = f"project:{pid}"
            projects[pid] = {
                "spent_usd": round(spent, 6),
                "limit_usd": self._per_project,
                "remaining_usd": round(self.remaining(scope), 6),
                "status": self._scope_status(scope, spent),
            }

        return {
            "enabled": self._enabled,
            "global": {
                "spent_usd": round(global_spent, 6),
                "limit_usd": limit_m,
                "remaining_usd": round(max(0.0, limit_m - global_spent), 6),
                "utilization_pct": round(global_spent / limit_m * 100, 2) if limit_m > 0 else 0.0,
                "status": self._scope_status("global", global_spent),
            },
            "projects": projects,
        }
