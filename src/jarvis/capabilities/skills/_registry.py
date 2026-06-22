# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from jarvis.capabilities.skills._loader import load_skills


class SkillRegistry:
    """Registre des skills actifs. Supporte le rechargement à chaud."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._active: list[dict] = []
        self.reload()

    def reload(self) -> None:
        """Recharge tous les skills depuis le disque."""
        self._active = load_skills(self._skills_dir)
        logger.info("SkillRegistry rechargé", count=len(self._active))

    @property
    def active(self) -> list[dict]:
        return list(self._active)

    def get(self, name: str) -> dict | None:
        return next((s for s in self._active if s["name"] == name), None)

    def list_names(self) -> list[str]:
        return [s["name"] for s in self._active]

    def remove(self, name: str) -> bool:
        """Désactive (et supprime du disque) un skill par son nom."""
        skill = self.get(name)
        if skill is None:
            return False
        skill_dir: Path = skill["dir"]
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            logger.info("Skill supprimé", name=name, dir=str(skill_dir))
        self._active = [s for s in self._active if s["name"] != name]
        return True

    def build_prompt_section(self) -> str:
        """Génère le bloc 'Skills actifs' à injecter dans le prompt système."""
        if not self._active:
            return ""
        lines = ["## Skills actifs\n"]
        for skill in self._active:
            lines.append(f"### {skill['name']}")
            if skill["description"]:
                lines.append(f"{skill['description']}\n")
            if skill["instructions"]:
                lines.append(skill["instructions"])
            lines.append("")
        return "\n".join(lines)
