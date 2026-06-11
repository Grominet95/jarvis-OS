"""Tests d'intégration Mission Engine (CDC §4).

Couvre :
- Plan refusé si un step n'a pas de success_criterion (§4.2)
- Persistance round-trip des nouveaux champs Step (§3.4) — reprise après crash
- Step bloque la progression si non vérifié (§4.4)
- Gate MODIFY_CORE / INSTALL_PACKAGE → approbation systématique (§4.5 + §9)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.engine.audit import AuditLog
from jarvis.engine.mission.governance import Governance
from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.mission.schemas import (
    Project,
    ProjectStatus,
    Step,
    StepStatus,
    validate_step,
)
from jarvis.engine.mission.verifier import VerificationResult, Verifier
from jarvis.engine.mission.worker_agent import WorkerAgent
from jarvis.engine.vocab import AccessLevel
from jarvis.kernel.approvals import ApprovalConfig, ApprovalMode
from jarvis.providers.llm.base import LLMProvider

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _NoOpLLM(LLMProvider):
    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        return "noop"

    async def health_check(self) -> bool:
        return True


class _FakeBudget:
    def __init__(self, enabled: bool = False, remaining: float = 1000.0) -> None:
        self._enabled = enabled
        self._remaining = remaining

    def remaining(self, scope: str) -> float:  # noqa: ARG002
        return self._remaining


def _make_governance(
    tmp_path: Path,
    mode_agent_mission: ApprovalMode = ApprovalMode.ALWAYS,
) -> Governance:
    cfg = ApprovalConfig()
    cfg.agent_mission = mode_agent_mission
    return Governance(
        approval_config=cfg,
        budget_guard=_FakeBudget(),
        audit_log=AuditLog(tmp_path / "audit.jsonl"),
    )


def _step(
    sid: str = "s1",
    criterion: str = "OK",
    access_level: AccessLevel = AccessLevel.WRITE_LOCAL,
) -> Step:
    return Step(
        id=sid,
        title=f"Step {sid}",
        description="desc",
        success_criterion=criterion,
        access_level=access_level,
    )


# ── 1. Plan refusé si un step n'a pas de success_criterion ─────────────────────


def test_validate_step_rejette_plan_avec_critere_manquant() -> None:
    """L'orchestrator REFUSE de lancer un plan dont un step n'a pas de critère (§4.2)."""
    bon = _step("s1", criterion="OK")
    mauvais = _step("s2", criterion="")

    validate_step(bon)  # ne lève pas
    with pytest.raises(ValueError, match="success_criterion"):
        validate_step(mauvais)


def test_validate_step_blancs_seuls_rejetes() -> None:
    """Critère composé uniquement d'espaces → rejet (cohérent avec PHASE 0)."""
    step = _step(criterion="   \t\n  ")
    with pytest.raises(ValueError, match="success_criterion"):
        validate_step(step)


# ── 2. Persistance round-trip des nouveaux champs Step (reprise après crash) ──


def test_persistance_step_roundtrip(tmp_path: Path) -> None:
    """Un projet sauvegardé puis rechargé conserve tous les nouveaux champs Step."""
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        store = ProjectStore()
        project = store.create_project(
            mission="Mission test",
            title="Test",
            timeout_minutes=10,
        )
        project.steps.append(
            Step(
                id="s1",
                title="Titre",
                description="desc",
                success_criterion="Fichier index.html non vide",
                verification_command="test -s index.html",
                access_level=AccessLevel.EXECUTE_CODE,
                verified=True,
                verification_notes="Vérifié couche déterministe",
                status=StepStatus.DONE,
            )
        )
        store.save_project(project)

        # Reload
        reloaded = store.load_project(project.id)
        assert reloaded is not None
        assert len(reloaded.steps) == 1
        s = reloaded.steps[0]
        assert s.success_criterion == "Fichier index.html non vide"
        assert s.verification_command == "test -s index.html"
        assert s.access_level == AccessLevel.EXECUTE_CODE
        assert s.verified is True
        assert s.verification_notes == "Vérifié couche déterministe"
        assert s.status == StepStatus.DONE


def test_persistance_projet_ancien_format_compat(tmp_path: Path) -> None:
    """Un projet sauvegardé AVANT PHASE 1 (sans les nouveaux champs) se recharge sans crash."""
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        # Simule un fichier d'état au format pré-PHASE-1
        project_id = "proj_old"
        workspace = tmp_path / project_id
        (workspace / ".jarvis").mkdir(parents=True)
        legacy_state = {
            "id": project_id,
            "title": "Vieux projet",
            "mission": "Une vieille mission",
            "status": "planning",
            "workspace_path": str(workspace),
            "timeout_minutes": 30,
            "created_at": "2026-05-01T12:00:00",
            "started_at": None,
            "completed_at": None,
            "llm_calls": 0,
            "files_created": [],
            "requires_network": False,
            "steps": [
                {
                    "id": "s1",
                    "title": "Vieille étape",
                    "description": "desc",
                    "status": "pending",
                    "requires_approval": False,
                    "output": None,
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                    # PAS de success_criterion, access_level, etc.
                }
            ],
        }
        (workspace / ".jarvis" / "state.json").write_text(
            json.dumps(legacy_state), encoding="utf-8"
        )

        store = ProjectStore()
        reloaded = store.load_project(project_id)
        assert reloaded is not None
        s = reloaded.steps[0]
        # Defaults appliqués via .get(...)
        assert s.success_criterion == ""
        assert s.verification_command is None
        assert s.access_level == AccessLevel.WRITE_LOCAL
        assert s.verified is False
        assert s.verification_notes is None


# ── 3. Step bloque la progression si non vérifié (§4.4) ───────────────────────


async def test_step_non_verifie_bloque_progression(tmp_path: Path) -> None:
    """Une mission avec 3 steps, le step 1 n'est pas vérifié → step 2 et 3 ne tournent pas.

    Test d'intégration : on injecte un verifier qui renvoie toujours verified=false,
    un gouvernance permissif, et un LLM no-op. Le worker doit FAILED le step 1
    après 2 essais (MAX_VERIFICATION_RETRIES) et arrêter la mission.
    """
    # Setup projet avec 3 steps
    # workspace_path doit correspondre à WORKSPACE_DIR/project_id pour que load_project marche.
    project_id = "proj_block"
    workspace = tmp_path / project_id
    workspace.mkdir()
    (workspace / ".jarvis").mkdir()
    project = Project(
        id=project_id,
        title="Test blocage",
        mission="Test",
        workspace_path=str(workspace),
        steps=[_step(f"s{i}", criterion=f"crit {i}") for i in range(1, 4)],
    )

    store = ProjectStore()
    # patcher WORKSPACE_DIR pour que claim_step écrive au bon endroit
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        store.save_project(project)

        # Fake verifier qui renvoie TOUJOURS verified=false
        class _AlwaysFailVerifier(Verifier):
            def __init__(self) -> None:
                pass  # pas d'init parent

            async def verify(
                self, project: Project, step: Step, files_before: list[str]
            ) -> VerificationResult:
                return VerificationResult(
                    verified=False,
                    layer="semantic",
                    issues=["fake failure"],
                    notes="Toujours faux",
                )

        # Approval callback : refuse tout (ne devrait pas être appelé ici car gate=auto)
        async def _approval_cb(pid: str, sid: str, desc: str) -> bool:
            return True

        # Broadcast no-op
        broadcasts: list[dict] = []

        def _broadcast(evt: dict) -> None:
            broadcasts.append(evt)

        # Mock _run_step_llm pour éviter l'appel LLM réel
        async def _fake_llm_run(
            self: WorkerAgent,
            step: Step,
            prev_issues: list[str] | None = None,
            attempt: int = 0,
        ) -> str:
            step.output = f"fake output try {attempt}"
            return f"fake output try {attempt}"

        worker = WorkerAgent(
            project=project,
            store=store,
            broadcast_event=_broadcast,
            approval_callback=_approval_cb,
            llm=_NoOpLLM(),
            governance=_make_governance(tmp_path),
            verifier=_AlwaysFailVerifier(),
        )

        with patch.object(WorkerAgent, "_run_step_llm", _fake_llm_run):
            with patch.object(WorkerAgent, "_setup_environment", _async_noop):
                await worker.run()

        # Vérifications : step 1 FAILED, steps 2 et 3 toujours PENDING
        reloaded = store.load_project(project.id)
        assert reloaded is not None
        assert reloaded.status == ProjectStatus.FAILED
        assert reloaded.steps[0].status == StepStatus.FAILED
        assert "Vérification" in (reloaded.steps[0].error or "")
        assert reloaded.steps[1].status == StepStatus.PENDING
        assert reloaded.steps[2].status == StepStatus.PENDING


async def _async_noop(self: WorkerAgent) -> None:
    return None


# ── 4. Gate refuse MODIFY_CORE / INSTALL_PACKAGE en mission ──────────────────


async def test_step_modify_core_declenche_approval_systematique(tmp_path: Path) -> None:
    """Un step MODIFY_CORE ne peut JAMAIS s'auto-exécuter (§4.5 + §9)."""
    # workspace_path doit correspondre à WORKSPACE_DIR/project_id pour que load_project marche.
    project_id = "proj_core"
    workspace = tmp_path / project_id
    workspace.mkdir()
    (workspace / ".jarvis").mkdir()
    project = Project(
        id=project_id,
        title="MC test",
        mission="Test",
        workspace_path=str(workspace),
        steps=[_step("s1", criterion="OK", access_level=AccessLevel.MODIFY_CORE)],
    )

    store = ProjectStore()
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        store.save_project(project)

        # Approval callback : refuse → le step doit être SKIPPED
        approval_calls: list[str] = []

        async def _approval_cb(pid: str, sid: str, desc: str) -> bool:
            approval_calls.append(sid)
            return False  # refuse

        worker = WorkerAgent(
            project=project,
            store=store,
            broadcast_event=lambda _: None,
            approval_callback=_approval_cb,
            llm=_NoOpLLM(),
            governance=_make_governance(tmp_path),
        )

        with patch.object(WorkerAgent, "_setup_environment", _async_noop):
            await worker.run()

        reloaded = store.load_project(project.id)
        assert reloaded is not None
        assert reloaded.steps[0].status == StepStatus.SKIPPED
        assert "s1" in approval_calls  # gate a déclenché la demande


async def test_step_never_categorie_failed_sans_demande(tmp_path: Path) -> None:
    """Catégorie NEVER → REFUSED → step FAILED immédiatement (pas de demande humaine)."""
    # workspace_path doit correspondre à WORKSPACE_DIR/project_id pour que load_project marche.
    project_id = "proj_never"
    workspace = tmp_path / project_id
    workspace.mkdir()
    (workspace / ".jarvis").mkdir()
    project = Project(
        id=project_id,
        title="NEVER test",
        mission="Test",
        workspace_path=str(workspace),
        steps=[_step("s1", criterion="OK", access_level=AccessLevel.READ_ONLY)],
    )

    store = ProjectStore()
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        store.save_project(project)

        approval_calls: list[str] = []

        async def _approval_cb(pid: str, sid: str, desc: str) -> bool:
            approval_calls.append(sid)
            return True  # serait approuvé, mais le gate ne demande pas

        gov = _make_governance(tmp_path, mode_agent_mission=ApprovalMode.NEVER)
        worker = WorkerAgent(
            project=project,
            store=store,
            broadcast_event=lambda _: None,
            approval_callback=_approval_cb,
            llm=_NoOpLLM(),
            governance=gov,
        )

        with patch.object(WorkerAgent, "_setup_environment", _async_noop):
            await worker.run()

        reloaded = store.load_project(project.id)
        assert reloaded is not None
        assert reloaded.steps[0].status == StepStatus.FAILED
        assert "REFUSED" in (reloaded.steps[0].error or "")
        assert approval_calls == []  # Aucune demande à l'humain : refus déterministe


# ── 5. Reprise — un step DONE n'est pas re-exécuté ────────────────────────────


async def test_reprise_skip_steps_deja_done(tmp_path: Path) -> None:
    """Un step DONE ou SKIPPED est sauté à la reprise (run() existante)."""
    # workspace_path doit correspondre à WORKSPACE_DIR/project_id pour que load_project marche.
    project_id = "proj_resume"
    workspace = tmp_path / project_id
    workspace.mkdir()
    (workspace / ".jarvis").mkdir()
    s1 = _step("s1", criterion="OK")
    s1.status = StepStatus.DONE
    s1.verified = True
    s2 = _step("s2", criterion="OK")
    project = Project(
        id=project_id,
        title="Resume test",
        mission="Test",
        workspace_path=str(workspace),
        steps=[s1, s2],
    )

    store = ProjectStore()
    with patch("jarvis.engine.mission.project_store.WORKSPACE_DIR", tmp_path):
        store.save_project(project)

        executions: list[str] = []

        async def _fake_llm_run(
            self: WorkerAgent,
            step: Step,
            prev_issues: list[str] | None = None,
            attempt: int = 0,
        ) -> str:
            executions.append(step.id)
            step.output = "done"
            return "done"

        class _AlwaysPassVerifier(Verifier):
            def __init__(self) -> None:
                pass

            async def verify(
                self, project: Project, step: Step, files_before: list[str]
            ) -> VerificationResult:
                return VerificationResult(verified=True, layer="semantic", notes="OK")

        worker = WorkerAgent(
            project=project,
            store=store,
            broadcast_event=lambda _: None,
            approval_callback=_no_approval_cb,
            llm=_NoOpLLM(),
            governance=_make_governance(tmp_path),
            verifier=_AlwaysPassVerifier(),
        )

        with patch.object(WorkerAgent, "_run_step_llm", _fake_llm_run):
            with patch.object(WorkerAgent, "_setup_environment", _async_noop):
                await worker.run()

        # s1 (DONE) sauté, s2 exécuté
        assert executions == ["s2"]


async def _no_approval_cb(pid: str, sid: str, desc: str) -> bool:
    return True
