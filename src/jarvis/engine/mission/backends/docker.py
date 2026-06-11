"""DockerBackend — délègue l'exécution au DockerExecutor déjà démarré."""

from __future__ import annotations

from loguru import logger

from jarvis.engine.mission.backends.base import BackendResult, ExecutionBackend
from jarvis.engine.mission.docker_executor import DockerExecutor
from jarvis.kernel.settings import settings


class DockerBackend(ExecutionBackend):
    """Wraps un DockerExecutor existant (démarré par worker_agent ou externalement).

    Respecte tous les garde-fous de DockerExecutor :
    --rm, cap-drop ALL, no-new-privileges, mémoire et CPU limités.
    """

    def __init__(self, executor: object) -> None:
        self._executor = executor  # instance DockerExecutor

    async def is_available(self) -> bool:

        return settings.docker_enabled and await DockerExecutor.is_available()

    async def execute(self, command: str, timeout: int = 60) -> BackendResult:  # noqa: ASYNC109
        if not self._executor:
            logger.error("DockerBackend: executor non initialisé")
            return BackendResult(
                success=False,
                stdout="",
                stderr="DockerBackend : executor non démarré.",
                returncode=-1,
            )

        result: dict = await self._executor.execute(command, timeout)
        return BackendResult(
            success=result["success"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            returncode=result["returncode"],
        )
