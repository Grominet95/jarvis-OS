"""
Outils de délégation — sous-agent isolé et exécution de script via RPC.

SpawnSubagentTool : délègue un workstream à un sous-agent ISOLÉ (contexte propre).
ScriptRPCTool    : execute un script Python qui appelle les outils via RPC —
                   un pipeline de N appels = un seul tour LLM (zéro coût contexte).

Inspiré de hermes-agent delegate_tool.py et execute_code.py
(MIT License, NousResearch — voir notices/exec-backends.md).
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.capabilities.tools.registry import ToolRegistry
from jarvis.engine.agent import Agent
from jarvis.engine.mission.backend_factory import get_backend
from jarvis.engine.mission.backends.rpc import ScriptRPCRunner
from jarvis.kernel.approval import get_approval_checker
from jarvis.kernel.schemas import Session


class SpawnSubagentTool(Tool):
    """Délègue un workstream à un sous-agent ISOLÉ avec son propre contexte.

    Le parent ne reçoit qu'un résumé compact — aucune contamination de contexte.
    La session du sous-agent est fraîche (aucun historique hérité du parent).

    Restriction : la récursion (sous-agent spawne un sous-agent) est possible
    mais déconseillée. Limitez la profondeur côté prompt.
    """

    name = "spawn_subagent"
    description = (
        "Délègue une tâche à un sous-agent isolé avec son propre contexte. "
        "Retourne un résumé compact. "
        "Utilise pour les workstreams parallèles ou les tâches longues "
        "sans polluer le contexte courant."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Description complète de la tâche à déléguer.",
            },
            "context": {
                "type": "string",
                "description": "Contexte additionnel optionnel pour le sous-agent.",
            },
        },
        "required": ["task"],
    }

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def execute(self, task: str, context: str = "") -> ToolResult:  # type: ignore[override]

        prompt = f"{context}\n\n---\nTâche : {task}" if context else task
        session = Session()
        session.add_message("user", prompt)

        logger.info("SpawnSubagent démarré", task=task[:60])
        try:
            # Tool loop complet sur une session fraîche = contexte totalement isolé
            result = await self._agent.respond_tools(session)
            summary = str(result)[:2000]
            logger.info("SpawnSubagent terminé", chars=len(summary))
            return ToolResult(content=f"[Sous-agent terminé]\n{summary}")
        except Exception as exc:
            logger.error("SpawnSubagent erreur", error=str(exc))
            return ToolResult(
                content=f"[Sous-agent erreur] {exc}",
                is_error=True,
            )


class ScriptRPCTool(Tool):
    """Exécute un script Python dans le sandbox avec accès aux outils Jarvis via RPC.

    Un pipeline de N appels d'outils = un seul tour LLM.
    Le script importe `jarvis_tools` (stub généré) pour appeler les outils.
    Seul le stdout remonte au LLM — les résultats intermédiaires n'entrent
    jamais dans le contexte.

    Tout dispatch d'outil passe par le backend sandboxé + approval_checker.
    """

    name = "execute_script"
    description = (
        "Exécute un script Python dans le sandbox. "
        "Le script peut appeler `import jarvis_tools` pour chaîner des outils. "
        "Idéal pour les pipelines multi-étapes : N appels d'outils = 1 seul tour LLM. "
        "Seul le stdout final remonte — les résultats intermédiaires sont hors contexte."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": (
                    "Script Python à exécuter. "
                    "Peut `import jarvis_tools` puis appeler les fonctions disponibles."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout en secondes (défaut 300).",
                "default": 300,
            },
        },
        "required": ["script"],
    }

    def __init__(
        self,
        tool_registry: ToolRegistry,
        workspace_path: str | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._workspace_path = workspace_path

    async def execute(self, script: str, timeout: int = 300) -> ToolResult:  # type: ignore[override]  # noqa: ASYNC109

        checker = get_approval_checker()
        if checker:
            approved = await checker.check(
                "code_write",
                f"Script RPC : {script[:80]}…",
                f"script-rpc-{uuid.uuid4().hex[:8]}",
            )
            if not approved:
                return ToolResult(content="Exécution de script refusée.", is_error=True)

        # Workspace : injecté à la construction ou répertoire temporaire
        if self._workspace_path:
            workspace = Path(self._workspace_path)
        else:
            workspace = Path(tempfile.mkdtemp(prefix="jarvis-rpc-"))

        backend = get_backend(str(workspace))
        if backend is None:
            return ToolResult(
                content=(
                    "Aucun backend disponible pour l'exécution de script. "
                    "Activez DOCKER_ENABLED ou ALLOW_UNSANDBOXED_EXEC."
                ),
                is_error=True,
            )

        runner = ScriptRPCRunner(backend, self._tool_registry, workspace)
        logger.info("ScriptRPCTool démarré", script_len=len(script))

        result = await runner.run(script, timeout=timeout)

        parts = [
            f"succès={result['success']}  appels_outils={result['tool_calls']}",
        ]
        if result["stderr"]:
            parts.append(f"stderr:\n{result['stderr'][:500]}")
        if result["stdout"]:
            parts.append(result["stdout"])

        return ToolResult(
            content="\n".join(parts),
            is_error=not result["success"],
        )
