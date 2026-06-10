"""Modèles de données partagés inter-couches — CDC §A.1.3.

Ce module regroupe les schemas pydantic/dataclass utilisés par au moins
deux packages. Chaque section conserve la sémantique exacte des fichiers
d'origine (memory/schemas.py, agent/schemas.py, proactive/schemas.py) :
**aucune réécriture de logique** (§0 règle 5).

Les fichiers d'origine deviennent des ré-exports `from kernel.schemas
import ...` pour préserver les call-sites existants jusqu'à la Phase B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from jarvis.kernel.vocab import AccessLevel, AutonomyLevel

# ════════════════════════════════════════════════════════════════════════════
# Section 1 — Memory (ex-memory/schemas.py)
# ════════════════════════════════════════════════════════════════════════════
#
# Contrats de données Memory Kernel — structures pures, aucune logique
# (CDC évolution §3.5, §6.2).


class FactStatus(StrEnum):
    """Cycle de vie d'un fact (§3.5)."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONFLICTED = "conflicted"
    ARCHIVED = "archived"
    NEEDS_REVIEW = "needs_review"


class DecayPolicy(StrEnum):
    """Politique de décroissance de saillance au retrieval (§3.5, §6.6)."""

    NONE = "none"
    VERY_SLOW = "very_slow"
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"


class ObservationType(StrEnum):
    """Type d'observation sur un fact existant (§6.2 — fact_observations)."""

    CONFIRM = "confirm"
    WEAKEN = "weaken"
    CORRECT = "correct"


class RelationType(StrEnum):
    """Nature du lien entre deux facts (§6.2 — fact_relations)."""

    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    RELATED_TO = "related_to"


@dataclass
class Event:
    """Log immuable de tout ce qui arrive — on ne supprime jamais un event brut (§6.2)."""

    id: str
    type: str
    source: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    metadata_json: str | None = None


@dataclass
class Fact:
    """Claim atomique : une idée par fact (§6.2, §6.3).

    predicate ∈ PREDICATES et category ∈ CATEGORIES sont validés à l'ingestion (§3.1).
    Un fact hors vocabulaire reçoit status=NEEDS_REVIEW et n'entre pas en base principale.
    """

    id: str
    subject: str
    predicate: str  # ∈ PREDICATES — validé par l'ingestion
    object: str  # noqa: A003 — nom imposé par le schéma relationnel §6.2
    category: str  # ∈ CATEGORIES — validé par l'ingestion
    status: FactStatus = FactStatus.ACTIVE
    confidence: float = 0.55
    support_count: int = 1
    decay_policy: DecayPolicy = DecayPolicy.MEDIUM
    # PHASE 3 (changement de contrat PHASE 0 signalé) — importance pour le ranking
    # retrieval (§6.9, formule Generative Agents : importance × récence × pertinence × confidence).
    # Notée par le LLM à l'ingestion sur [0, 1] ; défaut 0.5 si non précisée.
    importance: float = 0.5
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_event_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_seen_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class FactObservation:
    """Renforcement ou correction d'un fact sans duplication (§6.2, §6.5)."""

    id: str
    fact_id: str
    event_id: str
    observation_type: ObservationType
    confidence_delta: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class FactRelation:
    """Lien typé entre deux facts (§6.2)."""

    id: str
    from_fact_id: str
    to_fact_id: str
    relation_type: RelationType
    created_at: datetime = field(default_factory=datetime.now)


# ════════════════════════════════════════════════════════════════════════════
# Section 2 — Agent / Mission Engine (ex-agent/schemas.py)
# ════════════════════════════════════════════════════════════════════════════


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    SKIPPED = "skipped"


class ProjectStatus(StrEnum):
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class Step:
    id: str
    title: str
    description: str
    status: StepStatus = StepStatus.PENDING
    requires_approval: bool = False
    output: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Champs PHASE 0 — contrat de vérification (§3.4)
    success_criterion: str = ""
    verification_command: str | None = None
    access_level: AccessLevel = AccessLevel.WRITE_LOCAL
    verified: bool = False
    verification_notes: str | None = None


@dataclass
class Project:
    id: str
    title: str
    mission: str
    status: ProjectStatus = ProjectStatus.PLANNING
    steps: list[Step] = field(default_factory=list)
    workspace_path: str = ""
    timeout_minutes: int = 30
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    llm_calls: int = 0
    files_created: list[str] = field(default_factory=list)
    requires_network: bool = False


@dataclass
class LogEntry:
    timestamp: datetime
    level: str  # "info" | "tool" | "error" | "approval"
    message: str
    step_id: str | None = None
    data: Any = None


def validate_step(step: Step) -> None:
    """Valide qu'un Step porte un success_criterion non vide. Lève ValueError sinon.

    À appeler à la validation du plan (orchestrateur), pas à la construction (Option A §3.4).
    Le défaut `""` n'existe que pour la compatibilité ascendante : un step sans critère
    réel (vide ou blancs) doit toujours être rejeté.
    """
    if not step.success_criterion.strip():
        raise ValueError(f"Step '{step.id}' n'a pas de success_criterion.")


# ════════════════════════════════════════════════════════════════════════════
# Section 3 — Proactive (ex-proactive/schemas.py)
# ════════════════════════════════════════════════════════════════════════════


class ItemType(StrEnum):
    EMAIL = "email"
    EVENT = "event"
    TASK = "task"
    NEWS = "news"
    MISSION = "mission"
    MEMORY = "memory"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ContextItem:
    """Un élément d'information collecté depuis une source."""

    type: ItemType
    title: str
    summary: str
    raw: str
    source: str
    timestamp: datetime
    priority: Priority = Priority.MEDIUM
    metadata: dict = field(default_factory=dict)


@dataclass
class CollectionResult:
    """Résultat d'une collecte complète (toutes sources)."""

    items: list[ContextItem]
    collected_at: datetime
    errors: dict[str, str] = field(default_factory=dict)

    def by_type(self, item_type: ItemType) -> list[ContextItem]:
        return [i for i in self.items if i.type == item_type]

    def high_priority(self) -> list[ContextItem]:
        return [i for i in self.items if i.priority == Priority.HIGH]


class InitiativeType(StrEnum):
    DRAFT_RESPONSE = "draft_response"
    REMINDER = "reminder"
    SUGGESTION = "suggestion"
    ALERT = "alert"
    AUTO_TASK = "auto_task"
    INFO = "info"


class ExecutionMode(StrEnum):
    AUTO = "auto"
    NOTIFY = "notify"
    VALIDATE = "validate"


@dataclass
class Initiative:
    """Initiative proactive — étendue PHASE 6 §10.1.

    Champs historiques (PHASE 2 proactive existante) conservés :
    type, title, context, reasoning, action, priority, execution_mode,
    draft_content, mission_description, status.

    Nouveaux champs §10.1 — défauts pour compat ascendante des JSONL legacy :
    - autonomy_level : 0-5 (cf. kernel.vocab.AutonomyLevel). Défaut SUGGEST (1).
    - permission_required : catégorie ApprovalConfig (ex. "agent_mission",
      "email_send"). Lue par le gate composite à l'exécution.
    - cost_max_usd : plafond budgétaire de l'initiative. None = pas de plafond
      explicite ; le BudgetGuard global s'applique de toute façon.
    - risk : tag humain libre ("low" | "medium" | "high"). Indicatif.
    - deadline : datetime au-delà de laquelle l'initiative expire/annule.
    - next_action : prochaine étape concrète (texte court, humain-lisible).
    - requires_validation : override explicite. Si True, ignore autonomy_level
      et force passage par validation humaine. CDC §10 : niveau 5 toujours True.
    """

    id: str
    type: InitiativeType
    title: str
    context: str
    reasoning: str
    action: str
    priority: Priority
    execution_mode: ExecutionMode
    created_at: datetime = field(default_factory=datetime.now)
    draft_content: str | None = None
    mission_description: str | None = None
    status: str = "pending"
    # PHASE 6 — champs gouvernance §10.1 (defaults pour compat JSONL legacy).
    autonomy_level: AutonomyLevel = AutonomyLevel.SUGGEST
    permission_required: str = "agent_mission"
    cost_max_usd: float | None = None
    risk: str = "low"
    deadline: datetime | None = None
    next_action: str = ""
    requires_validation: bool = False


def needs_human_validation(initiative: Initiative) -> bool:
    """Renvoie True si l'initiative DOIT passer par validation humaine.

    Règle CDC §10 : niveau 5 (EXTERNAL_ACTION = publier/payer/contacter/
    supprimer) exige TOUJOURS validation, même si requires_validation=False.
    Le flag requires_validation peut forcer plus bas en niveau si besoin.
    """
    if initiative.autonomy_level == AutonomyLevel.EXTERNAL_ACTION:
        return True
    return initiative.requires_validation
