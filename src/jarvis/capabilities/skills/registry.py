# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Gestionnaire des skills installés localement."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from loguru import logger

from jarvis.capabilities.skills.base import PresetSkill, SkillBase
from jarvis.capabilities.skills.dev_extensions import iter_dev_skills_and_presets
from jarvis.kernel.paths import SKILLS_INSTALLED_DIR  # noqa: F401, E402


class SkillRegistry:
    """
    Charge et gère les skills depuis skills/installed/.
    Chaque sous-dossier = un skill (skill.py + skill.yaml).
    """

    _instance = None
    _skills: dict[str, SkillBase] = {}

    @classmethod
    def get_instance(cls) -> SkillRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load_all()
        return cls._instance

    def load_all(self) -> None:
        SKILLS_INSTALLED_DIR.mkdir(parents=True, exist_ok=True)
        self._skills = {}
        # Zone dev (~/.jarvis/extensions/dev) chargée en priorité. Inerte si
        # la zone n'existe pas : iter_dev_skills_and_presets() ne yield rien.
        for dev_dir in iter_dev_skills_and_presets():
            self._load_skill(dev_dir)
        for skill_dir in SKILLS_INSTALLED_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            # Skip si un skill dev du même nom a déjà été chargé (override dev).
            if skill_dir.name in self._skills:
                logger.debug(f"Skill installé masqué par version dev : {skill_dir.name}")
                continue
            self._load_skill(skill_dir)
        logger.info(f"SkillRegistry: {len(self._skills)} skill(s) chargé(s)")

    def _load_skill(self, skill_dir: Path) -> None:
        skill_py = skill_dir / "skill.py"
        skill_yaml = skill_dir / "skill.yaml"
        if not skill_py.exists():
            return

        metadata = {}
        if skill_yaml.exists():
            import yaml

            with skill_yaml.open() as f:
                metadata = yaml.safe_load(f) or {}

        if "requires_apps" not in metadata:
            metadata["requires_apps"] = []
        if "capabilities" not in metadata:
            metadata["capabilities"] = []
        # Dossier source réel — utilisé par PresetSkill.get_steps() pour lire
        # son skill.yaml sans hardcoder skills/installed/. Toujours injecté.
        metadata["__dir"] = str(skill_dir.resolve())

        try:
            spec = importlib.util.spec_from_file_location(f"skill_{skill_dir.name}", skill_py)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, SkillBase)
                    and attr is not SkillBase
                    and attr is not PresetSkill
                ):
                    skill = attr(metadata=metadata)
                    self._skills[skill.name] = skill
                    skill_type = metadata.get("type", "conversational")
                    if skill_type == "preset" or isinstance(skill, PresetSkill):
                        logger.debug(f"Preset chargé : {skill.name} v{skill.version}")
                    else:
                        logger.debug(
                            f"Skill conversationnel chargé : {skill.name} v{skill.version}"
                        )
                    break

        except Exception as e:
            logger.error(f"Erreur chargement skill {skill_dir.name}: {e}")

    def get_combined_system_prompt(self) -> str:
        """Retourne tous les SYSTEM_PROMPT des skills actifs concaténés."""
        prompts = []
        for skill in self._skills.values():
            if skill.is_active():
                prompts.append(f"## Skill actif : {skill.name}\n{skill.get_system_prompt()}")
        return "\n\n---\n\n".join(prompts)

    def reload(self) -> None:
        """Recharger tous les skills sans redémarrer Jarvis."""
        self.load_all()
        logger.info("SkillRegistry rechargé")

    def get(self, name: str) -> SkillBase | None:
        return self._skills.get(name)

    def _is_preset(self, skill: SkillBase) -> bool:
        return isinstance(skill, PresetSkill) or skill.metadata.get("type") == "preset"

    def list_installed(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "label": s.label,
                "version": s.version,
                "author": s.author,
                "description": s.description,
                "tags": s.tags,
                "type": s.metadata.get("type", "conversational"),
                "requires_env": s.metadata.get("requires_env", []),
                "requires_tools": s.metadata.get("requires_tools", []),
            }
            for s in self._skills.values()
        ]

    def get_all(self) -> dict[str, SkillBase]:
        return self._skills.copy()

    def get_all_tools(self) -> list:
        """Retourne tous les outils fournis par les skills installés."""
        tools = []
        for skill in self._skills.values():
            try:
                tools.extend(skill.get_tools())
            except Exception as e:
                logger.error(f"Erreur get_tools() pour {skill.name}: {e}")
        return tools

    def get_presets(self) -> dict[str, SkillBase]:
        """Retourne uniquement les skills de type preset."""
        return {name: skill for name, skill in self._skills.items() if self._is_preset(skill)}

    def get_preset(self, name: str) -> SkillBase | None:
        """Retourne un preset par son nom."""
        skill = self._skills.get(name)
        if skill and self._is_preset(skill):
            return skill
        return None

    def find_preset_by_trigger(self, text: str) -> SkillBase | None:
        """Trouve un preset dont un trigger correspond au texte (partiel, insensible à la casse)."""
        text_lower = text.lower()
        for skill in self.get_presets().values():
            for trigger in skill.get_triggers():
                if trigger.lower() in text_lower:
                    return skill
        return None


skill_registry = SkillRegistry.get_instance()
