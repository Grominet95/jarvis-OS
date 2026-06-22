# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests PHASE 0 — contrat de schémas partagés (§3).

Couvre :
- Vocabulaires fermés (§3.1)
- AccessLevel / AUTO_MAX_LEVEL (§3.2)
- AutonomyLevel (§3.3)
- Extension Step (§3.4) + validate_step()
- Types mémoire Event, Fact, FactObservation, FactRelation (§3.5 / §6.2)
- Round-trip JSON pour chaque type
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime

import pytest

from jarvis.engine.mission.schemas import Step, StepStatus, validate_step
from jarvis.engine.vocab import (
    AUTO_MAX_LEVEL,
    CATEGORIES,
    PREDICATES,
    AccessLevel,
    AutonomyLevel,
)
from jarvis.providers.memory.schemas import (
    DecayPolicy,
    Event,
    Fact,
    FactObservation,
    FactRelation,
    FactStatus,
    ObservationType,
    RelationType,
)

# ── Helpers de sérialisation ──────────────────────────────────────────────────

_ISO = datetime.fromisoformat


def _dt_to_str(d: dict) -> dict:
    """Convertit les datetime en ISO string dans un dict aplati."""
    result = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _roundtrip_json(obj: object) -> str:
    """Sérialise un dataclass en JSON (datetime → ISO string)."""
    return json.dumps(dataclasses.asdict(obj), default=str)  # type: ignore[call-overload]


# ── 1. Vocabulaires fermés (§3.1) ─────────────────────────────────────────────


def test_predicates_count() -> None:
    assert len(PREDICATES) == 16


def test_predicates_contenu_exact() -> None:
    attendus = {
        "is",
        "has",
        "prefers",
        "dislikes",
        "uses",
        "works_on",
        "targets",
        "plans",
        "believes",
        "needs",
        "struggles_with",
        "decided",
        "changed",
        "values",
        "communicates_as",
        "requires_validation_for",
    }
    assert PREDICATES == attendus


def test_categories_count() -> None:
    assert len(CATEGORIES) == 14


def test_categories_contenu_exact() -> None:
    attendus = {
        "identity",
        "preference",
        "project",
        "goal",
        "habit",
        "constraint",
        "belief",
        "relationship",
        "tool",
        "persona",
        "decision",
        "health_fitness",
        "work_style",
        "memory_correction",
    }
    assert CATEGORIES == attendus


def test_predicate_invalide_hors_vocabulaire() -> None:
    """Un prédicat libre ne doit pas être dans le vocabulaire."""
    for terme in ("vise", "veut", "target", "like", "aime"):
        assert terme not in PREDICATES, f"'{terme}' ne devrait pas être dans PREDICATES"


def test_category_invalide_hors_vocabulaire() -> None:
    for terme in ("emotion", "sport", "finances", "random"):
        assert terme not in CATEGORIES, f"'{terme}' ne devrait pas être dans CATEGORIES"


# ── 2. AccessLevel (§3.2) ─────────────────────────────────────────────────────


def test_access_level_valeurs() -> None:
    assert AccessLevel.READ_ONLY == 0
    assert AccessLevel.WRITE_LOCAL == 1
    assert AccessLevel.EXECUTE_CODE == 2
    assert AccessLevel.NETWORK == 3
    assert AccessLevel.INSTALL_PACKAGE == 4
    assert AccessLevel.MODIFY_CORE == 5


def test_access_level_ordre_croissant() -> None:
    assert AccessLevel.READ_ONLY < AccessLevel.WRITE_LOCAL < AccessLevel.EXECUTE_CODE
    assert AccessLevel.EXECUTE_CODE < AccessLevel.NETWORK < AccessLevel.INSTALL_PACKAGE
    assert AccessLevel.INSTALL_PACKAGE < AccessLevel.MODIFY_CORE


def test_auto_max_level_est_execute_code() -> None:
    assert AUTO_MAX_LEVEL == AccessLevel.EXECUTE_CODE


def test_auto_max_level_comparaison() -> None:
    """Tout niveau ≤ AUTO_MAX_LEVEL peut tourner sans validation humaine."""
    assert AccessLevel.READ_ONLY <= AUTO_MAX_LEVEL
    assert AccessLevel.WRITE_LOCAL <= AUTO_MAX_LEVEL
    assert AccessLevel.EXECUTE_CODE <= AUTO_MAX_LEVEL
    assert AccessLevel.NETWORK > AUTO_MAX_LEVEL
    assert AccessLevel.INSTALL_PACKAGE > AUTO_MAX_LEVEL
    assert AccessLevel.MODIFY_CORE > AUTO_MAX_LEVEL


# ── 3. AutonomyLevel (§3.3) ───────────────────────────────────────────────────


def test_autonomy_level_valeurs() -> None:
    assert AutonomyLevel.RESPOND_ONLY == 0
    assert AutonomyLevel.SUGGEST == 1
    assert AutonomyLevel.DRAFT == 2
    assert AutonomyLevel.SANDBOX == 3
    assert AutonomyLevel.MODIFY_PROJECT == 4
    assert AutonomyLevel.EXTERNAL_ACTION == 5


def test_autonomy_level_ordre_croissant() -> None:
    niveaux = list(AutonomyLevel)
    for i in range(len(niveaux) - 1):
        assert niveaux[i] < niveaux[i + 1]


# ── 4. Extension Step (§3.4) ──────────────────────────────────────────────────


def test_step_nouveaux_champs_defaults() -> None:
    step = Step(id="s1", title="T", description="D")
    assert step.success_criterion == ""
    assert step.verification_command is None
    assert step.access_level == AccessLevel.WRITE_LOCAL
    assert step.verified is False
    assert step.verification_notes is None


def test_step_champs_existants_inchanges() -> None:
    """Les champs antérieurs au CDC restent présents et fonctionnels."""
    step = Step(id="s1", title="T", description="D", status=StepStatus.RUNNING)
    assert step.status == StepStatus.RUNNING
    assert step.requires_approval is False
    assert step.output is None
    assert step.error is None


def test_step_avec_criterion_valide() -> None:
    step = Step(
        id="s1",
        title="T",
        description="D",
        success_criterion="Le fichier output.csv contient > 0 lignes.",
    )
    validate_step(step)  # ne doit pas lever


def test_step_sans_criterion_rejete() -> None:
    """Critère absent (défaut ``) → rejet."""
    step = Step(id="s1", title="T", description="D")
    with pytest.raises(ValueError, match="success_criterion"):
        validate_step(step)


def test_step_criterion_chaine_vide_rejete() -> None:
    """Critère explicitement vide → rejet."""
    step = Step(id="s2", title="T", description="D", success_criterion="")
    with pytest.raises(ValueError, match="success_criterion"):
        validate_step(step)


def test_step_criterion_blancs_seuls_rejete() -> None:
    """Critère uniquement composé d'espaces/tabs/newlines → rejet."""
    for blanc in ("   ", "\t", "\n", "  \t\n  "):
        step = Step(id="s3", title="T", description="D", success_criterion=blanc)
        with pytest.raises(ValueError, match="success_criterion"):
            validate_step(step)


def test_step_access_level_personnalise() -> None:
    step = Step(
        id="s1",
        title="T",
        description="D",
        success_criterion="Done",
        access_level=AccessLevel.NETWORK,
    )
    assert step.access_level == AccessLevel.NETWORK
    assert step.access_level > AUTO_MAX_LEVEL


# ── 5. Round-trip JSON — Event (§3.5 / §6.2) ─────────────────────────────────

_NOW = datetime(2026, 6, 1, 12, 0, 0)


def test_event_roundtrip() -> None:
    evt = Event(
        id="evt_001",
        type="mission_lesson",
        source="worker_agent",
        content="Étape 3 échouée : timeout Docker.",
        created_at=_NOW,
        metadata_json='{"project_id": "proj_abc"}',
    )
    raw = _roundtrip_json(evt)
    d = json.loads(raw)

    evt2 = Event(
        id=d["id"],
        type=d["type"],
        source=d["source"],
        content=d["content"],
        created_at=_ISO(d["created_at"]),
        metadata_json=d.get("metadata_json"),
    )

    assert evt.id == evt2.id
    assert evt.type == evt2.type
    assert evt.source == evt2.source
    assert evt.content == evt2.content
    assert evt.created_at == evt2.created_at
    assert evt.metadata_json == evt2.metadata_json


# ── 6. Round-trip JSON — Fact (§3.5 / §6.2) ──────────────────────────────────


def test_fact_roundtrip() -> None:
    fact = Fact(
        id="fact_001",
        subject="Barth",
        predicate="prefers",
        object="Python",
        category="tool",
        status=FactStatus.ACTIVE,
        confidence=0.75,
        support_count=2,
        decay_policy=DecayPolicy.SLOW,
        importance=0.7,
        valid_from=_NOW,
        valid_to=None,
        source_event_id="evt_001",
        created_at=_NOW,
        last_seen_at=_NOW,
        updated_at=_NOW,
    )
    raw = _roundtrip_json(fact)
    d = json.loads(raw)

    fact2 = Fact(
        id=d["id"],
        subject=d["subject"],
        predicate=d["predicate"],
        object=d["object"],
        category=d["category"],
        status=FactStatus(d["status"]),
        confidence=d["confidence"],
        support_count=d["support_count"],
        decay_policy=DecayPolicy(d["decay_policy"]),
        importance=d["importance"],
        valid_from=_ISO(d["valid_from"]) if d.get("valid_from") else None,
        valid_to=_ISO(d["valid_to"]) if d.get("valid_to") else None,
        source_event_id=d.get("source_event_id"),
        created_at=_ISO(d["created_at"]),
        last_seen_at=_ISO(d["last_seen_at"]),
        updated_at=_ISO(d["updated_at"]),
    )

    assert fact.id == fact2.id
    assert fact.predicate == fact2.predicate
    assert fact.object == fact2.object
    assert fact.category == fact2.category
    assert fact.status == fact2.status
    assert fact.confidence == fact2.confidence
    assert fact.support_count == fact2.support_count
    assert fact.decay_policy == fact2.decay_policy
    assert fact.importance == fact2.importance
    assert fact.valid_from == fact2.valid_from
    assert fact.valid_to == fact2.valid_to
    assert fact.source_event_id == fact2.source_event_id
    assert fact.created_at == fact2.created_at


def test_fact_predicate_hors_vocab_non_bloque_construction_mais_detectable() -> None:
    """Un Fact se construit avec n'importe quel prédicat (structures pures).

    C'est l'ingestion (PHASE 3) qui valide et met status=NEEDS_REVIEW.
    Ce test vérifie que le prédicat est bien stocké et que le vocabulaire
    permet de le détecter comme invalide.
    """
    fact = Fact(
        id="fact_bad",
        subject="Barth",
        predicate="vise",  # hors vocabulaire
        object="sub-3h",
        category="goal",
    )
    assert fact.predicate not in PREDICATES
    # Comportement attendu à l'ingestion : status mis à NEEDS_REVIEW
    fact.status = FactStatus.NEEDS_REVIEW
    assert fact.status == FactStatus.NEEDS_REVIEW


def test_fact_category_hors_vocab_non_bloque_construction_mais_detectable() -> None:
    fact = Fact(
        id="fact_bad_cat",
        subject="Barth",
        predicate="prefers",
        object="café",
        category="boisson",  # hors vocabulaire
    )
    assert fact.category not in CATEGORIES


# ── 7. Round-trip JSON — FactObservation (§6.2) ───────────────────────────────


def test_fact_observation_roundtrip() -> None:
    obs = FactObservation(
        id="obs_001",
        fact_id="fact_001",
        event_id="evt_002",
        observation_type=ObservationType.CONFIRM,
        confidence_delta=0.05,
        created_at=_NOW,
    )
    raw = _roundtrip_json(obs)
    d = json.loads(raw)

    obs2 = FactObservation(
        id=d["id"],
        fact_id=d["fact_id"],
        event_id=d["event_id"],
        observation_type=ObservationType(d["observation_type"]),
        confidence_delta=d["confidence_delta"],
        created_at=_ISO(d["created_at"]),
    )

    assert obs.id == obs2.id
    assert obs.fact_id == obs2.fact_id
    assert obs.observation_type == obs2.observation_type
    assert obs.confidence_delta == obs2.confidence_delta
    assert obs.created_at == obs2.created_at


# ── 8. Round-trip JSON — FactRelation (§6.2) ──────────────────────────────────


def test_fact_relation_roundtrip() -> None:
    rel = FactRelation(
        id="rel_001",
        from_fact_id="fact_002",
        to_fact_id="fact_001",
        relation_type=RelationType.SUPERSEDES,
        created_at=_NOW,
    )
    raw = _roundtrip_json(rel)
    d = json.loads(raw)

    rel2 = FactRelation(
        id=d["id"],
        from_fact_id=d["from_fact_id"],
        to_fact_id=d["to_fact_id"],
        relation_type=RelationType(d["relation_type"]),
        created_at=_ISO(d["created_at"]),
    )

    assert rel.id == rel2.id
    assert rel.from_fact_id == rel2.from_fact_id
    assert rel.to_fact_id == rel2.to_fact_id
    assert rel.relation_type == rel2.relation_type
    assert rel.created_at == rel2.created_at


# ── 9. Enums complets ─────────────────────────────────────────────────────────


def test_fact_status_valeurs_completes() -> None:
    valeurs = {s.value for s in FactStatus}
    assert valeurs == {"active", "superseded", "conflicted", "archived", "needs_review"}


def test_decay_policy_valeurs_completes() -> None:
    valeurs = {d.value for d in DecayPolicy}
    assert valeurs == {"none", "very_slow", "slow", "medium", "fast"}


def test_observation_type_valeurs_completes() -> None:
    valeurs = {o.value for o in ObservationType}
    assert valeurs == {"confirm", "weaken", "correct"}


def test_relation_type_valeurs_completes() -> None:
    valeurs = {r.value for r in RelationType}
    assert valeurs == {"supersedes", "contradicts", "supports", "related_to"}
