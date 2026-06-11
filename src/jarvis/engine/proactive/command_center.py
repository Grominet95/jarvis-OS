"""Command Center (CDC §10.2) — vue unifiée des workstreams en cours.

Jarvis ne "fait pas des trucs" : il gère des WORKSTREAMS. Le Command Center
agrège en lecture seule :
  - les initiatives proactives (InitiativeStore JSONL)
  - les missions agent en cours (ProjectStore)
  - le budget consommé / restant (BudgetGuard)
  - les skills installées et leur usage récent (SkillLifecycle)
  - le statut Capability Engine (skills candidates en attente)

Pas de nouveau stockage. Ce module est un AGRÉGATEUR : il lit ce qui existe
déjà dans les phases précédentes et le présente comme une vue cohérente.
Les actions (approve/reject/promote/etc.) restent sur les endpoints
spécialisés des phases respectives — le Command Center ne court-circuite RIEN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from jarvis.engine.budget import BudgetGuard
from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.mission.schemas import StepStatus
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.kernel.contracts import SkillLifecycle
from jarvis.kernel.schemas import SkillStatus


@dataclass
class InitiativeSummary:
    """Vue résumée d'une initiative pour le Command Center."""

    id: str
    title: str
    type: str
    autonomy_level: int
    permission_required: str
    cost_max_usd: float | None
    risk: str
    deadline: str | None
    next_action: str
    requires_validation: bool
    execution_mode: str
    status: str
    priority: str
    created_at: str


@dataclass
class MissionSummary:
    """Vue résumée d'une mission agent (Project)."""

    id: str
    title: str
    status: str
    steps_total: int
    steps_done: int
    steps_failed: int
    llm_calls: int
    created_at: str
    started_at: str | None
    completed_at: str | None


@dataclass
class BudgetSummary:
    """Vue du budget global + par scope."""

    enabled: bool = False
    global_spent_usd: float = 0.0
    global_limit_usd: float = 0.0
    global_status: str = "ok"
    global_utilization_pct: float = 0.0
    projects: list[dict] = field(default_factory=list)


@dataclass
class SkillSummary:
    """Vue résumée du lifecycle des skills."""

    by_status: dict[str, int] = field(default_factory=dict)
    candidates_pending_review: list[dict] = field(default_factory=list)
    stale_candidates: list[dict] = field(default_factory=list)


@dataclass
class CommandCenterSnapshot:
    """Snapshot complet de l'état Jarvis pour le Command Center."""

    captured_at: str
    initiatives: list[InitiativeSummary] = field(default_factory=list)
    missions: list[MissionSummary] = field(default_factory=list)
    budget: BudgetSummary = field(default_factory=BudgetSummary)
    skills: SkillSummary = field(default_factory=SkillSummary)
    heartbeat_seconds: float | None = None  # temps depuis dernière activité agent


class CommandCenter:
    """Agrégateur lecture-seule des workstreams Jarvis."""

    def __init__(
        self,
        initiative_store: InitiativeStore,
        project_store: ProjectStore,
        budget_guard: BudgetGuard | None,
        skill_lifecycle: SkillLifecycle | None,
    ) -> None:
        self._initiatives = initiative_store
        self._projects = project_store
        self._budget = budget_guard
        self._skills = skill_lifecycle
        self._heartbeat_at: datetime | None = None

    def signal_heartbeat(self) -> None:
        """Appelé quand une action proactive/agent se produit (pour heartbeat)."""
        self._heartbeat_at = datetime.now()

    # ── Snapshot complet ──────────────────────────────────────────────────────

    def snapshot(self, days: int = 7) -> CommandCenterSnapshot:
        """Produit un snapshot agrégé de l'état actuel."""
        snap = CommandCenterSnapshot(captured_at=datetime.now().isoformat())

        # Initiatives — pending + récentes (validées/rejetées) sur N jours
        try:
            recent = self._initiatives.list_recent(days=days)
        except Exception as exc:  # noqa: BLE001 — un store défaillant n'arrête pas la vue
            logger.warning("CommandCenter: initiatives load échec", error=str(exc))
            recent = []
        snap.initiatives = [self._initiative_to_summary(i) for i in recent]

        # Missions — projects.list_projects() trie déjà par date desc
        try:
            projects = self._projects.list_projects()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CommandCenter: missions load échec", error=str(exc))
            projects = []
        snap.missions = [self._project_to_summary(p) for p in projects[:20]]

        # Budget
        snap.budget = self._budget_summary()

        # Skills
        snap.skills = self._skills_summary()

        # Heartbeat
        if self._heartbeat_at:
            snap.heartbeat_seconds = (datetime.now() - self._heartbeat_at).total_seconds()

        return snap

    # ── Helpers de mapping ────────────────────────────────────────────────────

    @staticmethod
    def _initiative_to_summary(i: object) -> InitiativeSummary:
        # Imports tardifs pour éviter la circularité
        return InitiativeSummary(
            id=i.id,  # type: ignore[attr-defined]
            title=i.title,  # type: ignore[attr-defined]
            type=str(i.type),  # type: ignore[attr-defined]
            autonomy_level=int(i.autonomy_level),  # type: ignore[attr-defined]
            permission_required=i.permission_required,  # type: ignore[attr-defined]
            cost_max_usd=i.cost_max_usd,  # type: ignore[attr-defined]
            risk=i.risk,  # type: ignore[attr-defined]
            deadline=i.deadline.isoformat() if i.deadline else None,  # type: ignore[attr-defined]
            next_action=i.next_action,  # type: ignore[attr-defined]
            requires_validation=i.requires_validation,  # type: ignore[attr-defined]
            execution_mode=str(i.execution_mode),  # type: ignore[attr-defined]
            status=i.status,  # type: ignore[attr-defined]
            priority=str(i.priority),  # type: ignore[attr-defined]
            created_at=i.created_at.isoformat(),  # type: ignore[attr-defined]
        )

    @staticmethod
    def _project_to_summary(p: object) -> MissionSummary:

        steps = p.steps  # type: ignore[attr-defined]
        return MissionSummary(
            id=p.id,  # type: ignore[attr-defined]
            title=p.title,  # type: ignore[attr-defined]
            status=str(p.status),  # type: ignore[attr-defined]
            steps_total=len(steps),
            steps_done=sum(1 for s in steps if s.status == StepStatus.DONE),
            steps_failed=sum(1 for s in steps if s.status == StepStatus.FAILED),
            llm_calls=p.llm_calls,  # type: ignore[attr-defined]
            created_at=p.created_at.isoformat(),  # type: ignore[attr-defined]
            started_at=p.started_at.isoformat() if p.started_at else None,  # type: ignore[attr-defined]
            completed_at=(
                p.completed_at.isoformat() if p.completed_at else None  # type: ignore[attr-defined]
            ),
        )

    def _budget_summary(self) -> BudgetSummary:
        if self._budget is None:
            return BudgetSummary(enabled=False)
        try:
            status = self._budget.status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CommandCenter: budget.status() échec", error=str(exc))
            return BudgetSummary(enabled=False)
        global_block = status.get("global", {})
        projects = [{"id": k, **v} for k, v in (status.get("projects") or {}).items()]
        return BudgetSummary(
            enabled=status.get("enabled", False),
            global_spent_usd=global_block.get("spent_usd", 0.0),
            global_limit_usd=global_block.get("limit_usd", 0.0),
            global_status=global_block.get("status", "ok"),
            global_utilization_pct=global_block.get("utilization_pct", 0.0),
            projects=projects,
        )

    def _skills_summary(self) -> SkillSummary:
        if self._skills is None:
            return SkillSummary()

        by_status: dict[str, int] = {}
        for st in SkillStatus:
            try:
                by_status[st.value] = self._skills.count_by_status(st)
            except Exception:  # noqa: BLE001
                by_status[st.value] = 0
        # Candidates en attente de validation humaine (SANDBOXED_PASS)
        try:
            pending = self._skills.list_by_status(SkillStatus.SANDBOXED_PASS)
        except Exception:  # noqa: BLE001
            pending = []
        try:
            stale = self._skills.list_by_status(SkillStatus.STALE)
        except Exception:  # noqa: BLE001
            stale = []
        return SkillSummary(
            by_status=by_status,
            candidates_pending_review=[
                {"name": r.name, "created_at": r.created_at.isoformat()} for r in pending
            ],
            stale_candidates=[
                {
                    "name": r.name,
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                }
                for r in stale
            ],
        )


__all__ = [
    "BudgetSummary",
    "CommandCenter",
    "CommandCenterSnapshot",
    "InitiativeSummary",
    "MissionSummary",
    "SkillSummary",
]
