"""
JarvisCollector — collecte l'état interne de Jarvis.
Missions en cours, mémoire récente, sessions récentes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.settings import settings


class JarvisCollector(CollectorBase):
    name = "jarvis"

    async def _collect(self) -> list[ContextItem]:
        items = []
        items.extend(self._collect_missions())
        items.extend(self._collect_memory_summary())
        return items

    def _collect_missions(self) -> list[ContextItem]:

        store = ProjectStore()
        projects = store.list_projects()

        items = []
        for project in projects[:10]:
            priority = Priority.HIGH if project.status == "running" else Priority.LOW
            items.append(
                ContextItem(
                    type=ItemType.MISSION,
                    title=f"Mission: {project.title}",
                    summary=f"Statut: {project.status} — {len(project.steps)} étapes",
                    raw=(
                        f"Mission '{project.title}' créée le {project.created_at}."
                        f" Statut: {project.status}."
                    ),
                    source="jarvis_agent",
                    timestamp=project.created_at,
                    priority=priority,
                    metadata={"project_id": project.id, "status": project.status},
                )
            )

        return items

    def _collect_memory_summary(self) -> list[ContextItem]:

        memory_file = Path(settings.memory_dir) / "MEMORY.md"
        if not memory_file.exists():
            return []

        content = memory_file.read_text(encoding="utf-8")

        return [
            ContextItem(
                type=ItemType.MEMORY,
                title="Contexte utilisateur (mémoire Jarvis)",
                summary="Index de la mémoire longue terme",
                raw=content[:2000],
                source="jarvis_memory",
                timestamp=datetime.now(),
                priority=Priority.MEDIUM,
            )
        ]
