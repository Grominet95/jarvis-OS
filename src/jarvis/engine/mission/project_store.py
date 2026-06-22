# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Persistance des projets sur disque — JSONL pour les logs, JSON pour l'état."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from jarvis.engine.mission.schemas import LogEntry, Project, ProjectStatus, Step, StepStatus
from jarvis.engine.vocab import AccessLevel
from jarvis.kernel.file_lock import exclusive_file_lock
from jarvis.kernel.paths import WORKSPACE_DIR as _WORKSPACE

WORKSPACE_DIR = _WORKSPACE / "projects"


class ProjectStore:
    def __init__(self) -> None:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    def create_project(self, mission: str, title: str, timeout_minutes: int = 30) -> Project:
        project_id = f"proj_{uuid.uuid4().hex[:6]}"
        workspace = WORKSPACE_DIR / project_id
        (workspace / ".jarvis").mkdir(parents=True, exist_ok=True)

        project = Project(
            id=project_id,
            title=title,
            mission=mission,
            workspace_path=str(workspace.resolve()),
            timeout_minutes=timeout_minutes,
        )
        self.save_project(project)
        return project

    def save_project(self, project: Project) -> None:
        state_file = Path(project.workspace_path) / ".jarvis" / "state.json"
        state_file.write_text(
            json.dumps(self._to_dict(project), indent=2, default=str),
            encoding="utf-8",
        )

    def load_project(self, project_id: str) -> Project | None:
        state_file = WORKSPACE_DIR / project_id / ".jarvis" / "state.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return self._from_dict(data)
        except Exception:
            return None

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        for state_file in WORKSPACE_DIR.glob("*/.jarvis/state.json"):
            project = self.load_project(state_file.parent.parent.name)
            if project:
                projects.append(project)
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def append_log(self, project: Project, entry: LogEntry) -> None:
        log_file = Path(project.workspace_path) / ".jarvis" / "logs.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": entry.timestamp.isoformat(),
                        "level": entry.level,
                        "msg": entry.message,
                        "step_id": entry.step_id,
                        "data": entry.data,
                    }
                )
                + "\n"
            )

    def get_logs(self, project: Project, last_n: int = 200) -> list[LogEntry]:
        log_file = Path(project.workspace_path) / ".jarvis" / "logs.jsonl"
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        entries: list[LogEntry] = []
        for line in lines[-last_n:]:
            try:
                d = json.loads(line)
                entries.append(
                    LogEntry(
                        timestamp=datetime.fromisoformat(d["ts"]),
                        level=d["level"],
                        message=d["msg"],
                        step_id=d.get("step_id"),
                        data=d.get("data"),
                    )
                )
            except Exception:
                pass
        return entries

    # ── Claim atomique (anti-double-exécution) ────────────────────────────────

    def claim_step(self, project_id: str, step_id: str, worker_id: str) -> bool:
        """Réclame atomiquement une étape pour un worker.

        Utilise flock(LOCK_EX) pour garantir l'exclusivité entre processus.
        Retourne False si l'étape est déjà réclamée par un autre worker.
        """
        jarvis_dir = WORKSPACE_DIR / project_id / ".jarvis"
        jarvis_dir.mkdir(parents=True, exist_ok=True)
        claims_file = jarvis_dir / "step_claims.json"
        lock_path = jarvis_dir / "claims.lock"

        with exclusive_file_lock(lock_path):
            claims: dict[str, str] = {}
            if claims_file.exists():
                try:
                    claims = json.loads(claims_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if step_id in claims:
                return False

            claims[step_id] = worker_id
            claims_file.write_text(json.dumps(claims, indent=2), encoding="utf-8")
            return True

    def release_step_claim(self, project_id: str, step_id: str) -> None:
        """Libère le claim d'une étape (budget pause ou fin normale)."""
        claims_file = WORKSPACE_DIR / project_id / ".jarvis" / "step_claims.json"
        lock_path = WORKSPACE_DIR / project_id / ".jarvis" / "claims.lock"
        if not claims_file.exists():
            return

        with exclusive_file_lock(lock_path):
            claims: dict[str, str] = {}
            try:
                claims = json.loads(claims_file.read_text(encoding="utf-8"))
            except Exception:
                pass
            claims.pop(step_id, None)
            claims_file.write_text(json.dumps(claims, indent=2), encoding="utf-8")

    # ── Pause / reprise budget ─────────────────────────────────────────────────

    def pause_for_budget(self, project: Project, current_step_id: str | None) -> None:
        """Met le projet en pause budgétaire.

        L'étape en cours repasse à PENDING pour pouvoir être reprise.
        Libère son claim pour qu'un futur worker puisse la réclamer.
        """
        for step in project.steps:
            if step.id == current_step_id and step.status == StepStatus.RUNNING:
                step.status = StepStatus.PENDING
                step.started_at = None
                step.error = None
                break

        project.status = ProjectStatus.PAUSED
        self.save_project(project)

        if current_step_id:
            self.release_step_claim(project.id, current_step_id)

    def is_resumable(self, project: Project) -> bool:
        """Vrai si le projet est en pause et possède des étapes PENDING à exécuter."""
        if project.status != ProjectStatus.PAUSED:
            return False
        return any(s.status == StepStatus.PENDING for s in project.steps)

    # ── Sérialisation ─────────────────────────────────────────────────────────

    def _to_dict(self, project: Project) -> dict:
        return {
            "id": project.id,
            "title": project.title,
            "mission": project.mission,
            "status": project.status,
            "workspace_path": project.workspace_path,
            "timeout_minutes": project.timeout_minutes,
            "created_at": project.created_at.isoformat(),
            "started_at": project.started_at.isoformat() if project.started_at else None,
            "completed_at": project.completed_at.isoformat() if project.completed_at else None,
            "llm_calls": project.llm_calls,
            "files_created": project.files_created,
            "requires_network": project.requires_network,
            "steps": [
                {
                    "id": s.id,
                    "title": s.title,
                    "description": s.description,
                    "status": s.status,
                    "requires_approval": s.requires_approval,
                    "output": s.output,
                    "error": s.error,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    # PHASE 1 — champs de vérification & gouvernance (§3.4)
                    "success_criterion": s.success_criterion,
                    "verification_command": s.verification_command,
                    "access_level": int(s.access_level),
                    "verified": s.verified,
                    "verification_notes": s.verification_notes,
                }
                for s in project.steps
            ],
        }

    def _from_dict(self, d: dict) -> Project:
        steps = [
            Step(
                id=s["id"],
                title=s["title"],
                description=s["description"],
                status=StepStatus(s["status"]),
                requires_approval=s.get("requires_approval", False),
                output=s.get("output"),
                error=s.get("error"),
                started_at=datetime.fromisoformat(s["started_at"]) if s.get("started_at") else None,
                completed_at=datetime.fromisoformat(s["completed_at"])
                if s.get("completed_at")
                else None,
                # PHASE 1 — champs PHASE 0 ajoutés ; `.get(...)` pour les projets antérieurs.
                success_criterion=s.get("success_criterion", ""),
                verification_command=s.get("verification_command"),
                access_level=AccessLevel(s.get("access_level", int(AccessLevel.WRITE_LOCAL))),
                verified=s.get("verified", False),
                verification_notes=s.get("verification_notes"),
            )
            for s in d.get("steps", [])
        ]
        return Project(
            id=d["id"],
            title=d["title"],
            mission=d["mission"],
            status=ProjectStatus(d["status"]),
            steps=steps,
            workspace_path=d["workspace_path"],
            timeout_minutes=d.get("timeout_minutes", 30),
            created_at=datetime.fromisoformat(d["created_at"]),
            started_at=datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None,
            completed_at=datetime.fromisoformat(d["completed_at"])
            if d.get("completed_at")
            else None,
            llm_calls=d.get("llm_calls", 0),
            files_created=d.get("files_created", []),
            requires_network=d.get("requires_network", False),
        )
