"""LocalBackend — exécution directe sur l'hôte dans le workspace (opt-in explicite)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from jarvis.engine.mission.backends.base import BackendResult, ExecutionBackend
from jarvis.kernel.settings import settings


class LocalBackend(ExecutionBackend):
    """Exécution directe dans le workspace hôte.

    Requiert allow_unsandboxed_exec=True dans les settings — refuse sinon.
    La validation whitelist/blacklist reste à la charge de WorkerCLITool en amont.
    """

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path).resolve()

    async def is_available(self) -> bool:

        return bool(getattr(settings, "allow_unsandboxed_exec", False))

    async def execute(self, command: str, timeout: int = 60) -> BackendResult:  # noqa: ASYNC109

        if not getattr(settings, "allow_unsandboxed_exec", False):
            logger.error("LocalBackend: opt-in manquant (ALLOW_UNSANDBOXED_EXEC absent/false)")
            return BackendResult(
                success=False,
                stdout="",
                stderr=(
                    "Exécution directe refusée : ALLOW_UNSANDBOXED_EXEC non activé. "
                    "Activez Docker (DOCKER_ENABLED=true, recommandé) "
                    "ou passez ALLOW_UNSANDBOXED_EXEC=true (déconseillé)."
                ),
                returncode=-1,
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            logger.debug("LocalBackend exec", cmd=command[:60], rc=proc.returncode)
            return BackendResult(
                success=proc.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace")[:8000],
                stderr=stderr.decode("utf-8", errors="replace")[:2000],
                returncode=proc.returncode,
            )
        except TimeoutError:
            return BackendResult(
                success=False,
                stdout="",
                stderr=f"Timeout après {timeout}s",
                returncode=-1,
            )
        except Exception as exc:
            return BackendResult(
                success=False,
                stdout="",
                stderr=str(exc),
                returncode=-1,
            )
