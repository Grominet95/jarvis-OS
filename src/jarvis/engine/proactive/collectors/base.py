# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger

from jarvis.engine.proactive.schemas import ContextItem
from jarvis.kernel.connectivity import is_offline_mode


class CollectorBase(ABC):
    name: str = "base"

    async def collect(self) -> list[ContextItem]:
        """Point d'entrée principal. Gère les erreurs proprement."""

        try:
            items = await self._collect()
            logger.debug(f"Collector {self.name}: {len(items)} items")
            return items
        except Exception as e:
            if is_offline_mode():
                logger.debug(f"Collector {self.name} ignoré — mode local ({type(e).__name__})")
            else:
                logger.error(f"Collector {self.name} failed: {e}")
            return []

    @abstractmethod
    async def _collect(self) -> list[ContextItem]:
        """Implémenter dans chaque sous-classe."""
