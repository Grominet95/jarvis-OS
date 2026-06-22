# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
ContextBuilder — fusionne toutes les sources en un état du monde cohérent.
Identifie les connexions entre les domaines (email ↔ calendar ↔ tasks ↔ missions).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from jarvis.engine.proactive.collectors.calendar import CalendarCollector
from jarvis.engine.proactive.collectors.email import EmailCollector
from jarvis.engine.proactive.collectors.jarvis import JarvisCollector
from jarvis.engine.proactive.collectors.news import NewsCollector
from jarvis.engine.proactive.collectors.tasks import TaskCollector
from jarvis.engine.proactive.collectors.weather import WeatherCollector
from jarvis.engine.proactive.schemas import CollectionResult, ContextItem, ItemType, Priority
from jarvis.kernel.contracts import CalendarReadTool, NotionReadTool


@dataclass
class WorldState:
    """L'état du monde à un instant T — prêt pour l'InitiativeGenerator."""

    collected_at: datetime
    collection: CollectionResult

    email_summary: str = ""
    calendar_summary: str = ""
    tasks_summary: str = ""
    news_summary: str = ""
    jarvis_summary: str = ""
    weather_summary: str = ""

    cross_domain_connections: list[str] = field(default_factory=list)
    tensions: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Formate l'état du monde pour injection dans un prompt LLM."""
        sections = []

        if self.email_summary:
            sections.append(f"## EMAILS\n{self.email_summary}")
        if self.calendar_summary:
            sections.append(f"## AGENDA\n{self.calendar_summary}")
        if self.tasks_summary:
            sections.append(f"## TÂCHES\n{self.tasks_summary}")
        if self.jarvis_summary:
            sections.append(f"## MISSIONS JARVIS\n{self.jarvis_summary}")
        if self.weather_summary:
            sections.append(f"## MÉTÉO\n{self.weather_summary}")
        if self.news_summary:
            sections.append(f"## ACTUALITÉS PERTINENTES\n{self.news_summary}")
        if self.cross_domain_connections:
            connections_text = "\n".join(f"- {c}" for c in self.cross_domain_connections)
            sections.append(f"## CONNEXIONS DÉTECTÉES\n{connections_text}")

        return "\n\n".join(sections)


class ContextBuilder:
    def __init__(
        self,
        calendar_tool: CalendarReadTool,
        notion_tool: NotionReadTool,
    ) -> None:
        self._collectors = [
            EmailCollector(),
            CalendarCollector(calendar_tool=calendar_tool),
            TaskCollector(notion_tool=notion_tool),
            NewsCollector(),
            JarvisCollector(),
            WeatherCollector(),
        ]

    async def build(self) -> WorldState:
        """Lance tous les collecteurs en parallèle et construit l'état du monde."""
        logger.info("ContextBuilder: collecting from all sources")

        tasks = [collector.collect() for collector in self._collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[ContextItem] = []
        errors = {}

        for collector, result in zip(self._collectors, results, strict=False):
            if isinstance(result, Exception):
                errors[collector.name] = str(result)
                logger.error(f"Collector {collector.name} error: {result}")
            else:
                all_items.extend(result)

        collection = CollectionResult(items=all_items, collected_at=datetime.now(), errors=errors)

        state = WorldState(collected_at=datetime.now(), collection=collection)

        state.email_summary = self._summarize_emails(collection.by_type(ItemType.EMAIL))
        state.calendar_summary = self._summarize_calendar(collection.by_type(ItemType.EVENT))
        state.tasks_summary = self._summarize_tasks(collection.by_type(ItemType.TASK))
        weather_items = [i for i in collection.by_type(ItemType.NEWS) if i.source == "weather"]
        news_items = [i for i in collection.by_type(ItemType.NEWS) if i.source != "weather"]
        state.weather_summary = self._summarize_weather(weather_items)
        state.news_summary = self._summarize_news(news_items)
        state.jarvis_summary = self._summarize_jarvis(
            collection.by_type(ItemType.MISSION) + collection.by_type(ItemType.MEMORY)
        )
        state.cross_domain_connections = self._detect_connections(collection)

        logger.info(
            f"ContextBuilder: {len(all_items)} items collectés, "
            f"{len(state.cross_domain_connections)} connexions détectées"
        )

        return state

    def _summarize_emails(self, emails: list[ContextItem]) -> str:
        if not emails:
            return "Aucun email important."

        high = [e for e in emails if e.priority == Priority.HIGH]
        medium = [e for e in emails if e.priority == Priority.MEDIUM]

        lines = []
        if high:
            lines.append(f"HAUTE PRIORITÉ ({len(high)}) :")
            for e in high:
                lines.append(f"  - {e.metadata.get('from', '?')} : {e.title}")
                lines.append(f"    → {e.summary}")
        if medium:
            lines.append(f"Autres ({len(medium)}) :")
            for e in medium[:5]:
                lines.append(f"  - {e.title}")

        return "\n".join(lines)

    def _summarize_calendar(self, events: list[ContextItem]) -> str:
        if not events:
            return "Agenda libre dans les 48h."
        return "\n".join(f"  - {e.title}" for e in events[:8])

    def _summarize_tasks(self, tasks: list[ContextItem]) -> str:
        if not tasks:
            return "Aucune tâche en cours."
        return "\n".join(f"  - {t.title}" for t in tasks[:10])

    def _summarize_weather(self, items: list[ContextItem]) -> str:
        if not items:
            return ""
        return "\n".join(i.summary for i in items)

    def _summarize_news(self, news: list[ContextItem]) -> str:
        if not news:
            return "Aucune actualité pertinente."
        return "\n".join(f"  - [{n.source}] {n.title}" for n in news[:8])

    def _summarize_jarvis(self, items: list[ContextItem]) -> str:
        if not items:
            return "Aucune mission en cours."
        return "\n".join(f"  - {i.title}: {i.summary}" for i in items[:5])

    def _detect_connections(self, collection: CollectionResult) -> list[str]:
        """
        Heuristique simple de connexions cross-domain.
        Le LLM fera la vraie analyse dans l'InitiativeGenerator.
        """
        connections = []

        emails = collection.by_type(ItemType.EMAIL)
        tasks = collection.by_type(ItemType.TASK)

        stop_words = {"le", "la", "les", "de", "du", "un", "une", "en", "et", "à"}

        for email in emails:
            email_words = set(email.title.lower().split()) - stop_words
            for task in tasks:
                task_words = set(task.title.lower().split()) - stop_words
                common = email_words & task_words
                if len(common) >= 2:
                    connections.append(
                        f"Email '{email.title[:40]}' semble lié à la tâche '{task.title[:40]}'"
                    )

        return connections[:5]
