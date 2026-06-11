"""Tests du retrieval (CDC §6.9) — score importance × récence × pertinence × confidence + decay."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.retrieval import MemoryRetrieval, _bm25_to_relevance, _recency_factor
from jarvis.providers.memory.schemas import DecayPolicy, Fact, FactStatus, RelationType


def _make_fact(
    fid: str,
    subject: str = "barth",
    predicate: str = "prefers",
    obj: str = "python",
    category: str = "tool",
    status: FactStatus = FactStatus.ACTIVE,
    confidence: float = 0.75,
    importance: float = 0.6,
    decay: DecayPolicy = DecayPolicy.MEDIUM,
    last_seen: datetime | None = None,
) -> Fact:
    now = last_seen or datetime.now()
    return Fact(
        id=fid,
        subject=subject,
        predicate=predicate,
        object=obj,
        category=category,
        status=status,
        confidence=confidence,
        support_count=1,
        decay_policy=decay,
        importance=importance,
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )


@pytest.fixture
def kernel(tmp_path: Path) -> MemoryKernel:
    return MemoryKernel(tmp_path / "test.db")


# ── Utils ─────────────────────────────────────────────────────────────────────


def test_recency_decay_none_toujours_1() -> None:
    f = _make_fact("x", decay=DecayPolicy.NONE)
    long_ago = datetime.now() + timedelta(days=10000)
    assert _recency_factor(f, long_ago) == 1.0


def test_recency_decay_fast_diminue_avec_age() -> None:
    f = _make_fact("x", decay=DecayPolicy.FAST, last_seen=datetime.now() - timedelta(days=14))
    # 14 jours = 1 demi-vie pour FAST → ~0.5
    rec = _recency_factor(f, datetime.now())
    assert 0.4 < rec < 0.6


def test_bm25_to_relevance_borne() -> None:
    assert _bm25_to_relevance(0.0) == 0.0  # no match
    r1 = _bm25_to_relevance(-2.0)
    r2 = _bm25_to_relevance(-10.0)
    assert 0.0 <= r1 <= 1.0
    assert 0.0 <= r2 <= 1.0


# ── Retrieval de base ─────────────────────────────────────────────────────────


def test_retrieve_remonte_les_facts_pertinents(kernel: MemoryKernel) -> None:
    kernel.insert_fact(_make_fact("f1", obj="python developer"))
    kernel.insert_fact(_make_fact("f2", obj="cuisine italienne", category="preference"))

    retrieval = MemoryRetrieval(kernel)
    results = retrieval.retrieve("python", k=5)
    assert len(results) >= 1
    assert results[0].fact.id == "f1"
    assert results[0].score > 0


def test_retrieve_ignore_les_superseded(kernel: MemoryKernel) -> None:
    kernel.insert_fact(_make_fact("old", obj="python ancien", status=FactStatus.SUPERSEDED))
    kernel.insert_fact(_make_fact("new", obj="python récent"))
    results = MemoryRetrieval(kernel).retrieve("python")
    ids = [r.fact.id for r in results]
    assert "old" not in ids
    assert "new" in ids


def test_score_combine_4_axes(kernel: MemoryKernel) -> None:
    """Plus haute importance × confidence × récence → score plus élevé."""
    # f1 : importance/confidence haute, récent
    kernel.insert_fact(_make_fact("haut", obj="python", importance=0.9, confidence=0.95))
    # f2 : même contenu mais importance/confidence basse
    kernel.insert_fact(_make_fact("bas", obj="python", importance=0.2, confidence=0.3))
    results = MemoryRetrieval(kernel).retrieve("python", k=2)
    assert results[0].fact.id == "haut"
    assert results[1].fact.id == "bas"
    assert results[0].score > results[1].score


def test_decay_reduit_la_saillance_au_retrieval(kernel: MemoryKernel) -> None:
    """Un goal vieux de 30 jours (FAST decay) saillance < goal d'aujourd'hui."""
    now = datetime.now()
    kernel.insert_fact(
        _make_fact(
            "old_goal",
            obj="ancien obj running",
            category="goal",
            decay=DecayPolicy.FAST,
            last_seen=now - timedelta(days=30),
        )
    )
    kernel.insert_fact(
        _make_fact("new_goal", obj="objectif running", category="goal", decay=DecayPolicy.FAST)
    )

    results = MemoryRetrieval(kernel).retrieve("running")
    by_id = {r.fact.id: r for r in results}
    assert by_id["new_goal"].recency > by_id["old_goal"].recency
    assert by_id["new_goal"].score > by_id["old_goal"].score


def test_decay_identity_pas_de_chute(kernel: MemoryKernel) -> None:
    """Une identity ancienne garde recency = 1.0 (DecayPolicy.NONE)."""
    now = datetime.now()
    kernel.insert_fact(
        _make_fact(
            "id_old",
            obj="developer",
            category="identity",
            decay=DecayPolicy.NONE,
            last_seen=now - timedelta(days=1000),
        )
    )
    results = MemoryRetrieval(kernel).retrieve("developer")
    assert len(results) == 1
    assert results[0].recency == 1.0


# ── Contradictions ────────────────────────────────────────────────────────────


def test_retrieve_remonte_les_contradictions(kernel: MemoryKernel) -> None:
    """Si un fact actif a un old superseded, retrieve liste l'old en contradiction."""
    kernel.insert_fact(
        _make_fact("old", obj="sub-3h", category="goal", status=FactStatus.SUPERSEDED)
    )
    kernel.insert_fact(_make_fact("new", obj="3h10", category="goal"))
    kernel.link_facts("new", "old", RelationType.SUPERSEDES)

    results = MemoryRetrieval(kernel).retrieve("3h10")
    assert len(results) == 1
    assert results[0].fact.id == "new"
    assert len(results[0].contradictions) == 1
    assert results[0].contradictions[0].id == "old"


def test_cold_start_fallback_recents_actifs(kernel: MemoryKernel) -> None:
    """Si pas de match FTS, on renvoie les facts ACTIVE les plus récents."""
    kernel.insert_fact(_make_fact("recent", obj="quelque chose"))
    results = MemoryRetrieval(kernel).retrieve("zzz_query_inexistante", k=5)
    # Pas de match FTS mais on a quand même quelque chose
    assert len(results) >= 1
