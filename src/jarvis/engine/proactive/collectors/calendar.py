# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
CalendarCollector — récupère les événements des prochaines 48h.
Réutilise le tool calendar existant.
"""

from __future__ import annotations

from datetime import datetime

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.contracts import CalendarReadTool


class CalendarCollector(CollectorBase):
    name = "calendar"

    def __init__(self, calendar_tool: CalendarReadTool) -> None:
        self._calendar_tool = calendar_tool

    async def _collect(self) -> list[ContextItem]:
        result = await self._calendar_tool.execute(days_ahead=2)

        if result.is_error:
            return []

        items = []
        now = datetime.now()

        lines = result.content.split("\n") if result.content else []
        for line in lines:
            if not line.strip():
                continue

            priority = Priority.MEDIUM
            if "aujourd'hui" in line.lower() or "dans" in line.lower():
                priority = Priority.HIGH

            items.append(
                ContextItem(
                    type=ItemType.EVENT,
                    title=line.strip(),
                    summary=line.strip(),
                    raw=line.strip(),
                    source="google_calendar",
                    timestamp=now,
                    priority=priority,
                )
            )

        return items
