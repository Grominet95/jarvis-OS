"""Classe de base pour tous les skills Jarvis."""
from __future__ import annotations

import platform
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from tools.base import Tool


class SkillBase(ABC):
    """
    Un skill est une extension de capacité pour Jarvis.

    SYSTEM_PROMPT est injecté automatiquement dans le contexte
    de Jarvis à chaque conversation quand le skill est installé.

    get_tools() permet à un skill d'exposer des outils qui seront
    automatiquement enregistrés dans le ToolRegistry.
    """

    SYSTEM_PROMPT: str = ""

    def __init__(self, metadata: dict = None):
        self.metadata = metadata or {}
        self.name = metadata.get("name", self.__class__.__name__)
        self.label = metadata.get("label", self.name)
        self.version = metadata.get("version", "1.0.0")
        self.author = metadata.get("author", "unknown")
        self.description = metadata.get("description", "")
        self.tags = metadata.get("tags", [])

    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT.strip()

    def get_tools(self) -> list["Tool"]:
        """Retourne les outils fournis par ce skill (vide par défaut)."""
        return []

    def is_active(self) -> bool:
        return bool(self.SYSTEM_PROMPT)

    def is_routine(self) -> bool:
        return False

    def __repr__(self):
        return f"<Skill {self.name} v{self.version} by {self.author}>"


# ── Routine support ──────────────────────────────────────────────────────────


class RoutineStep:
    """Un step d'une routine."""

    def __init__(self, data: dict):
        self.name = data.get("name", "")
        self.type = data.get("type", "")
        self.platforms = data.get("platforms", {})
        self.command = data.get("command", "")
        self.action = data.get("action", "")
        self.query = data.get("query", "")
        self.text = data.get("text", "")
        self.prompt = data.get("prompt", "")
        self.seconds = data.get("seconds", 1)
        self.title = data.get("title", "")
        self.body = data.get("body", "")
        self.requires_confirmation = data.get("requires_confirmation", False)

    def get_command(self) -> str | None:
        """
        Résout la commande CLI pour la plateforme actuelle.
        Retourne None si non supporté sur cette plateforme.
        """
        if self.command:
            return self.command

        if self.platforms:
            system = platform.system().lower()
            key = "mac" if system == "darwin" else system
            cmd = self.platforms.get(key)
            if cmd is None:
                return None
            return cmd

        return None


class RoutineSkill(SkillBase):
    """
    Skill de type routine — exécute une séquence de steps depuis skill.yaml.

    Le SYSTEM_PROMPT est auto-généré depuis les triggers définis dans skill.yaml.
    Surcharger SYSTEM_PROMPT pour un comportement vocal personnalisé.
    """

    @property  # type: ignore[override]
    def SYSTEM_PROMPT(self) -> str:
        triggers = self.metadata.get("triggers", [])
        name = self.metadata.get("name", self.name)
        label = self.metadata.get("label", name)
        description = self.metadata.get("description", "")

        if not triggers:
            return ""

        triggers_str = '", "'.join(triggers)
        return (
            f"\n## Skill Routine : {label}\n\n{description}\n\n"
            f'Quand l\'utilisateur dit "{triggers_str}" ou une formulation similaire,\n'
            f'appeler l\'outil execute_routine avec routine_name="{name}".\n\n'
            "Ne pas exécuter les étapes manuellement — utiliser uniquement execute_routine.\n"
        )

    def get_system_prompt(self) -> str:
        return self.SYSTEM_PROMPT.strip()

    def is_active(self) -> bool:
        return bool(self.SYSTEM_PROMPT)

    def get_steps(self) -> list[RoutineStep]:
        installed_dir = Path("skills/installed") / self.name
        yaml_file = installed_dir / "skill.yaml"

        if not yaml_file.exists():
            return []

        with yaml_file.open() as f:
            skill_yaml = yaml.safe_load(f)

        if not skill_yaml:
            return []

        return [RoutineStep(step) for step in skill_yaml.get("steps", [])]

    def get_triggers(self) -> list[str]:
        return self.metadata.get("triggers", [])

    def get_platforms(self) -> list[str]:
        return self.metadata.get("platforms", [])

    def is_routine(self) -> bool:
        return True
