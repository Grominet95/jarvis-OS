"""Tests du SkillLab (CDC §7) — gate test-vert-sinon-rejet + polling idempotent.

Le test sandbox tourne en mode DIRECT (Docker indisponible en CI) — c'est le
fallback prévu dans SkillLab._run_direct_test. Cela suffit à vérifier que :
- le gate distingue skill correcte vs skill cassée,
- le lifecycle est mis à jour cohéremment,
- la promotion refuse si pas SANDBOXED_PASS,
- le scan est idempotent (un event déjà traité ne re-génère pas).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.capabilities.skills.lab import SkillLab
from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillStatus
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.kernel import MemoryKernel

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeSynthesizerLLM(LLMProvider):
    """Renvoie un SKILL.md prédéfini (l'extracteur n'est pas testé ici)."""

    def __init__(self, skill_md: str) -> None:
        self._md = skill_md
        self.calls = 0

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        self.calls += 1
        return self._md

    async def health_check(self) -> bool:
        return True


_GOOD_SKILL_MD = """\
---
name: batch-articles
description: Génère N articles markdown structurés à partir d'un template.
license: MIT
metadata:
  author: jarvis-synthesizer
  version: "1.0"
  tags: [content, batch, markdown]
---

# batch-articles

Quand l'utilisateur demande de produire plusieurs articles similaires :

1. Identifier le template commun.
2. Pour chaque sujet, instancier le template.
3. Vérifier la cohérence finale.
"""


# SKILL.md sans 'name' → le synthesizer lève ValueError → le Lab gère
_BROKEN_SKILL_MD = """\
---
description: Skill foireuse sans champ name.
license: MIT
metadata:
  author: jarvis-synthesizer
  version: "1.0"
---

Du contenu mais pas de nom.
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def kernel(workspace: Path) -> MemoryKernel:
    return MemoryKernel(workspace / "memory.db")


@pytest.fixture
def lifecycle(workspace: Path) -> SkillLifecycle:
    return SkillLifecycle(db_path=workspace / "memory.db")


def _make_lab(
    kernel: MemoryKernel,
    lifecycle: SkillLifecycle,
    workspace: Path,
    skill_md: str = _GOOD_SKILL_MD,
) -> SkillLab:
    llm = _FakeSynthesizerLLM(skill_md=skill_md)
    synth = SkillSynthesizer(llm=llm)
    return SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=workspace / "candidates",
        installed_dir=workspace / "installed",
    )


# ── 1. Pipeline depuis un event Kernel — cas nominal ─────────────────────────


async def test_propose_from_event_good_skill_passes_sandbox(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Un event skill_candidate_proposal → SkillLab génère + teste en sandbox
    direct → SANDBOXED_PASS."""
    evt = kernel.log_event(
        type="skill_candidate_proposal",
        source="reflexion:proj_test",
        content="Générer plusieurs articles markdown structurés à partir d'un template",
        metadata={"project_id": "proj_test"},
    )
    lab = _make_lab(kernel, lifecycle, workspace, skill_md=_GOOD_SKILL_MD)

    record = await lab.propose_from_event(evt.id)
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_PASS
    assert record.source_event_id == evt.id

    # La candidate est sur disque, PAS dans installed/
    assert (workspace / "candidates" / "batch-articles" / "skill.py").exists()
    assert not (workspace / "installed" / "batch-articles").exists()


# ── 2. Cas REJET — skill volontairement cassée ───────────────────────────────


async def test_propose_from_event_skill_py_cassee_va_en_sandboxed_fail(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """On corrompt skill.py après génération → test sandbox direct doit échouer
    à l'import → SANDBOXED_FAIL → la skill N'EST PAS installable."""
    evt = kernel.log_event(
        type="skill_candidate_proposal",
        source="test",
        content="Skill à corrompre",
        metadata={},
    )
    # Construit un synthesizer qui produit un skill.py volontairement cassé
    # (au lieu du générateur standard). Le test sandbox doit attraper.
    llm = _FakeSynthesizerLLM(skill_md=_GOOD_SKILL_MD)
    synth = SkillSynthesizer(llm=llm)
    synth._generate_skill_py = lambda name: (  # noqa: ARG005
        "raise RuntimeError('skill volontairement cassée à l\\'import')\n"
    )
    lab2 = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=workspace / "candidates",
        installed_dir=workspace / "installed",
    )
    record = await lab2.propose_from_event(evt.id)
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_FAIL
    assert (record.sandbox_notes or "").lower().startswith("[import]")


# ── 3. GATE test-vert-sinon-rejet — promotion refusée si pas SANDBOXED_PASS ──


def test_promote_refuse_si_sandboxed_fail(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """CDC §7 anti-pattern : ne JAMAIS installer une skill sans test vert."""
    lab = _make_lab(kernel, lifecycle, workspace)
    # On simule directement : lifecycle marque la skill comme SANDBOXED_FAIL
    lifecycle.create_candidate(name="broken-skill")
    lifecycle.mark_sandbox_result(name="broken-skill", passed=False, notes="import error")
    record = lab.promote("broken-skill")
    assert record is None  # promotion refusée
    assert not (workspace / "installed" / "broken-skill").exists()


def test_promote_refuse_si_status_candidate(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Une candidate qui n'a même pas été testée ne peut pas être promue."""
    lab = _make_lab(kernel, lifecycle, workspace)
    lifecycle.create_candidate(name="untested")
    record = lab.promote("untested")
    assert record is None


def test_promote_success_apres_sandboxed_pass(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Une skill SANDBOXED_PASS peut être promue : candidate → installed."""
    lab = _make_lab(kernel, lifecycle, workspace)
    # Setup : crée la candidate sur disque + lifecycle SANDBOXED_PASS
    cand_dir = workspace / "candidates" / "ok-skill"
    cand_dir.mkdir(parents=True)
    (cand_dir / "skill.py").write_text("# placeholder\n")
    (cand_dir / "skill.yaml").write_text("name: ok-skill\n")
    lifecycle.create_candidate(name="ok-skill")
    lifecycle.mark_sandbox_result(name="ok-skill", passed=True, notes="ok")

    record = lab.promote("ok-skill")
    assert record is not None
    assert record.status == SkillStatus.ACTIVE
    # Dossier déplacé
    assert not cand_dir.exists()
    assert (workspace / "installed" / "ok-skill" / "skill.py").exists()


def test_promote_refuse_si_collision_installed(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Pas d'écrasement silencieux : si installed/{name}/ existe → refus."""
    lab = _make_lab(kernel, lifecycle, workspace)
    cand_dir = workspace / "candidates" / "collision"
    cand_dir.mkdir(parents=True)
    (cand_dir / "skill.py").write_text("# x\n")
    installed_dir = workspace / "installed" / "collision"
    installed_dir.mkdir(parents=True)
    (installed_dir / "skill.py").write_text("# existing\n")

    lifecycle.create_candidate(name="collision")
    lifecycle.mark_sandbox_result(name="collision", passed=True, notes="ok")

    record = lab.promote("collision")
    assert record is None
    # Aucun écrasement
    assert (installed_dir / "skill.py").read_text() == "# existing\n"


# ── 4. Polling idempotent ─────────────────────────────────────────────────────


async def test_scan_kernel_idempotent_sur_event_deja_traite(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Un event skill_candidate_proposal déjà traité ne re-déclenche pas la
    pipeline (économie LLM, pas d'écrasement)."""
    kernel.log_event(
        type="skill_candidate_proposal",
        source="test",
        content="Pattern X",
        metadata={},
    )
    lab = _make_lab(kernel, lifecycle, workspace)

    # 1er scan : génère la candidate
    r1 = await lab.scan_kernel()
    assert r1.events_examined == 1
    assert r1.candidates_generated == 1
    assert r1.skipped_already_handled == 0
    llm_calls_after_1 = lab._synthesizer._llm.calls

    # 2e scan : même event → skippé, pas de nouvelle génération
    r2 = await lab.scan_kernel()
    assert r2.events_examined == 1
    assert r2.candidates_generated == 0
    assert r2.skipped_already_handled == 1
    assert lab._synthesizer._llm.calls == llm_calls_after_1  # pas de nouvel appel LLM


async def test_scan_kernel_aucun_event(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Scan sans events skill_candidate_proposal → 0 examined, 0 generated."""
    lab = _make_lab(kernel, lifecycle, workspace)
    result = await lab.scan_kernel()
    assert result.events_examined == 0
    assert result.candidates_generated == 0


# ── 5. reject ────────────────────────────────────────────────────────────────


def test_reject_marque_rejected_sans_supprimer_fichiers(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Par défaut le rejet GARDE les fichiers candidats (audit)."""
    lab = _make_lab(kernel, lifecycle, workspace)
    cand_dir = workspace / "candidates" / "to-reject"
    cand_dir.mkdir(parents=True)
    (cand_dir / "skill.py").write_text("x = 1\n")
    lifecycle.create_candidate(name="to-reject")

    record = lab.reject("to-reject", reason="trop générique")
    assert record is not None
    assert record.status == SkillStatus.REJECTED
    assert cand_dir.exists()  # fichiers conservés


def test_reject_avec_delete_files(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    lab = _make_lab(kernel, lifecycle, workspace)
    cand_dir = workspace / "candidates" / "to-delete"
    cand_dir.mkdir(parents=True)
    (cand_dir / "skill.py").write_text("x = 1\n")
    lifecycle.create_candidate(name="to-delete")

    lab.reject("to-delete", delete_files=True)
    assert not cand_dir.exists()


# ── 6. Anti-pattern CDC §7 : test sandbox sur skill sans SkillBase ──────────


async def test_skill_sans_classe_skillbase_est_rejetee(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """Le test générique requiert au moins une classe subclass de SkillBase."""
    cand_dir = workspace / "candidates" / "no-class"
    cand_dir.mkdir(parents=True)
    (cand_dir / "skill.py").write_text("X = 1\n")  # pas de classe SkillBase
    (cand_dir / "skill.yaml").write_text("name: no-class\n")
    lifecycle.create_candidate(name="no-class")

    lab = _make_lab(kernel, lifecycle, workspace)
    record = await lab.test_in_sandbox("no-class")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_FAIL
    assert (
        "classe" in (record.sandbox_notes or "").lower()
        or "skillbase" in (record.sandbox_notes or "").lower()
    )


async def test_skill_system_prompt_vide_rejetee(
    workspace: Path, kernel: MemoryKernel, lifecycle: SkillLifecycle
) -> None:
    """get_system_prompt() doit retourner str non-vide. Skill avec SYSTEM_PROMPT=""
    → SANDBOXED_FAIL."""
    cand_dir = workspace / "candidates" / "empty-prompt"
    cand_dir.mkdir(parents=True)
    skill_py = (
        "from skills.base import SkillBase\n\n"
        "class EmptyPrompt(SkillBase):\n"
        "    SYSTEM_PROMPT = ''\n"
    )
    (cand_dir / "skill.py").write_text(skill_py)
    (cand_dir / "skill.yaml").write_text("name: empty-prompt\n")
    lifecycle.create_candidate(name="empty-prompt")

    lab = _make_lab(kernel, lifecycle, workspace)
    record = await lab.test_in_sandbox("empty-prompt")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_FAIL
    assert "system_prompt" in (record.sandbox_notes or "").lower()
