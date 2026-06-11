"""Tests du Memory Kernel (CDC §6.1–§6.2) — schéma, CRUD, FTS5, atomicité, correction humaine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jarvis.providers.memory.kernel import MemoryKernel, normalize
from jarvis.providers.memory.schemas import (
    DecayPolicy,
    Fact,
    FactStatus,
    ObservationType,
    RelationType,
)


def _make_fact(
    subject: str = "barth",
    predicate: str = "prefers",
    obj: str = "python",
    category: str = "tool",
    status: FactStatus = FactStatus.ACTIVE,
    confidence: float = 0.75,
    importance: float = 0.6,
) -> Fact:
    now = datetime.now()
    return Fact(
        id="",  # set by caller
        subject=subject,
        predicate=predicate,
        object=obj,
        category=category,
        status=status,
        confidence=confidence,
        support_count=1,
        decay_policy=DecayPolicy.MEDIUM,
        importance=importance,
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )


# ── Init / Schema ─────────────────────────────────────────────────────────────


def test_kernel_init_cree_la_base(tmp_path: Path) -> None:
    db_path = tmp_path / "deep" / "jarvis_memory.db"
    k = MemoryKernel(db_path)
    assert db_path.exists()
    assert k.db_path == db_path
    # Tables vides
    assert k.count_events() == 0
    assert k.count_facts() == 0


def test_kernel_idempotent_init(tmp_path: Path) -> None:
    """Réinstancier sur le même fichier ne casse pas les données."""
    k1 = MemoryKernel(tmp_path / "m.db")
    k1.log_event("test", "src", "hello")
    k2 = MemoryKernel(tmp_path / "m.db")
    assert k2.count_events() == 1


def test_normalize() -> None:
    assert normalize("  BARTH  ") == "barth"
    assert normalize("Python") == "python"


# ── Events ────────────────────────────────────────────────────────────────────


def test_event_log_immuable(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    evt = k.log_event("exchange", "voice", "Barth dit qu'il vise sub-3h")
    assert evt.id.startswith("evt_")
    assert evt.type == "exchange"
    assert evt.metadata_json is None

    fetched = k.get_event(evt.id)
    assert fetched is not None
    assert fetched.content == evt.content


def test_event_avec_metadata(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    evt = k.log_event("exchange", "voice", "content", metadata={"session_id": "abc", "score": 0.9})
    fetched = k.get_event(evt.id)
    assert fetched is not None
    assert fetched.metadata_json is not None
    assert "abc" in fetched.metadata_json
    assert "0.9" in fetched.metadata_json


# ── Facts ─────────────────────────────────────────────────────────────────────


def test_insert_et_get_fact(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    fact = _make_fact()
    fact.id = "fact_test"
    k.insert_fact(fact)

    fetched = k.get_fact("fact_test")
    assert fetched is not None
    assert fetched.subject == "barth"
    assert fetched.confidence == 0.75
    assert fetched.importance == 0.6


def test_find_active_match_meme_triplet(tmp_path: Path) -> None:
    """find_active_match retrouve un fact ACTIF sur (subject, predicate, category)."""
    k = MemoryKernel(tmp_path / "m.db")
    fact = _make_fact(subject="Barth", predicate="prefers", obj="python", category="tool")
    fact.id = "fact_1"
    fact.subject = normalize(fact.subject)
    fact.predicate = normalize(fact.predicate)
    fact.category = normalize(fact.category)
    k.insert_fact(fact)

    match = k.find_active_match("Barth", "prefers", "tool")
    assert match is not None
    assert match.id == "fact_1"

    # Différent predicate → pas de match
    assert k.find_active_match("Barth", "dislikes", "tool") is None
    # Différent subject → pas de match
    assert k.find_active_match("Alice", "prefers", "tool") is None


def test_find_active_ignore_superseded(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    fact = _make_fact(status=FactStatus.SUPERSEDED)
    fact.id = "fact_s"
    k.insert_fact(fact)
    assert k.find_active_match("barth", "prefers", "tool") is None


def test_update_fact_change_status_et_reindex_fts(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    fact = _make_fact()
    fact.id = "fact_up"
    k.insert_fact(fact)
    fact.status = FactStatus.SUPERSEDED
    fact.confidence = 0.4
    k.update_fact(fact)

    fetched = k.get_fact("fact_up")
    assert fetched is not None
    assert fetched.status == FactStatus.SUPERSEDED
    assert fetched.confidence == 0.4


def test_count_facts_par_status(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    for i in range(3):
        f = _make_fact()
        f.id = f"a{i}"
        k.insert_fact(f)
    f = _make_fact(status=FactStatus.NEEDS_REVIEW)
    f.id = "nr"
    k.insert_fact(f)

    assert k.count_facts() == 4
    assert k.count_facts(FactStatus.ACTIVE) == 3
    assert k.count_facts(FactStatus.NEEDS_REVIEW) == 1


def test_list_by_category(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    f1 = _make_fact(category="tool")
    f1.id = "t1"
    f2 = _make_fact(category="preference")
    f2.id = "p1"
    k.insert_fact(f1)
    k.insert_fact(f2)
    tools = k.list_facts_by_category("tool")
    assert len(tools) == 1
    assert tools[0].id == "t1"


# ── Observations & Relations ──────────────────────────────────────────────────


def test_record_observation_persiste(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    evt = k.log_event("exchange", "voice", "hello")
    fact = _make_fact()
    fact.id = "fact_obs"
    fact.source_event_id = evt.id
    k.insert_fact(fact)

    obs = k.record_observation(
        fact_id=fact.id,
        event_id=evt.id,
        observation_type=ObservationType.CONFIRM,
        confidence_delta=0.05,
    )
    assert obs.id.startswith("obs_")

    obs_list = k.list_observations(fact.id)
    assert len(obs_list) == 1
    assert obs_list[0].observation_type == ObservationType.CONFIRM
    assert obs_list[0].confidence_delta == 0.05


def test_link_facts_supersedes(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    old = _make_fact()
    old.id = "old"
    k.insert_fact(old)
    new = _make_fact()
    new.id = "new"
    k.insert_fact(new)

    rel = k.link_facts(new.id, old.id, RelationType.SUPERSEDES)
    assert rel.id.startswith("rel_")

    relations = k.list_relations(new.id)
    assert len(relations) == 1
    assert relations[0].relation_type == RelationType.SUPERSEDES
    assert relations[0].from_fact_id == "new"
    assert relations[0].to_fact_id == "old"


# ── FTS5 ──────────────────────────────────────────────────────────────────────


def test_fts_recherche_basique(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    f = _make_fact(subject="barth", predicate="targets", obj="sub-3h marathon", category="goal")
    f.id = "fact_goal"
    k.insert_fact(f)

    results = k.search_facts_fts("marathon")
    assert len(results) == 1
    assert results[0][0].id == "fact_goal"


def test_fts_pas_de_match(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    f = _make_fact()
    f.id = "x"
    k.insert_fact(f)
    assert k.search_facts_fts("zzzzz_inexistant") == []


def test_fts_caracteres_speciaux_tolere(tmp_path: Path) -> None:
    """Les guillemets/apostrophes dans la query ne doivent pas crasher."""
    k = MemoryKernel(tmp_path / "m.db")
    f = _make_fact()
    f.id = "y"
    k.insert_fact(f)
    # Ne doit pas crasher
    k.search_facts_fts('"unclosed quote')
    k.search_facts_fts("apostrophe'")


def test_fts_update_reindex(tmp_path: Path) -> None:
    """Quand on update un fact, sa réindexation FTS doit suivre."""
    k = MemoryKernel(tmp_path / "m.db")
    f = _make_fact(obj="python")
    f.id = "fact_lang"
    k.insert_fact(f)

    # Avant update : "python" matche
    assert any(r[0].id == "fact_lang" for r in k.search_facts_fts("python"))

    # Update object → ré-indexation
    f.object = "rust"
    k.update_fact(f)

    assert k.search_facts_fts("python") == []
    assert any(r[0].id == "fact_lang" for r in k.search_facts_fts("rust"))


# ── Correction humaine (§6.7) ─────────────────────────────────────────────────


def test_apply_correction_met_a_jour_fact_et_trace_event(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    f = _make_fact(obj="sub-3h")
    f.id = "goal_marathon"
    k.insert_fact(f)

    evt, updated = k.apply_correction(
        target_fact_id="goal_marathon",
        new_object="3h10",
        correction_text="Barth dit qu'il révise son objectif à 3h10",
    )

    assert evt.type == "human_correction"
    assert evt.metadata_json is not None
    assert "goal_marathon" in evt.metadata_json
    assert updated is not None
    assert updated.object == "3h10"

    obs = k.list_observations("goal_marathon")
    assert len(obs) == 1
    assert obs[0].observation_type == ObservationType.CORRECT


def test_apply_correction_fact_introuvable_trace_quand_meme(tmp_path: Path) -> None:
    k = MemoryKernel(tmp_path / "m.db")
    evt, fact = k.apply_correction(target_fact_id="nonexistent", new_object="x")
    assert evt.type == "human_correction"
    assert fact is None


# ── Atomicité / Foreign Keys ──────────────────────────────────────────────────


def test_persistence_apres_reouverture(tmp_path: Path) -> None:
    """Données persistées entre instances Kernel."""
    db = tmp_path / "p.db"
    k1 = MemoryKernel(db)
    f = _make_fact()
    f.id = "persist"
    k1.insert_fact(f)

    k2 = MemoryKernel(db)
    fetched = k2.get_fact("persist")
    assert fetched is not None
    assert fetched.subject == "barth"
