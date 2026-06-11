"""Configuration des backends d'exécution — loader kernel.

Chaque backend peut être : auto | docker | local | ssh | remote
  auto   → Docker si disponible, sinon Local avec opt-in requis
  docker → Container Docker isolé (recommandé en production)
  local  → Hôte direct (ALLOW_UNSANDBOXED_EXEC=true requis)
  ssh    → Hôte distant SSH (host + user requis dans la config)
  remote → Serverless (Modal / Daytona — stub)

Loader pur : dataclass + JSON persisté dans `CONFIG_DIR / "backends.json"`.
La factory engine-aware `get_backend()` qui instancie DockerBackend/LocalBackend/…
a été déplacée dans `jarvis.engine.mission.backend_factory` en Phase F.7 —
elle ne peut pas vivre ici (RÈGLE 1 : kernel ne dépend pas d'engine).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from loguru import logger

from jarvis.kernel.paths import CONFIG_DIR


class BackendType(StrEnum):
    """Type de backend d'exécution sélectionnable."""

    AUTO = "auto"
    DOCKER = "docker"
    LOCAL = "local"
    SSH = "ssh"
    REMOTE = "remote"


@dataclass
class SSHConfig:
    """Paramètres de connexion pour le backend SSH."""

    host: str = ""
    user: str = ""
    port: int = 22
    key_path: str = ""
    remote_workdir: str = "~/jarvis-workspace"


@dataclass
class BackendsConfig:
    """Configuration globale des backends d'exécution."""

    default_backend: BackendType = BackendType.AUTO
    ssh: SSHConfig = field(default_factory=SSHConfig)
    remote_provider: str = "modal"


_CONFIG_FILE = CONFIG_DIR / "backends.json"


def load_backends_config() -> BackendsConfig:
    """Charge depuis CONFIG_DIR/backends.json. Crée avec valeurs par défaut si absent."""
    if not _CONFIG_FILE.exists():
        cfg = BackendsConfig()
        save_backends_config(cfg)
        return cfg

    try:
        raw = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        ssh_raw = raw.pop("ssh", {})
        bt = BackendType(raw.get("default_backend", BackendType.AUTO))
        ssh_cfg = SSHConfig(**{k: v for k, v in ssh_raw.items() if hasattr(SSHConfig, k)})
        return BackendsConfig(
            default_backend=bt,
            ssh=ssh_cfg,
            remote_provider=raw.get("remote_provider", "modal"),
        )
    except Exception:
        logger.warning("config/backends.json illisible — utilisation des valeurs par défaut")
        return BackendsConfig()


def save_backends_config(config: BackendsConfig) -> None:
    """Persiste la configuration dans CONFIG_DIR/backends.json."""
    _CONFIG_FILE.parent.mkdir(exist_ok=True)
    data = asdict(config)
    data["default_backend"] = str(config.default_backend)
    _CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


backends_config: BackendsConfig = load_backends_config()
