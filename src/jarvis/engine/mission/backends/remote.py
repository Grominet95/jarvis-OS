# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""RemoteBackend — stub pour les environnements serverless distants."""

from __future__ import annotations

from loguru import logger

from jarvis.engine.mission.backends.base import BackendResult, ExecutionBackend


class RemoteBackend(ExecutionBackend):
    """Stub pour les backends serverless distants (Modal, Daytona, Vercel Sandbox).

    Ce stub refuse toute exécution avec un message explicite d'implémentation requise.
    Pour une vraie intégration, sous-classez RemoteBackend et surchargez execute().

    Persistance serverless (hibernate quand idle) : pattern à implémenter dans
    la sous-classe en s'inspirant de hermes-agent providers/managed_modal.py
    et providers/daytona.py (MIT License, NousResearch — voir notices/exec-backends.md).
    """

    def __init__(self, provider: str = "modal") -> None:
        self._provider = provider

    @property
    def name(self) -> str:
        return f"RemoteBackend({self._provider})"

    async def is_available(self) -> bool:
        return False

    async def execute(self, command: str, timeout: int = 60) -> BackendResult:  # noqa: ASYNC109
        logger.warning(
            "RemoteBackend stub appelé — non implémenté",
            provider=self._provider,
            cmd=command[:60],
        )
        return BackendResult(
            success=False,
            stdout="",
            stderr=(
                f"RemoteBackend({self._provider}) non implémenté. "
                "Sous-classez RemoteBackend et surchargez execute() pour "
                "intégrer Modal, Daytona ou Vercel Sandbox."
            ),
            returncode=-1,
        )
