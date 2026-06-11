"""Tests du SkillLifecycle (CDC §7.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.capabilities.skills.lifecycle import CONFIDENCE_INITIAL, SkillLifecycle, SkillStatus


@pytest.fixture
def lifecycle(tmp_path: Path) -> SkillLifecycle:
    return SkillLifecycle(db_path=tmp_path / "skills.db")


def test_create_candidate(lifecycle: SkillLifecycle) -> None:
    record = lifecycle.create_candidate(name="my-skill", source_event_id="evt_1")
    assert record.name == "my-skill"
    assert record.status == SkillStatus.CANDIDATE
    assert record.confidence == CONFIDENCE_INITIAL
    assert record.support_count == 0
    assert record.source_event_id == "evt_1"


def test_create_candidate_idempotent(lifecycle: SkillLifecycle) -> None:
    """Recréer une candidate déjà présente renvoie l'existante sans écraser."""
    lifecycle.create_candidate(name="my-skill", source_event_id="evt_1")
    # Simule la transition
    lifecycle.mark_sandbox_result(name="my-skill", passed=True, notes="ok")
    # Re-création
    r2 = lifecycle.create_candidate(name="my-skill", source_event_id="evt_2")
    assert r2.status == SkillStatus.SANDBOXED_PASS
    assert r2.source_event_id == "evt_1"  # source d'origine préservée


def test_get_returns_none_if_unknown(lifecycle: SkillLifecycle) -> None:
    assert lifecycle.get("inexistante") is None


def test_mark_sandbox_pass(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="ok-skill")
    record = lifecycle.mark_sandbox_result(name="ok-skill", passed=True, notes="all good")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_PASS
    assert "all good" in (record.sandbox_notes or "")


def test_mark_sandbox_fail(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="bad-skill")
    record = lifecycle.mark_sandbox_result(name="bad-skill", passed=False, notes="import error")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_FAIL
    assert "import" in (record.sandbox_notes or "")


def test_promote(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="ok-skill")
    lifecycle.mark_sandbox_result(name="ok-skill", passed=True, notes="ok")
    record = lifecycle.promote("ok-skill")
    assert record is not None
    assert record.status == SkillStatus.ACTIVE
    assert record.promoted_at is not None


def test_promote_skill_inconnue(lifecycle: SkillLifecycle) -> None:
    assert lifecycle.promote("inexistante") is None


def test_reject(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="bad")
    lifecycle.mark_sandbox_result(name="bad", passed=True, notes="ok")
    record = lifecycle.reject("bad", reason="trop générique")
    assert record is not None
    assert record.status == SkillStatus.REJECTED
    assert "trop générique" in (record.sandbox_notes or "")


def test_mark_used_increment_compteurs(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="s")
    lifecycle.mark_sandbox_result(name="s", passed=True, notes="ok")
    lifecycle.promote("s")
    initial = lifecycle.get("s")
    assert initial is not None
    initial_conf = initial.confidence

    record = lifecycle.mark_used("s")
    assert record is not None
    assert record.support_count == 1
    assert record.last_used_at is not None
    assert record.confidence == pytest.approx(min(0.99, initial_conf + 0.05))


def test_mark_used_revient_de_stale_a_active(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="s")
    lifecycle.mark_sandbox_result(name="s", passed=True, notes="ok")
    lifecycle.promote("s")
    lifecycle.mark_stale("s")
    assert lifecycle.get("s").status == SkillStatus.STALE
    record = lifecycle.mark_used("s")
    assert record.status == SkillStatus.ACTIVE  # réactivation


def test_archive(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="s")
    lifecycle.mark_sandbox_result(name="s", passed=True, notes="ok")
    lifecycle.promote("s")
    lifecycle.mark_stale("s")
    record = lifecycle.archive("s")
    assert record is not None
    assert record.status == SkillStatus.ARCHIVED
    assert record.archived_at is not None


def test_list_by_status(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="c1")
    lifecycle.create_candidate(name="c2")
    lifecycle.mark_sandbox_result(name="c1", passed=True, notes="")
    lifecycle.promote("c1")

    candidates = lifecycle.list_by_status(SkillStatus.CANDIDATE)
    actives = lifecycle.list_by_status(SkillStatus.ACTIVE)
    assert {r.name for r in candidates} == {"c2"}
    assert {r.name for r in actives} == {"c1"}


def test_count_by_status(lifecycle: SkillLifecycle) -> None:
    lifecycle.create_candidate(name="a")
    lifecycle.create_candidate(name="b")
    lifecycle.mark_sandbox_result(name="a", passed=True, notes="")
    lifecycle.promote("a")
    assert lifecycle.count_by_status(SkillStatus.ACTIVE) == 1
    assert lifecycle.count_by_status(SkillStatus.CANDIDATE) == 1


def test_has_been_proposed_for_event(lifecycle: SkillLifecycle) -> None:
    """Idempotence du polling : un event déjà traité ne re-déclenche pas."""
    lifecycle.create_candidate(name="s", source_event_id="evt_xyz")
    assert lifecycle.has_been_proposed_for_event("evt_xyz") is True
    assert lifecycle.has_been_proposed_for_event("evt_inconnu") is False


def test_persistance_entre_instances(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    lc1 = SkillLifecycle(db_path=db)
    lc1.create_candidate(name="s", source_event_id="e")

    lc2 = SkillLifecycle(db_path=db)
    record = lc2.get("s")
    assert record is not None
    assert record.source_event_id == "e"
