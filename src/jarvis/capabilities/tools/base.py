# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class Tool(ABC):
    """Base class pour tous les outils Jarvis.

    Chaque sous-classe définit name, description, input_schema comme attributs de classe
    (ou d'instance pour les outils à description dynamique comme CLIRunnerTool).
    """

    name: str = ""
    description: str = ""
    input_schema: dict = {}  # noqa: RUF012

    def to_claude_schema(self) -> dict:
        """Retourne le schéma au format attendu par l'API Anthropic."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    @abstractmethod
    async def execute(self, **kwargs: object) -> ToolResult: ...
