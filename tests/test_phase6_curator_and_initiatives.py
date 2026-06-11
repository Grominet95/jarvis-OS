"""Tests PHASE 6 — Curator + Command Center + initiatives gouvernées.

Cas négatifs prioritaires (CDC §10) :
- Initiative niveau 5 (EXTERNAL_ACTION) exige TOUJOURS validation humaine.
- Le Curator ne s'auto-applique PAS, même pour les patches signalés
  auto_appliable=True.
- Tout patch qui toucherait au noyau §11 (`_PROTECTED_PATHS`) est REFUSÉ.
- Budget hard_stop note dans le rapport.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest

from jarvis.capabilities.skills.lifecycle import SkillLifecycle
from jarvis.engine.proactive.curator import (
    _PROTECTED_PATHS,
    Curator,
    PatchKind,
    is_protected_path,
)
from jarvis.engine.proactive.schemas import (
    ExecutionMode,
    Initiative,
    InitiativeType,
    Priority,
    needs_human_validation,
)
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.engine.vocab import AutonomyLevel
from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.schemas import DecayPolicy, Fact, FactStatus

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_initiative(
    autonomy_level: AutonomyLevel = AutonomyLevel.SUGGEST,
    requires_validation: bool = False,
    title: str = "Test",
) -> Initiative:
    return Initiative(
        id="ini_test",
        type=InitiativeType.SUGGESTION,
        title=title,
        context="ctx",
        reasoning="r",
        action="a",
        priority=Priority.MEDIUM,
        execution_mode=ExecutionMode.NOTIFY,
        autonomy_level=autonomy_level,
        requires_validation=requires_validation,
    )


def _make_fact(
    fid: str,
    decay: DecayPolicy = DecayPolicy.FAST,
    age_days: float = 0.0,
) -> Fact:
    ts = datetime.now() - timedelta(days=age_days)
    return Fact(
        id=fid,
        subject="barth",
        predicate="prefers",
        object="python",
        category="goal",
        status=FactStatus.ACTIVE,
        confidence=0.75,
        support_count=1,
        decay_policy=decay,
        importance=0.5,
        created_at=ts,
        last_seen_at=ts,
        updated_at=ts,
    )


@pytest.fixture
def kernel(tmp_path: Path) -> MemoryKernel:
    return MemoryKernel(tmp_path / "memory.db")


@pytest.fixture
def lifecycle(tmp_path: Path) -> SkillLifecycle:
    return SkillLifecycle(db_path=tmp_path / "memory.db")


@pytest.fixture
def initiative_store(tmp_path: Path) -> InitiativeStore:
    with mock_patch("jarvis.engine.proactive.store.INITIATIVES_DIR", tmp_path / "initiatives"):
        store = InitiativeStore()
        yield store


@pytest.fixture
def curator(
    tmp_path: Path,
    kernel: MemoryKernel,
    lifecycle: SkillLifecycle,
    initiative_store: InitiativeStore,
) -> Curator:
    return Curator(
        kernel=kernel,
        skill_lifecycle=lifecycle,
        initiative_store=initiative_store,
        budget_guard=None,
        reports_dir=tmp_path / "curator_reports",
    )


# ── 1. Initiative niveau 5 (EXTERNAL_ACTION) exige TOUJOURS validation ──────


def test_initiative_niveau_5_exige_validation_par_principe() -> None:
    """CDC §10.1 : niveau 5 = publier/payer/contacter/supprimer → validation
    humaine TOUJOURS, même si requires_validation=False."""
    init = _make_initiative(
        autonomy_level=AutonomyLevel.EXTERNAL_ACTION,
        requires_validation=False,  # explicitly False !
    )
    assert needs_human_validation(init) is True


def test_initiative_niveau_bas_avec_flag_explicite_exige_validation() -> None:
    """requires_validation=True peut FORCER validation même sur niveau bas."""
    init = _make_initiative(
        autonomy_level=AutonomyLevel.SUGGEST,
        requires_validation=True,
    )
    assert needs_human_validation(init) is True


def test_initiative_niveau_bas_sans_flag_pas_de_validation_forcee() -> None:
    """Niveau 1 (SUGGEST) sans flag explicite → pas forcé en validation."""
    init = _make_initiative(
        autonomy_level=AutonomyLevel.SUGGEST,
        requires_validation=False,
    )
    assert needs_human_validation(init) is False


def test_initiative_roundtrip_jsonl_preserve_niveau(
    initiative_store: InitiativeStore,
) -> None:
    """Round-trip JSON : les nouveaux champs §10.1 persistent."""
    init = _make_initiative(autonomy_level=AutonomyLevel.EXTERNAL_ACTION)
    init.id = "ini_roundtrip"
    init.permission_required = "email_send"
    init.cost_max_usd = 1.50
    init.risk = "high"
    init.next_action = "envoyer email confirmation"
    init.requires_validation = True
    initiative_store.save(init)

    loaded = initiative_store.get_by_id("ini_roundtrip")
    assert loaded is not None
    assert loaded.autonomy_level == AutonomyLevel.EXTERNAL_ACTION
    assert loaded.permission_required == "email_send"
    assert loaded.cost_max_usd == 1.50
    assert loaded.risk == "high"
    assert loaded.next_action == "envoyer email confirmation"
    assert loaded.requires_validation is True


def test_initiative_legacy_jsonl_compat_ascendante(
    initiative_store: InitiativeStore,
) -> None:
    """Un JSON sans les champs §10.1 (legacy) se recharge avec defaults."""
    import json

    today = datetime.now().strftime("%Y-%m-%d")
    # On écrit directement un legacy
    from jarvis.engine.proactive.store import INITIATIVES_DIR

    INITIATIVES_DIR.mkdir(parents=True, exist_ok=True)
    legacy_path = INITIATIVES_DIR / f"{today}.jsonl"
    legacy_data = {
        "id": "ini_legacy",
        "type": "suggestion",
        "title": "Vieille initiative",
        "context": "ctx",
        "reasoning": "r",
        "action": "a",
        "priority": "medium",
        "execution_mode": "notify",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        # PAS de autonomy_level, permission_required, etc.
    }
    with legacy_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(legacy_data) + "\n")

    loaded = initiative_store.get_by_id("ini_legacy")
    assert loaded is not None
    assert loaded.autonomy_level == AutonomyLevel.SUGGEST  # default
    assert loaded.permission_required == "agent_mission"
    assert loaded.cost_max_usd is None
    assert loaded.risk == "low"


# ── 2. Curator détecte les skills stale ──────────────────────────────────────


async def test_curator_detecte_skill_stale(curator: Curator, lifecycle: SkillLifecycle) -> None:
    """Une skill ACTIVE non utilisée depuis > 30j → patch MARK_SKILL_STALE proposé."""
    # Skill "vieille" qui n'a pas été utilisée
    lifecycle.create_candidate("skill-old")
    lifecycle.mark_sandbox_result("skill-old", passed=True, notes="ok")
    rec = lifecycle.promote("skill-old")
    assert rec is not None
    # Backdate manuellement le created_at + promoted_at (pas d'API publique
    # — on triche en SQL direct pour simuler une skill ancienne)
    import sqlite3

    old = (datetime.now() - timedelta(days=60)).isoformat()
    with sqlite3.connect(lifecycle.db_path) as conn:
        conn.execute(
            "UPDATE skills SET created_at=?, promoted_at=?, updated_at=? WHERE name=?",
            (old, old, old, "skill-old"),
        )
        conn.commit()

    report = await curator.scan()

    stale_patches = [p for p in report.patches if p.kind == PatchKind.MARK_SKILL_STALE]
    assert len(stale_patches) == 1
    assert stale_patches[0].target == "skill-old"


# ── 3. Curator détecte les facts à archiver par decay ────────────────────────


async def test_curator_detecte_facts_decay(curator: Curator, kernel: MemoryKernel) -> None:
    """Fact FAST decay vieux de > 3 demi-vies (42j) → patch ARCHIVE_FACT."""
    f = _make_fact("fact_old", decay=DecayPolicy.FAST, age_days=50.0)
    kernel.insert_fact(f)

    report = await curator.scan()

    archive_patches = [p for p in report.patches if p.kind == PatchKind.ARCHIVE_FACT]
    assert len(archive_patches) == 1
    assert archive_patches[0].target == "fact_old"


async def test_curator_ignore_facts_recents(curator: Curator, kernel: MemoryKernel) -> None:
    """Fact récent (< demi-vie) → pas de patch decay proposé."""
    f = _make_fact("fact_recent", decay=DecayPolicy.FAST, age_days=2.0)
    kernel.insert_fact(f)

    report = await curator.scan()

    archive_patches = [p for p in report.patches if p.kind == PatchKind.ARCHIVE_FACT]
    assert len(archive_patches) == 0


async def test_curator_ignore_facts_decay_none(curator: Curator, kernel: MemoryKernel) -> None:
    """Fact DecayPolicy.NONE (identity) → jamais archivé, peu importe l'âge."""
    f = _make_fact("fact_identity", decay=DecayPolicy.NONE, age_days=10000.0)
    kernel.insert_fact(f)

    report = await curator.scan()

    archive_patches = [p for p in report.patches if p.kind == PatchKind.ARCHIVE_FACT]
    assert len(archive_patches) == 0


# ── 4. CRITIQUE : Curator n'APPLIQUE jamais en MVP ──────────────────────────


async def test_curator_apply_patch_refuse_toujours_en_mvp(curator: Curator) -> None:
    """CDC §10 anti-pattern : le Curator PROPOSE, n'APPLIQUE pas."""
    # Force la création d'un rapport avec au moins un patch

    f = _make_fact("fact_for_apply_test", decay=DecayPolicy.FAST, age_days=100.0)
    curator._kernel.insert_fact(f)
    report = await curator.scan()
    assert len(report.patches) >= 1

    # Tente d'appliquer le premier patch — DOIT être refusé
    applied, reason = curator.apply_patch(0, report)
    assert applied is False
    assert "refuse" in reason.lower() or "manuel" in reason.lower()


async def test_curator_patch_sur_noyau_protege_refuse(
    curator: Curator,
) -> None:
    """§11 PERSONNALITÉ : un patch dont target est dans _PROTECTED_PATHS
    est refusé AVANT même la phase d'exécution.

    On simule un patch qui cible un fichier protégé en l'insérant dans la
    liste pendant un scan (via réécriture du _scan_facts).
    """
    from jarvis.engine.proactive.curator import CuratorPatch, PatchKind

    # Injecte un patch synthétique qui cible un fichier protégé
    fake_patch = CuratorPatch(
        kind=PatchKind.ARCHIVE_FACT,  # peu importe le kind ici
        target="prompts/system_static.md",  # PROTÉGÉ
        description="patch malveillant qui touche le noyau",
        auto_appliable=True,  # même signalé auto, doit être refusé
        reason="test",
    )
    patches = [fake_patch]
    kept, refused = curator._filter_protected_patches(patches)
    assert kept == []
    assert len(refused) == 1
    assert "system_static.md" in refused[0]


def test_is_protected_path() -> None:
    """Sanity check : tous les paths _PROTECTED_PATHS sont reconnus."""
    for p in _PROTECTED_PATHS:
        assert is_protected_path(p), f"{p} devrait être protégé"
        assert is_protected_path(f"/abs/path/{p}"), f"absolute path /abs/path/{p}"
    # Non-protégés
    assert not is_protected_path("random/file.txt")
    assert not is_protected_path("skills_data/installed/my-skill/skill.py")


# ── 5. Curator produit un rapport persisté ──────────────────────────────────


async def test_curator_scan_persiste_le_rapport(curator: Curator, tmp_path: Path) -> None:
    """Chaque scan écrit un JSON timestampé + le miroir latest.md."""
    report = await curator.scan()
    json_files = sorted((tmp_path / "curator_reports").glob("*.json"))
    assert len(json_files) >= 1
    md_file = tmp_path / "curator_reports" / "latest.md"
    assert md_file.exists()
    md = md_file.read_text(encoding="utf-8")
    assert "Curator Report" in md
    # Le rapport latest_report() doit le retrouver
    loaded = curator.latest_report()
    assert loaded is not None
    assert loaded.generated_at == report.generated_at


async def test_curator_scan_avec_aucune_donnee_renvoie_rapport_vide(
    curator: Curator,
) -> None:
    """Kernel vide + lifecycle vide → rapport sans patches."""
    report = await curator.scan()
    assert report.facts_active == 0
    assert report.skills_active == 0
    assert len(report.patches) == 0


# ── 6. Budget hard_stop noté dans le rapport ─────────────────────────────────


class _FakeBudgetHardStop:
    """Fake BudgetGuard qui retourne hard_stop."""

    def status(self) -> dict:
        return {
            "enabled": True,
            "global": {
                "spent_usd": 100.0,
                "limit_usd": 100.0,
                "remaining_usd": 0.0,
                "utilization_pct": 100.0,
                "status": "hard_stop",
            },
            "projects": {},
        }


async def test_curator_budget_hard_stop_note_dans_rapport(
    tmp_path: Path,
    kernel: MemoryKernel,
    lifecycle: SkillLifecycle,
    initiative_store: InitiativeStore,
) -> None:
    """Budget en hard_stop → note explicite dans le rapport."""
    cur = Curator(
        kernel=kernel,
        skill_lifecycle=lifecycle,
        initiative_store=initiative_store,
        budget_guard=_FakeBudgetHardStop(),
        reports_dir=tmp_path / "reports",
    )
    report = await cur.scan()
    assert report.budget_status == "hard_stop"
    assert any("HARD_STOP" in n for n in report.notes)


# ── 7. Command Center snapshot agrège correctement ──────────────────────────


def test_command_center_snapshot_agrege_tout(
    tmp_path: Path,
    kernel: MemoryKernel,
    lifecycle: SkillLifecycle,
    initiative_store: InitiativeStore,
) -> None:
    """CommandCenter agrège initiatives, missions, budget, skills sans crash."""
    from jarvis.engine.proactive.command_center import CommandCenter

    # Setup état minimal
    init = _make_initiative(title="Test snapshot")
    initiative_store.save(init)

    lifecycle.create_candidate("snap-skill")

    # ProjectStore mock simple
    class _FakeProjectStore:
        def list_projects(self) -> list:
            return []

    cc = CommandCenter(
        initiative_store=initiative_store,
        project_store=_FakeProjectStore(),
        budget_guard=None,
        skill_lifecycle=lifecycle,
    )

    snap = cc.snapshot(days=1)
    assert snap.captured_at  # non vide
    assert len(snap.initiatives) >= 1
    assert snap.initiatives[0].title == "Test snapshot"
    assert snap.budget.enabled is False  # pas de budget guard
    # SkillSummary contient au moins notre candidate
    assert snap.skills.by_status.get("candidate", 0) == 1


def test_command_center_snapshot_avec_budget(
    tmp_path: Path,
    kernel: MemoryKernel,
    lifecycle: SkillLifecycle,
    initiative_store: InitiativeStore,
) -> None:
    """Le snapshot inclut le budget si BudgetGuard fourni."""
    from jarvis.engine.proactive.command_center import CommandCenter

    class _FakeProjectStore:
        def list_projects(self) -> list:
            return []

    cc = CommandCenter(
        initiative_store=initiative_store,
        project_store=_FakeProjectStore(),
        budget_guard=_FakeBudgetHardStop(),
        skill_lifecycle=lifecycle,
    )
    snap = cc.snapshot()
    assert snap.budget.enabled is True
    assert snap.budget.global_status == "hard_stop"
    assert snap.budget.global_spent_usd == 100.0


def test_command_center_heartbeat() -> None:
    """signal_heartbeat met à jour le timestamp interne."""
    from jarvis.engine.proactive.command_center import CommandCenter

    class _FakeProjectStore:
        def list_projects(self) -> list:
            return []

    class _FakeInitiativeStore:
        def list_recent(self, days: int = 7) -> list:  # noqa: ARG002
            return []

    cc = CommandCenter(
        initiative_store=_FakeInitiativeStore(),
        project_store=_FakeProjectStore(),
        budget_guard=None,
        skill_lifecycle=None,
    )
    snap1 = cc.snapshot()
    assert snap1.heartbeat_seconds is None  # jamais signalé
    cc.signal_heartbeat()
    snap2 = cc.snapshot()
    assert snap2.heartbeat_seconds is not None
    assert snap2.heartbeat_seconds < 1.0  # vient d'être signalé


# ── 8. Garde-fou : apply_patch sur index hors borne ─────────────────────────


async def test_curator_apply_patch_index_hors_borne(curator: Curator) -> None:
    report = await curator.scan()
    applied, reason = curator.apply_patch(999, report)
    assert applied is False
    assert "hors borne" in reason
