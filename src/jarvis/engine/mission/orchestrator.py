"""ProjectOrchestrator — point d'entrée central pour créer, suivre et tuer les projets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from loguru import logger

from jarvis.engine.budget import BudgetGuard
from jarvis.engine.mission.file_tool import SandboxedFileTool
from jarvis.engine.mission.project_manager import ProjectManager
from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.mission.reflexion import Reflexion
from jarvis.engine.mission.schemas import (
    LogEntry,
    Project,
    ProjectStatus,
    StepStatus,
    validate_step,
)
from jarvis.engine.mission.worker_agent import WorkerAgent
from jarvis.kernel.contracts import LLMProvider
from jarvis.kernel.events import EventBus


class ProjectOrchestrator:
    """Gère le cycle de vie complet des projets agents.

    Phase C : `store` et `manager` injectés au constructeur (auparavant
    `ProjectStore()` et `ProjectManager()` instanciés en interne).
    `broadcast_event`, `budget_guard`, `reflexion` étaient déjà injectés
    en pré-C. `WorkerAgent(...)` et `SandboxedFileTool(...)` restent
    instanciés par-projet (pas des dépendances globales — légitime).
    """

    def __init__(
        self,
        broadcast_event: Callable[[dict], None],
        store: ProjectStore,
        manager: ProjectManager,
        worker_llm: LLMProvider,
        budget_guard: BudgetGuard | None = None,
        reflexion: Reflexion | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._broadcast = broadcast_event
        self._budget = budget_guard
        self._reflexion = reflexion  # PHASE 2 — gardée pour le code legacy (cf. WorkerAgent)
        self._store = store
        self._manager = manager
        self._worker_llm = worker_llm
        self._bus = bus
        self._workers: dict[str, WorkerAgent] = {}
        self._pending_approvals: dict[str, asyncio.Future[bool]] = {}

    # ── Création & lancement ──────────────────────────────────────────────────

    async def create_and_run(self, mission: str, timeout_minutes: int = 30) -> Project:
        """Crée le projet (appel LLM de planification) et lance le worker en background.

        PHASE 1 §4.2 — refuse de lancer un plan dont un step n'a pas de success_criterion.
        """
        project = await self._manager.create_project(mission, timeout_minutes)

        # Validation du plan : chaque step DOIT porter un success_criterion vérifiable.
        try:
            for step in project.steps:
                validate_step(step)
        except ValueError as exc:
            project.status = ProjectStatus.FAILED
            self._store.save_project(project)
            logger.error(
                "Plan refusé — step sans success_criterion",
                project_id=project.id,
                error=str(exc),
            )
            self._broadcast(
                {
                    "type": "project_plan_invalid",
                    "project_id": project.id,
                    "error": str(exc),
                }
            )
            raise

        worker = WorkerAgent(
            project=project,
            store=self._store,
            broadcast_event=self._broadcast,
            approval_callback=self._request_approval,
            llm=self._worker_llm,
            budget_guard=self._budget,
            reflexion=self._reflexion,
            bus=self._bus,
        )
        self._workers[project.id] = worker

        # Push initial vers le dashboard
        self._broadcast(
            {
                "type": "project_created",
                "project": self._project_summary(project),
            }
        )

        asyncio.create_task(
            asyncio.wait_for(worker.run(), timeout=project.timeout_minutes * 60),
            name=f"worker-{project.id}",
        )

        logger.info("Project launched", id=project.id, steps=len(project.steps))
        return project

    # ── Kill switch ───────────────────────────────────────────────────────────

    def kill(self, project_id: str) -> bool:
        worker = self._workers.get(project_id)
        if not worker:
            return False
        worker.kill()
        return True

    # ── Retry ─────────────────────────────────────────────────────────────────

    async def retry_project(self, project_id: str) -> Project | None:
        """Remet le projet en running depuis la première étape bloquée/failed."""

        # Tuer le worker actuel si encore vivant
        if w := self._workers.get(project_id):
            w.kill()

        project = self._store.load_project(project_id)
        if not project:
            return None

        # Remettre les étapes "running", "failed" (et "pending" déjà ok) en pending
        reset = False
        for step in project.steps:
            if step.status in (StepStatus.RUNNING, StepStatus.FAILED):
                step.status = StepStatus.PENDING
                step.error = None
                step.output = None
                step.started_at = None
                step.completed_at = None
                if not reset:
                    reset = True

        project.status = ProjectStatus.RUNNING
        self._store.save_project(project)

        worker = WorkerAgent(
            project=project,
            store=self._store,
            broadcast_event=self._broadcast,
            approval_callback=self._request_approval,
            llm=self._worker_llm,
            budget_guard=self._budget,
            reflexion=self._reflexion,
            bus=self._bus,
        )
        self._workers[project_id] = worker

        self._broadcast(
            {
                "type": "project_update",
                "project": self._project_summary(project),
            }
        )

        asyncio.create_task(
            asyncio.wait_for(worker.run(), timeout=project.timeout_minutes * 60),
            name=f"retry-{project_id}",
        )
        logger.info("Project retried", id=project_id)
        return project

    # ── Reprise après pause budget ────────────────────────────────────────────

    async def resume_project(self, project_id: str) -> Project | None:
        """Reprend un projet en pause budgétaire sans réinitialiser les étapes déjà DONE.

        Contrairement à retry_project, cette méthode ne touche pas aux étapes DONE/SKIPPED
        et ne réinitialise que le statut global du projet.
        """

        if w := self._workers.get(project_id):
            w.kill()

        project = self._store.load_project(project_id)
        if not project:
            return None

        if not self._store.is_resumable(project):
            logger.warning("Projet non reprennable", id=project_id, status=project.status)
            return None

        project.status = ProjectStatus.RUNNING
        self._store.save_project(project)

        worker = WorkerAgent(
            project=project,
            store=self._store,
            broadcast_event=self._broadcast,
            approval_callback=self._request_approval,
            llm=self._worker_llm,
            budget_guard=self._budget,
            reflexion=self._reflexion,
            bus=self._bus,
        )
        self._workers[project_id] = worker

        self._broadcast(
            {
                "type": "project_update",
                "project": self._project_summary(project),
            }
        )

        asyncio.create_task(
            asyncio.wait_for(worker.run(), timeout=project.timeout_minutes * 60),
            name=f"resume-{project_id}",
        )
        logger.info("Project resumed from budget pause", id=project_id)
        return project

    # ── Approval system ───────────────────────────────────────────────────────

    async def _request_approval(self, project_id: str, step_id: str, description: str) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        key = f"{project_id}:{step_id}"
        self._pending_approvals[key] = future

        self._broadcast(
            {
                "type": "approval_request",
                "project_id": project_id,
                "step_id": step_id,
                "description": description,
                "approval_key": key,
            }
        )

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=600)
        except TimeoutError:
            self._pending_approvals.pop(key, None)
            logger.warning("Approval timeout", key=key)
            return False

    def resolve_approval(self, project_id: str, step_id: str, approved: bool) -> bool:
        key = f"{project_id}:{step_id}"
        future = self._pending_approvals.pop(key, None)
        if future and not future.done():
            future.set_result(approved)
            return True
        return False

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_project(self, project_id: str) -> Project | None:
        return self._store.load_project(project_id)

    def list_projects(self) -> list[Project]:
        return self._store.list_projects()

    def get_logs(self, project_id: str, last_n: int = 200) -> list[LogEntry]:
        project = self._store.load_project(project_id)
        if not project:
            return []
        return self._store.get_logs(project, last_n)

    def get_workspace_files(self, project_id: str) -> list[str]:

        project = self._store.load_project(project_id)
        if not project:
            return []
        return SandboxedFileTool(project.workspace_path).list_files()

    def read_workspace_file(self, project_id: str, path: str) -> str:

        project = self._store.load_project(project_id)
        if not project:
            raise FileNotFoundError(f"Projet non trouvé : {project_id}")
        return SandboxedFileTool(project.workspace_path).read_file(path)

    # ── Serialization helpers ─────────────────────────────────────────────────

    @staticmethod
    def _project_summary(project: Project) -> dict:
        done = sum(1 for s in project.steps if s.status == "done")
        total = len(project.steps)
        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "steps_done": done,
            "steps_total": total,
            "progress": round(done / total * 100) if total else 0,
            "timeout_minutes": project.timeout_minutes,
            "created_at": project.created_at.isoformat(),
            "steps": [
                {
                    "id": s.id,
                    "title": s.title,
                    "status": s.status,
                    "requires_approval": s.requires_approval,
                    "output": s.output,
                    "error": s.error,
                }
                for s in project.steps
            ],
        }
