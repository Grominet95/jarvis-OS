# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Outil execute_preset — permet à Jarvis de lancer un preset."""

from __future__ import annotations

from jarvis.capabilities.skills.executor import PresetExecutor
from jarvis.capabilities.skills.registry import skill_registry
from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.capabilities.tools.registry import ToolRegistry
from jarvis.kernel.contracts import TTSEngine
from jarvis.kernel.notifications import broadcast_event


class ExecutePresetTool(Tool):
    name = "execute_preset"
    description = (
        "Lance un preset Jarvis — séquence d'actions automatisées.\n\n"
        "Utilise cet outil quand l'utilisateur demande de lancer un preset "
        "dont tu connais le nom (via les SYSTEM_PROMPT des skills de type preset).\n\n"
        "Exemples :\n"
        '- "lance le mode streameur" → execute_preset(preset_name="mode-streameur")\n'
        '- "mode travail" → execute_preset(preset_name="mode-travail")\n'
        '- "bonne nuit" → execute_preset(preset_name="mode-nuit")'
    )
    input_schema = {  # noqa: RUF012
        "type": "object",
        "properties": {
            "preset_name": {
                "type": "string",
                "description": "Nom du preset à lancer (slug kebab-case)",
            }
        },
        "required": ["preset_name"],
    }

    def __init__(self, *, tool_registry: ToolRegistry, tts_engine: TTSEngine) -> None:
        self._tool_registry = tool_registry
        self._tts_engine = tts_engine

    async def execute(self, preset_name: str, **_: object) -> ToolResult:
        preset = skill_registry.get_preset(preset_name)

        if not preset:
            return ToolResult(
                content=f"Preset '{preset_name}' introuvable ou non installée",
                is_error=True,
            )

        executor = PresetExecutor(
            tool_registry=self._tool_registry,
            tts_engine=self._tts_engine,
        )

        results = await executor.execute(preset, broadcast_fn=broadcast_event)

        done = results["steps_done"]
        skipped = results["steps_skipped"]
        failed = results["steps_failed"]

        msg = f"Preset '{preset_name}' exécutée — {done} étapes réalisées"
        if skipped:
            msg += f", {skipped} ignorées (plateforme)"
        if failed:
            msg += f", {failed} en erreur"

        return ToolResult(content=msg)
