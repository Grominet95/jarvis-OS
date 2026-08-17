# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.error_collector import collector

_TOOL_CODES: dict[str, str] = {
    "spotify": "JRV-TOL-002",
    "gmail": "JRV-TOL-003",
    "browser": "JRV-TOL-004",
    "notion": "JRV-TOL-005",
    "calendar": "JRV-TOL-006",
    "cli_runner": "JRV-TOL-007",
    "execute_cli": "JRV-TOL-007",
    "filesystem": "JRV-TOL-008",
    "vision": "JRV-TOL-009",
    "fusion360": "JRV-TOL-010",
    "memory": "JRV-TOL-011",
    "weather": "JRV-TOL-012",
    "subagent": "JRV-TOL-013",
    "map_control": "JRV-TOL-014",
}

_DEFAULT_TOOL_CODE = "JRV-TOL-001"


def _tool_code(name: str) -> str:
    key = name.lower()
    for prefix, code in _TOOL_CODES.items():
        if key == prefix or key.startswith(prefix):
            return code
    return _DEFAULT_TOOL_CODE


def _prefix_error_content(code: str, content: str) -> str:
    if content.startswith("[JRV-"):
        return content
    return f"[{code}] {content}"


class ToolRegistry:
    """Registre central de tous les outils disponibles pour Jarvis."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._skill_tool_names: set[str] = set()

    def register(self, *tools: Tool) -> None:
        for tool in tools:
            self._tools[tool.name] = tool
            logger.debug("Tool registered", name=tool.name)

    def replace_skill_tools(self, *tools: Tool) -> None:
        """Remplace atomiquement les outils venant des skills."""
        for name in list(self._skill_tool_names):
            self._tools.pop(name, None)
        self._skill_tool_names = set()
        for tool in tools:
            self._tools[tool.name] = tool
            self._skill_tool_names.add(tool.name)
            logger.debug("Skill tool registered", name=tool.name)
        logger.info(f"Skill tools sync: {len(tools)} outil(s)")

    def has_tools(self) -> bool:
        return bool(self._tools)

    def schemas(self) -> list[dict]:
        """Retourne les schémas Claude de tous les outils enregistrés."""
        return [t.to_claude_schema() for t in self._tools.values()]

    def core_schemas(self) -> list[dict]:
        """Retourne uniquement les schémas des outils natifs (hors skills)."""
        return [
            t.to_claude_schema()
            for name, t in self._tools.items()
            if name not in self._skill_tool_names
        ]

    async def call(self, name: str, inputs: dict) -> ToolResult:
        """Exécute un outil par nom. Retourne une ToolResult d'erreur si inconnu."""
        tool = self._tools.get(name)
        code = _tool_code(name)
        if tool is None:
            logger.warning("Unknown tool called", name=name)
            collector.error(code, f"Unknown tool: {name}")
            return ToolResult(
                content=_prefix_error_content(code, f"Outil inconnu: {name}"),
                is_error=True,
            )
        try:
            result = await tool.execute(**inputs)
            if result.is_error:
                collector.error(code, f"Tool {name} returned error")
                return ToolResult(
                    content=_prefix_error_content(code, result.content),
                    is_error=True,
                )
            logger.info("Tool executed", name=name, is_error=result.is_error)
            return result
        except Exception as e:
            collector.error(code, f"Tool {name} failed", cause=e)
            logger.error("Tool execution error", name=name, error=str(e))
            return ToolResult(
                content=_prefix_error_content(code, f"Erreur outil {name}: {e}"),
                is_error=True,
            )

    async def call_str(self, name: str, inputs: dict) -> str:
        result = await self.call(name, inputs)
        if result.is_error:
            return result.content
        return result.content
