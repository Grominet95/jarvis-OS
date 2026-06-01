"""ABC ExecutionBackend — contrat partagé par tous les backends d'exécution."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class BackendResult(TypedDict):
    """Résultat normalisé retourné par tous les backends d'exécution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


class ExecutionBackend(ABC):
    """Interface commune pour les backends d'exécution de Jarvis.

    Chaque backend implémente execute() et is_available().
    Le résultat est toujours un BackendResult normalisé, compatible avec
    les dict retournés historiquement par WorkerCLITool et DockerExecutor.
    """

    @abstractmethod
    async def execute(self, command: str, timeout: int = 60) -> BackendResult:  # noqa: ASYNC109
        """Exécute une commande et retourne un BackendResult normalisé."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Retourne True si ce backend est opérationnel dans l'environnement courant."""
        ...

    @property
    def name(self) -> str:
        """Nom lisible du backend (logs)."""
        return self.__class__.__name__
