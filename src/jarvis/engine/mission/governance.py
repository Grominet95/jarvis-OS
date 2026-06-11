"""Gate composite à 3 axes (CDC §9, option α PHASE 1).

Compose risque technique (AccessLevel) + catégorie d'approbation (ApprovalConfig)
+ budget (BudgetGuard). Le plus restrictif gagne. Aucun appel bloquant ici :
gate() est PUREMENT décisionnel. Le caller (worker, orchestrator) exécute
l'approbation effective selon le canal approprié.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from loguru import logger

from jarvis.engine.audit import AuditEntry, AuditLog
from jarvis.engine.budget import BudgetGuard
from jarvis.engine.vocab import AUTO_MAX_LEVEL, AccessLevel
from jarvis.kernel.approvals import ApprovalConfig, ApprovalMode


class GateDecision(StrEnum):
    """Sortie du gate composite.

    AUTO     → exécution sans validation humaine.
    DRY_RUN  → afficher le diff/la requête, ne pas exécuter (niveau intermédiaire).
    APPROVAL → demander à l'humain (peut être accordée).
    REFUSED  → refus déterministe (catégorie NEVER ou budget hard_stop).
               Aucune approbation humaine ne peut sauver l'action.
    """

    AUTO = "auto"
    DRY_RUN = "dry_run"
    APPROVAL = "approval"
    REFUSED = "refused"


# Ordre de restriction croissante — le plus grand gagne.
_DECISION_RANK: dict[GateDecision, int] = {
    GateDecision.AUTO: 0,
    GateDecision.DRY_RUN: 1,
    GateDecision.APPROVAL: 2,
    GateDecision.REFUSED: 3,
}


@dataclass
class GateContext:
    """Entrées au gate composite (§9)."""

    access_level: AccessLevel
    action_category: str  # ex. "agent_mission", "file_write", "email_send"
    estimated_cost_usd: float = 0.0
    budget_scope: str = "global"  # "global" | "project:<id>" | "run:<id>"
    dry_run_available: bool = False
    description: str = ""


class Governance:
    """Pilote du gate composite. Une instance par projet OU globale au choix."""

    def __init__(
        self,
        approval_config: ApprovalConfig,
        budget_guard: BudgetGuard | None,
        audit_log: AuditLog,
    ) -> None:
        self._approval_config = approval_config
        self._budget = budget_guard
        self._audit = audit_log

    # ── API publique ──────────────────────────────────────────────────────────

    def gate(self, ctx: GateContext, context_id: str = "") -> GateDecision:
        """Renvoie la décision composite. Trace systématiquement dans l'audit."""
        risk = self._risk_axis(ctx)
        category = self._category_axis(ctx)
        budget, budget_status = self._budget_axis(ctx)

        # Le plus restrictif gagne (OU logique côté refus/demande).
        decision = max(
            (risk, category, budget),
            key=lambda d: _DECISION_RANK[d],
        )

        self._audit.append(
            AuditEntry(
                timestamp=datetime.now(),
                decision=decision.value,
                context_id=context_id,
                access_level=int(ctx.access_level),
                action_category=ctx.action_category,
                estimated_cost_usd=ctx.estimated_cost_usd,
                risk_decision=risk.value,
                category_decision=category.value,
                budget_decision=budget.value,
                budget_status=budget_status,
                extra={"description": ctx.description[:200]} if ctx.description else {},
            )
        )

        if decision != GateDecision.AUTO:
            logger.info(
                "Gate decision",
                ctx=context_id,
                decision=decision.value,
                risk=risk.value,
                cat=category.value,
                budget=budget.value,
            )
        return decision

    # ── Axe 1 — risque technique (AccessLevel) ────────────────────────────────

    def _risk_axis(self, ctx: GateContext) -> GateDecision:
        # MODIFY_CORE et INSTALL_PACKAGE → toujours approval (§9).
        if ctx.access_level in (AccessLevel.INSTALL_PACKAGE, AccessLevel.MODIFY_CORE):
            return GateDecision.APPROVAL
        if ctx.access_level <= AUTO_MAX_LEVEL:
            return GateDecision.AUTO
        # Niveau intermédiaire (NETWORK) → dry_run si dispo, sinon approval.
        if ctx.dry_run_available:
            return GateDecision.DRY_RUN
        return GateDecision.APPROVAL

    # ── Axe 2 — catégorie d'approbation (ApprovalConfig) ─────────────────────

    def _category_axis(self, ctx: GateContext) -> GateDecision:
        # Catégorie inconnue → comportement par défaut conservateur : ASK.
        mode: ApprovalMode = getattr(self._approval_config, ctx.action_category, ApprovalMode.ASK)
        if mode == ApprovalMode.ALWAYS:
            return GateDecision.AUTO
        if mode == ApprovalMode.NEVER:
            return GateDecision.REFUSED
        return GateDecision.APPROVAL  # ASK

    # ── Axe 3 — budget (BudgetGuard) ──────────────────────────────────────────

    def _budget_axis(self, ctx: GateContext) -> tuple[GateDecision, str | None]:
        # Budget désactivé ou absent → axe neutre.
        if self._budget is None or not self._budget._enabled:
            return GateDecision.AUTO, None

        scope = ctx.budget_scope
        remaining = self._budget.remaining(scope)
        if remaining == float("inf"):
            return GateDecision.AUTO, "unlimited"
        if remaining < ctx.estimated_cost_usd:
            return GateDecision.REFUSED, "hard_stop"
        # Marge confortable ou warning : on autorise (le warning est tracé par BudgetGuard
        # lors de la réservation effective).
        return GateDecision.AUTO, "ok"
