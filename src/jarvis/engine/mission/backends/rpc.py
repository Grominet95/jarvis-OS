"""Pattern script-via-RPC : un pipeline multi-étapes = un seul tour LLM.

Architecture (transport fichiers — fonctionne local ET Docker via volume monté) :
  1. Génère jarvis_tools.py (stubs RPC) dans rpc_dir à l'intérieur du workspace
  2. Lance le script utilisateur dans le backend sandboxé
  3. Dispatcher asyncio poll-lit les request files et dispatche via tool_registry
  4. Seul le stdout du script remonte au LLM — résultats intermédiaires hors contexte

Sécurité :
  - Seul un sous-ensemble safe (RPC_ALLOWED_TOOLS) est exposé dans le sandbox
  - Tout dispatch passe par approval_checker si configuré
  - Le backend reste sandboxé (Docker ou opt-in local)

Inspiré de hermes-agent code_execution_tool.py (MIT License, NousResearch).
Voir notices/exec-backends.md pour l'attribution complète.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
import uuid
from pathlib import Path

from loguru import logger

from jarvis.engine.approval_checker import get_approval_checker
from jarvis.engine.mission.backends.base import ExecutionBackend
from jarvis.kernel.contracts import ToolRegistry

# Sous-ensemble d'outils exposés dans le sandbox RPC.
# Intersection avec les outils enregistrés au moment de l'exécution.
RPC_ALLOWED_TOOLS: frozenset[str] = frozenset(
    [
        "weather",
        "browser",
        "read_file",
        "find_files",
        "calendar_list",
        "memory_search",
        "cli_runner",
        "execute_cli",
    ]
)

_STUB_TEMPLATE = textwrap.dedent("""\
    \"\"\"Stub jarvis_tools — généré par ScriptRPCRunner. Ne pas modifier.\"\"\"
    import json as _json, os as _os, time as _time, uuid as _uuid

    _RPC_DIR = {rpc_dir!r}
    _CALL_TIMEOUT = 60


    def _call(tool_name, **kwargs):
        req_id = _uuid.uuid4().hex
        req_path = _os.path.join(_RPC_DIR, f"req_{{req_id}}.json")
        res_path = _os.path.join(_RPC_DIR, f"res_{{req_id}}.json")
        with open(req_path, "w") as _f:
            _json.dump({{"tool": tool_name, "inputs": kwargs}}, _f)
        deadline = _time.monotonic() + _CALL_TIMEOUT
        while _time.monotonic() < deadline:
            if _os.path.exists(res_path):
                with open(res_path) as _f:
                    return _json.load(_f)
            _time.sleep(0.05)
        raise TimeoutError(f"RPC timeout pour {{tool_name}} ({{_CALL_TIMEOUT}}s)")


{stubs}
""")


def _build_stub(rpc_dir: str, tools: list[str]) -> str:
    """Génère le module jarvis_tools.py avec une fonction par outil."""
    lines = [
        f"def {name}(**kwargs):\n    return _call({name!r}, **kwargs)\n" for name in sorted(tools)
    ]
    return _STUB_TEMPLATE.format(rpc_dir=rpc_dir, stubs="\n".join(lines))


class ScriptRPCRunner:
    """Exécute un script Python via le backend sandbox avec bridge RPC vers tool_registry.

    Pattern "zéro coût de contexte" : N appels d'outils = 1 seul tour LLM.
    """

    MAX_TOOL_CALLS = 50
    MAX_STDOUT_BYTES = 50_000

    def __init__(
        self,
        backend: ExecutionBackend,
        tool_registry: ToolRegistry,
        workspace: Path,
    ) -> None:
        self._backend = backend
        self._registry = tool_registry
        self._workspace = workspace

    async def run(
        self,
        script: str,
        timeout: int = 300,  # noqa: ASYNC109
        allowed_tools: frozenset[str] | None = None,
    ) -> dict:
        """
        Exécute script dans le backend avec stubs jarvis_tools disponibles.

        Retourne {"stdout", "stderr", "success", "tool_calls"}.
        """
        if allowed_tools is None:
            registered = frozenset(t["name"] for t in self._registry.schemas())
            allowed_tools = RPC_ALLOWED_TOOLS & registered

        run_id = uuid.uuid4().hex[:8]
        rpc_dir = self._workspace / ".jarvis_rpc" / run_id
        rpc_dir.mkdir(parents=True, exist_ok=True)

        # Chemin du rpc_dir tel que vu depuis le backend.
        # Pour Docker : workspace → /workspace (volume monté).
        backend_rpc = str(rpc_dir).replace(str(self._workspace), "/workspace")

        (rpc_dir / "jarvis_tools.py").write_text(
            _build_stub(backend_rpc, list(allowed_tools)),
            encoding="utf-8",
        )
        (rpc_dir / "user_script.py").write_text(
            f"import sys\nsys.path.insert(0, {backend_rpc!r})\n{script}",
            encoding="utf-8",
        )

        tool_call_count = [0]  # liste mutable pour closure

        async def _dispatcher() -> None:
            while True:
                for req_path in sorted(rpc_dir.glob("req_*.json")):
                    req_id = req_path.stem[4:]  # "req_<id>" → "<id>"
                    res_path = rpc_dir / f"res_{req_id}.json"
                    if res_path.exists():
                        continue  # déjà traité

                    try:
                        data = json.loads(req_path.read_text())
                        tool_name = data["tool"]
                        inputs = data.get("inputs", {})

                        if tool_name not in allowed_tools:
                            response = {
                                "error": f"Outil non autorisé dans le sandbox RPC : {tool_name}"
                            }
                        elif tool_call_count[0] >= self.MAX_TOOL_CALLS:
                            response = {"error": "Quota d'appels RPC atteint"}
                        else:
                            checker = get_approval_checker()
                            if checker:
                                approved = await checker.check(
                                    "code_write",
                                    f"Script RPC → {tool_name}",
                                    f"rpc-{run_id}-{req_id}",
                                )
                                if not approved:
                                    response = {
                                        "error": f"Appel {tool_name} refusé par l'utilisateur"
                                    }
                                else:
                                    tool_call_count[0] += 1
                                    result = await self._registry.call(tool_name, inputs)
                                    response = {
                                        "result": result.content,
                                        "is_error": result.is_error,
                                    }
                            else:
                                tool_call_count[0] += 1
                                result = await self._registry.call(tool_name, inputs)
                                response = {
                                    "result": result.content,
                                    "is_error": result.is_error,
                                }
                    except Exception as exc:
                        logger.warning("RPC dispatch error", error=str(exc))
                        response = {"error": str(exc)}

                    res_path.write_text(json.dumps(response), encoding="utf-8")
                    req_path.unlink(missing_ok=True)

                await asyncio.sleep(0.05)

        dispatch_task = asyncio.create_task(_dispatcher())
        script_path = f"{backend_rpc}/user_script.py"

        try:
            result = await self._backend.execute(
                f"python3 {script_path}",
                timeout=timeout,
            )
        finally:
            dispatch_task.cancel()
            try:
                await dispatch_task
            except asyncio.CancelledError:
                pass
            shutil.rmtree(rpc_dir, ignore_errors=True)

        return {
            "success": result["success"],
            "stdout": result["stdout"][: self.MAX_STDOUT_BYTES],
            "stderr": result["stderr"],
            "tool_calls": tool_call_count[0],
        }
