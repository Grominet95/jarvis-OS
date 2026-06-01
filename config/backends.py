"""
Sélection et configuration des backends d'exécution de Jarvis.

Chaque backend peut être : auto | docker | local | ssh | remote
  auto   → Docker si disponible, sinon Local avec opt-in requis (comportement historique)
  docker → Container Docker isolé (recommandé en production)
  local  → Hôte direct (ALLOW_UNSANDBOXED_EXEC=true requis)
  ssh    → Hôte distant SSH (host + user requis dans la config)
  remote → Serverless (Modal / Daytona — stub, nécessite une sous-classe)

Pattern identique à config/approvals.py : dataclass + JSON persisté.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from loguru import logger


class BackendType(StrEnum):
    """Type de backend d'exécution sélectionnable."""

    AUTO   = "auto"
    DOCKER = "docker"
    LOCAL  = "local"
    SSH    = "ssh"
    REMOTE = "remote"


@dataclass
class SSHConfig:
    """Paramètres de connexion pour le backend SSH."""

    host: str         = ""
    user: str         = ""
    port: int         = 22
    key_path: str     = ""
    remote_workdir: str = "~/jarvis-workspace"


@dataclass
class BackendsConfig:
    """Configuration globale des backends d'exécution."""

    default_backend: BackendType = BackendType.AUTO
    ssh: SSHConfig               = field(default_factory=SSHConfig)
    remote_provider: str         = "modal"


_CONFIG_FILE = Path("config/backends.json")


def load_backends_config() -> BackendsConfig:
    """Charge depuis config/backends.json. Crée avec valeurs par défaut si absent."""
    if not _CONFIG_FILE.exists():
        cfg = BackendsConfig()
        save_backends_config(cfg)
        return cfg

    try:
        raw     = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        ssh_raw = raw.pop("ssh", {})
        bt      = BackendType(raw.get("default_backend", BackendType.AUTO))
        ssh_cfg = SSHConfig(**{k: v for k, v in ssh_raw.items() if hasattr(SSHConfig, k)})
        return BackendsConfig(
            default_backend  = bt,
            ssh              = ssh_cfg,
            remote_provider  = raw.get("remote_provider", "modal"),
        )
    except Exception:
        logger.warning("config/backends.json illisible — utilisation des valeurs par défaut")
        return BackendsConfig()


def save_backends_config(config: BackendsConfig) -> None:
    """Persiste la configuration dans config/backends.json."""
    _CONFIG_FILE.parent.mkdir(exist_ok=True)
    data = asdict(config)
    data["default_backend"] = str(config.default_backend)
    _CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_backend(
    workspace_path: str,
    docker_executor: object | None = None,
) -> object | None:
    """
    Retourne l'ExecutionBackend configuré pour ce workspace.

    Retourne None si aucun backend sûr n'est disponible.
    Le docker_executor (si fourni) doit être déjà démarré (DockerExecutor.start() appelé).
    """
    from agent.backends import DockerBackend, LocalBackend, RemoteBackend, SSHBackend
    from config.settings import settings

    config = load_backends_config()

    # ── AUTO ou DOCKER ───────────────────────────────────────────────────────
    if config.default_backend in (BackendType.AUTO, BackendType.DOCKER):
        if docker_executor is not None and settings.docker_enabled:
            return DockerBackend(docker_executor)

        if config.default_backend == BackendType.DOCKER:
            # Docker explicitement demandé mais indisponible → refus
            logger.error(
                "Backend DOCKER configuré mais non disponible "
                "(docker_executor=None ou docker_enabled=False)"
            )
            return None

        # AUTO sans Docker → fallback Local (is_available() vérifiera l'opt-in)
        return LocalBackend(workspace_path)

    # ── LOCAL ────────────────────────────────────────────────────────────────
    if config.default_backend == BackendType.LOCAL:
        return LocalBackend(workspace_path)

    # ── SSH ──────────────────────────────────────────────────────────────────
    if config.default_backend == BackendType.SSH:
        ssh = config.ssh
        if not ssh.host or not ssh.user:
            logger.error("Backend SSH : host ou user manquant dans config/backends.json")
            return None
        return SSHBackend(ssh.host, ssh.user, ssh.port, ssh.key_path, ssh.remote_workdir)

    # ── REMOTE ───────────────────────────────────────────────────────────────
    if config.default_backend == BackendType.REMOTE:
        return RemoteBackend(config.remote_provider)

    return None


# Instance globale (chargée à l'import comme approval_config)
backends_config: BackendsConfig = load_backends_config()
