"""Système d'approbation par catégorie — loader kernel.

Chaque catégorie peut être : "always", "ask", "never"
  always → Jarvis exécute sans demander
  ask    → Demande confirmation avant d'exécuter
  never  → Refuse d'exécuter cette catégorie

Loader pur : dataclass + JSON persisté dans `CONFIG_DIR / "approvals.json"`
(chemin absolu via `kernel.paths`, robuste au cwd). Migré depuis le shim
racine `config/approvals.py` en Phase F.7 (RÈGLE 4 import-linter).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum

from jarvis.kernel.paths import CONFIG_DIR


class ApprovalMode(StrEnum):
    ALWAYS = "always"
    ASK = "ask"
    NEVER = "never"


@dataclass
class ApprovalConfig:
    """Configuration des approbations par catégorie."""

    system_shutdown: ApprovalMode = ApprovalMode.ASK
    system_restart: ApprovalMode = ApprovalMode.ASK

    file_read: ApprovalMode = ApprovalMode.ALWAYS
    file_write: ApprovalMode = ApprovalMode.ASK
    file_delete: ApprovalMode = ApprovalMode.ASK

    app_launch: ApprovalMode = ApprovalMode.ALWAYS
    app_close: ApprovalMode = ApprovalMode.ALWAYS

    web_search: ApprovalMode = ApprovalMode.ALWAYS
    web_navigate: ApprovalMode = ApprovalMode.ALWAYS
    web_agent: ApprovalMode = ApprovalMode.ASK

    email_draft: ApprovalMode = ApprovalMode.ALWAYS
    email_send: ApprovalMode = ApprovalMode.ASK

    code_write: ApprovalMode = ApprovalMode.ASK
    agent_mission: ApprovalMode = ApprovalMode.ALWAYS

    printer_slice: ApprovalMode = ApprovalMode.ASK
    printer_print: ApprovalMode = ApprovalMode.ASK
    fusion_create: ApprovalMode = ApprovalMode.ALWAYS
    fusion_modify: ApprovalMode = ApprovalMode.ASK
    fusion_delete: ApprovalMode = ApprovalMode.ASK

    smart_home_read: ApprovalMode = ApprovalMode.ALWAYS
    smart_home_write: ApprovalMode = ApprovalMode.ALWAYS


CONFIG_FILE = CONFIG_DIR / "approvals.json"


def load_approval_config() -> ApprovalConfig:
    """Charge depuis CONFIG_DIR/approvals.json. Crée avec défauts si absent."""
    if not CONFIG_FILE.exists():
        config = ApprovalConfig()
        save_approval_config(config)
        return config

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return ApprovalConfig(
            **{
                k: ApprovalMode(v)
                for k, v in data.items()
                if hasattr(ApprovalConfig, k) and isinstance(v, str)
            }
        )
    except Exception:
        return ApprovalConfig()


def save_approval_config(config: ApprovalConfig) -> None:
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


approval_config = load_approval_config()
