# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests du log d'audit (CDC §9 — toute action laisse une entrée d'audit)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jarvis.engine.audit import AuditEntry, AuditLog


def _make_entry(decision: str = "auto", ctx: str = "step:proj:s1") -> AuditEntry:
    return AuditEntry(
        timestamp=datetime(2026, 6, 1, 12, 0, 0),
        decision=decision,
        context_id=ctx,
        access_level=1,
        action_category="agent_mission",
        estimated_cost_usd=0.02,
        risk_decision="auto",
        category_decision="auto",
        budget_decision="auto",
        budget_status="ok",
        extra={"description": "test step"},
    )


def test_audit_log_creates_parent_dir(tmp_path: Path) -> None:
    audit_path = tmp_path / "deep" / "nested" / "audit.jsonl"
    log = AuditLog(audit_path)
    assert audit_path.parent.exists()
    assert log.path == audit_path


def test_audit_append_and_read_roundtrip(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    e1 = _make_entry("auto", "step:proj:s1")
    e2 = _make_entry("approval", "tool:write_file:proj:s2")
    log.append(e1)
    log.append(e2)

    entries = log.read_all()
    assert len(entries) == 2
    assert entries[0].decision == "auto"
    assert entries[1].decision == "approval"
    assert entries[0].context_id == "step:proj:s1"
    assert entries[1].context_id == "tool:write_file:proj:s2"
    assert entries[0].timestamp == datetime(2026, 6, 1, 12, 0, 0)


def test_audit_read_empty_log(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    assert log.read_all() == []


def test_audit_append_only_no_truncate(tmp_path: Path) -> None:
    """L'audit log NE supprime JAMAIS une entrée — il est append-only."""
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(5):
        log.append(_make_entry(ctx=f"step:proj:s{i}"))
    # Nouvelle instance, même chemin
    log2 = AuditLog(tmp_path / "audit.jsonl")
    log2.append(_make_entry(ctx="step:proj:s6"))
    entries = log2.read_all()
    assert len(entries) == 6
    assert [e.context_id for e in entries][-1] == "step:proj:s6"


def test_audit_handles_empty_lines(tmp_path: Path) -> None:
    """Tolère les lignes blanches dans le fichier (manipulations externes)."""
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append(_make_entry())
    # Ajout d'une ligne vide
    with (tmp_path / "audit.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n\n")
    log.append(_make_entry(ctx="step:proj:s2"))
    entries = log.read_all()
    assert len(entries) == 2
