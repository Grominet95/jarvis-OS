"""Outil execute_routine — permet à Jarvis de lancer une routine."""
from __future__ import annotations

from tools.base import Tool, ToolResult


class ExecuteRoutineTool(Tool):
    name = "execute_routine"
    description = (
        "Lance une routine Jarvis — séquence d'actions automatisées.\n\n"
        "Utilise cet outil quand l'utilisateur demande de lancer une routine "
        "dont tu connais le nom (via les SYSTEM_PROMPT des skills de type routine).\n\n"
        "Exemples :\n"
        '- "lance le mode streameur" → execute_routine(routine_name="mode-streameur")\n'
        '- "mode travail" → execute_routine(routine_name="mode-travail")\n'
        '- "bonne nuit" → execute_routine(routine_name="mode-nuit")'
    )
    input_schema = {
        "type": "object",
        "properties": {
            "routine_name": {
                "type": "string",
                "description": "Nom de la routine à lancer (slug kebab-case)",
            }
        },
        "required": ["routine_name"],
    }

    async def execute(self, routine_name: str, **_) -> ToolResult:
        from skills.registry import skill_registry
        from skills.executor import RoutineExecutor
        from audio.tts import tts_engine
        from core.gateway import get_tool_registry
        from background.notifications import broadcast_event

        routine = skill_registry.get_routine(routine_name)

        if not routine:
            return ToolResult(
                content=f"Routine '{routine_name}' introuvable ou non installée",
                is_error=True,
            )

        executor = RoutineExecutor(
            tool_registry=get_tool_registry(),
            tts_engine=tts_engine,
        )

        results = await executor.execute(routine, broadcast_fn=broadcast_event)

        done = results["steps_done"]
        skipped = results["steps_skipped"]
        failed = results["steps_failed"]

        msg = f"Routine '{routine_name}' exécutée — {done} étapes réalisées"
        if skipped:
            msg += f", {skipped} ignorées (plateforme)"
        if failed:
            msg += f", {failed} en erreur"

        return ToolResult(content=msg)
