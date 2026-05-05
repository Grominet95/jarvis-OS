"""
Système d'approbation par catégorie.
Chaque catégorie peut être : "always", "ask", "never"
  always → Jarvis exécute sans demander
  ask    → Demande confirmation avant d'exécuter
  never  → Refuse d'exécuter cette catégorie
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class ApprovalMode(StrEnum):
    ALWAYS = "always"
    ASK    = "ask"
    NEVER  = "never"


@dataclass
class ApprovalConfig:
    """Configuration des approbations par catégorie."""

    # Système
    system_shutdown: ApprovalMode = ApprovalMode.ASK
    system_restart:  ApprovalMode = ApprovalMode.ASK

    # Fichiers
    file_read:   ApprovalMode = ApprovalMode.ALWAYS
    file_write:  ApprovalMode = ApprovalMode.ASK
    file_delete: ApprovalMode = ApprovalMode.ASK

    # Applications
    app_launch: ApprovalMode = ApprovalMode.ALWAYS
    app_close:  ApprovalMode = ApprovalMode.ALWAYS

    # Web
    web_search:   ApprovalMode = ApprovalMode.ALWAYS
    web_navigate: ApprovalMode = ApprovalMode.ALWAYS
    web_agent:    ApprovalMode = ApprovalMode.ASK

    # Communications
    email_draft: ApprovalMode = ApprovalMode.ALWAYS
    email_send:  ApprovalMode = ApprovalMode.ASK

    # Code / Agent
    code_write:    ApprovalMode = ApprovalMode.ASK
    agent_mission: ApprovalMode = ApprovalMode.ALWAYS

    # Matériel
    printer_slice:  ApprovalMode = ApprovalMode.ASK
    printer_print:  ApprovalMode = ApprovalMode.ASK
    fusion_create:  ApprovalMode = ApprovalMode.ALWAYS
    fusion_modify:  ApprovalMode = ApprovalMode.ASK
    fusion_delete:  ApprovalMode = ApprovalMode.ASK

    # Domotique
    smart_home_read:  ApprovalMode = ApprovalMode.ALWAYS
    smart_home_write: ApprovalMode = ApprovalMode.ALWAYS


CONFIG_FILE = Path("config/approvals.json")


def load_approval_config() -> ApprovalConfig:
    """Charge depuis config/approvals.json. Crée avec défauts si absent."""
    if not CONFIG_FILE.exists():
        config = ApprovalConfig()
        save_approval_config(config)
        return config

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return ApprovalConfig(**{
            k: ApprovalMode(v)
            for k, v in data.items()
            if hasattr(ApprovalConfig, k) and isinstance(v, str)
        })
    except Exception:
        return ApprovalConfig()


def save_approval_config(config: ApprovalConfig) -> None:
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# Instance globale
approval_config = load_approval_config()
