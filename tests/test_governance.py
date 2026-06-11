"""Tests du gate composite à 3 axes (CDC §9, PHASE 1 option α).

Couvre :
- Axe 1 (risque technique) — chaque AccessLevel produit la bonne décision (autres axes neutres)
- Axe 2 (catégorie d'approbation) — chaque ApprovalMode produit la bonne décision
- Axe 3 (budget) — hard_stop refuse même si risque et catégorie sont permissifs
- Croisé — le plus restrictif gagne (READ_ONLY + NEVER → REFUSED ; NETWORK + ALWAYS → APPROVAL)
- Audit — chaque appel laisse une entrée tracée avec les 3 décisions partielles
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.engine.audit import AuditLog
from jarvis.engine.mission.governance import GateContext, GateDecision, Governance
from jarvis.engine.vocab import AccessLevel
from jarvis.kernel.approvals import ApprovalConfig, ApprovalMode

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeBudget:
    """Fake BudgetGuard : on contrôle `_enabled`, `remaining()` et le scope."""

    def __init__(self, enabled: bool = True, remaining: float = 1000.0) -> None:
        self._enabled = enabled
        self._remaining = remaining

    def remaining(self, scope: str) -> float:  # noqa: ARG002 — scope ignoré dans le fake
        return self._remaining


def _make_governance(
    *,
    category_modes: dict[str, ApprovalMode] | None = None,
    budget_enabled: bool = False,
    budget_remaining: float = 1000.0,
    audit_path: Path | None = None,
) -> tuple[Governance, AuditLog]:
    """Construit une Governance avec dépendances paramétrables."""
    cfg = ApprovalConfig()
    if category_modes:
        for cat, mode in category_modes.items():
            setattr(cfg, cat, mode)
    budget = _FakeBudget(enabled=budget_enabled, remaining=budget_remaining)
    audit = AuditLog(audit_path or Path("/tmp/_test_audit_unused.jsonl"))
    return Governance(approval_config=cfg, budget_guard=budget, audit_log=audit), audit


def _ctx(
    access_level: AccessLevel = AccessLevel.READ_ONLY,
    category: str = "agent_mission",
    cost: float = 0.0,
    dry_run: bool = False,
) -> GateContext:
    return GateContext(
        access_level=access_level,
        action_category=category,
        estimated_cost_usd=cost,
        budget_scope="global",
        dry_run_available=dry_run,
    )


# ── 1. Axe 1 — risque technique (AccessLevel) ─────────────────────────────────


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (AccessLevel.READ_ONLY, GateDecision.AUTO),
        (AccessLevel.WRITE_LOCAL, GateDecision.AUTO),
        (AccessLevel.EXECUTE_CODE, GateDecision.AUTO),  # == AUTO_MAX_LEVEL
        (AccessLevel.NETWORK, GateDecision.APPROVAL),  # intermédiaire sans dry-run
        (AccessLevel.INSTALL_PACKAGE, GateDecision.APPROVAL),  # toujours
        (AccessLevel.MODIFY_CORE, GateDecision.APPROVAL),  # toujours
    ],
)
def test_risk_axis_isole(tmp_path: Path, level: AccessLevel, expected: GateDecision) -> None:
    """Catégorie ALWAYS + budget illimité : seul l'axe risque décide."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        budget_enabled=False,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=level)) == expected


def test_risk_network_avec_dry_run_dispo(tmp_path: Path) -> None:
    """NETWORK avec dry_run_available=True → DRY_RUN."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.NETWORK, dry_run=True)) == GateDecision.DRY_RUN


def test_risk_install_package_jamais_dry_run(tmp_path: Path) -> None:
    """INSTALL_PACKAGE → APPROVAL toujours, même avec dry_run_available."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert (
        gov.gate(_ctx(access_level=AccessLevel.INSTALL_PACKAGE, dry_run=True))
        == GateDecision.APPROVAL
    )


# ── 2. Axe 2 — catégorie d'approbation (ApprovalMode) ─────────────────────────


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (ApprovalMode.ALWAYS, GateDecision.AUTO),
        (ApprovalMode.ASK, GateDecision.APPROVAL),
        (ApprovalMode.NEVER, GateDecision.REFUSED),
    ],
)
def test_category_axis_isole(tmp_path: Path, mode: ApprovalMode, expected: GateDecision) -> None:
    """Risque READ_ONLY + budget illimité : seul l'axe catégorie décide."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": mode},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.READ_ONLY)) == expected


def test_category_inconnue_fallback_ask(tmp_path: Path) -> None:
    """Catégorie absente d'ApprovalConfig → comportement conservateur ASK → APPROVAL."""
    gov, _ = _make_governance(audit_path=tmp_path / "audit.jsonl")
    assert gov.gate(_ctx(category="categorie_inexistante")) == GateDecision.APPROVAL


# ── 3. Axe 3 — budget (BudgetGuard) ───────────────────────────────────────────


def test_budget_hard_stop_refuse_meme_si_axes_permissifs(tmp_path: Path) -> None:
    """READ_ONLY + ALWAYS + budget hard_stop → REFUSED."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        budget_enabled=True,
        budget_remaining=0.01,  # < cost
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(cost=0.10)) == GateDecision.REFUSED


def test_budget_marge_ok(tmp_path: Path) -> None:
    """READ_ONLY + ALWAYS + budget OK → AUTO."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        budget_enabled=True,
        budget_remaining=10.0,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(cost=0.05)) == GateDecision.AUTO


def test_budget_desactive_axe_neutre(tmp_path: Path) -> None:
    """budget._enabled=False → axe neutre → AUTO via axe 1 et 2 permissifs."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        budget_enabled=False,
        budget_remaining=0.0,  # ignoré car _enabled=False
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(cost=1000.0)) == GateDecision.AUTO


# ── 4. Croisé — le plus restrictif gagne ──────────────────────────────────────


def test_read_only_mais_never_refuse(tmp_path: Path) -> None:
    """Action à risque nul mais catégorie NEVER → REFUSED."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.NEVER},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.READ_ONLY)) == GateDecision.REFUSED


def test_network_mais_always_reste_approval_a_cause_du_risque(tmp_path: Path) -> None:
    """NETWORK + ALWAYS → APPROVAL (le risque domine ALWAYS)."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.NETWORK)) == GateDecision.APPROVAL


def test_modify_core_toujours_approval_meme_si_ask(tmp_path: Path) -> None:
    """MODIFY_CORE + ASK → APPROVAL (les deux concordent, mais le risque garantit le résultat)."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ASK},
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.MODIFY_CORE)) == GateDecision.APPROVAL


def test_budget_hard_stop_domine_approval(tmp_path: Path) -> None:
    """NETWORK + ASK + budget hard_stop → REFUSED (refusé domine approval)."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ASK},
        budget_enabled=True,
        budget_remaining=0.001,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.NETWORK, cost=1.0)) == GateDecision.REFUSED


def test_tous_axes_permissifs_auto(tmp_path: Path) -> None:
    """Tous les axes au plus permissif → AUTO."""
    gov, _ = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ALWAYS},
        budget_enabled=False,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert gov.gate(_ctx(access_level=AccessLevel.READ_ONLY)) == GateDecision.AUTO


# ── 5. Audit — chaque appel trace les 3 décisions partielles ──────────────────


def test_audit_trace_les_trois_axes(tmp_path: Path) -> None:
    """Chaque gate() laisse une entrée d'audit contenant les 3 décisions partielles."""
    audit_path = tmp_path / "audit.jsonl"
    gov, audit = _make_governance(
        category_modes={"agent_mission": ApprovalMode.ASK},
        budget_enabled=True,
        budget_remaining=10.0,
        audit_path=audit_path,
    )
    gov.gate(
        _ctx(access_level=AccessLevel.NETWORK, cost=0.05),
        context_id="step:proj:s1",
    )

    entries = audit.read_all()
    assert len(entries) == 1
    e = entries[0]
    assert e.context_id == "step:proj:s1"
    assert e.access_level == int(AccessLevel.NETWORK)
    assert e.action_category == "agent_mission"
    assert e.estimated_cost_usd == 0.05
    # Les 3 axes sont tracés
    assert e.risk_decision == GateDecision.APPROVAL.value
    assert e.category_decision == GateDecision.APPROVAL.value
    assert e.budget_decision == GateDecision.AUTO.value
    # Décision finale = APPROVAL (le plus restrictif)
    assert e.decision == GateDecision.APPROVAL.value


def test_audit_chaque_appel_ajoute_une_entree(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gov, audit = _make_governance(audit_path=audit_path)
    for i in range(3):
        gov.gate(_ctx(), context_id=f"step:proj:s{i}")
    entries = audit.read_all()
    assert len(entries) == 3
    assert {e.context_id for e in entries} == {"step:proj:s0", "step:proj:s1", "step:proj:s2"}


# ── 6. Test de non-régression sécurité — MODIFY_CORE / INSTALL_PACKAGE ────────


@pytest.mark.parametrize(
    "level",
    [AccessLevel.INSTALL_PACKAGE, AccessLevel.MODIFY_CORE],
)
def test_securite_critique_jamais_auto(tmp_path: Path, level: AccessLevel) -> None:
    """Aucune combinaison ne doit permettre auto pour INSTALL_PACKAGE / MODIFY_CORE."""
    for mode in (ApprovalMode.ALWAYS, ApprovalMode.ASK, ApprovalMode.NEVER):
        gov, _ = _make_governance(
            category_modes={"agent_mission": mode},
            audit_path=tmp_path / "audit.jsonl",
        )
        decision = gov.gate(_ctx(access_level=level))
        assert decision != GateDecision.AUTO, (
            f"FUITE SÉCURITÉ : level={level.name}, mode={mode.value} → {decision.value}"
        )
