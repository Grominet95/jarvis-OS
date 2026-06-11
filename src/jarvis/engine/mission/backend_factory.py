"""Factory `get_backend()` — sélection runtime du backend d'exécution.

Engine-aware : instancie les classes `DockerBackend/LocalBackend/SSHBackend/
RemoteBackend` de `jarvis.engine.mission.backends`. La configuration (type
sélectionné, paramètres SSH) vient de `jarvis.kernel.backends` (loader pur).

Migré depuis l'ancien shim racine `config/backends.py::get_backend` en
Phase F.7. Le split kernel↔engine casse le cycle RÈGLE 2 attrapé par le
4e contrat import-linter (`capabilities.tools.subagent → config.backends →
jarvis.engine.mission.backends`).
"""

from __future__ import annotations

from loguru import logger

from jarvis.engine.mission.backends import (
    DockerBackend,
    LocalBackend,
    RemoteBackend,
    SSHBackend,
)
from jarvis.kernel.backends import BackendType, load_backends_config
from jarvis.kernel.settings import settings


def get_backend(
    workspace_path: str,
    docker_executor: object | None = None,
) -> object | None:
    """Retourne l'ExecutionBackend configuré pour ce workspace.

    Retourne None si aucun backend sûr n'est disponible.
    Le docker_executor (si fourni) doit être déjà démarré.
    """

    config = load_backends_config()

    if config.default_backend in (BackendType.AUTO, BackendType.DOCKER):
        if docker_executor is not None and settings.docker_enabled:
            return DockerBackend(docker_executor)

        if config.default_backend == BackendType.DOCKER:
            logger.error(
                "Backend DOCKER configuré mais non disponible "
                "(docker_executor=None ou docker_enabled=False)"
            )
            return None

        return LocalBackend(workspace_path)

    if config.default_backend == BackendType.LOCAL:
        return LocalBackend(workspace_path)

    if config.default_backend == BackendType.SSH:
        ssh = config.ssh
        if not ssh.host or not ssh.user:
            logger.error("Backend SSH : host ou user manquant dans config/backends.json")
            return None
        return SSHBackend(ssh.host, ssh.user, ssh.port, ssh.key_path, ssh.remote_workdir)

    if config.default_backend == BackendType.REMOTE:
        return RemoteBackend(config.remote_provider)

    return None
