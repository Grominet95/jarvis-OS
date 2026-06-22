# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Adaptateur entre le format Jarvis et le standard ouvert agentskills.io.

Spec : https://agentskills.io/specification
Format SKILL.md : frontmatter YAML (name, description, license, compatibility,
                  metadata, allowed-tools) + corps Markdown.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml
from loguru import logger

from jarvis.kernel.paths import SKILLS_INSTALLED_DIR  # noqa: F401, E402

# ── YAML Dumper avec block scalars ────────────────────────────────────────────


class _BlockDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _str_representer)


# ── Adaptateur ────────────────────────────────────────────────────────────────


class AgentSkillsAdapter:
    """Convertit entre le format Jarvis (skill.yaml + skill.py) et agentskills.io (SKILL.md).

    Exemples::

        # Installer un skill depuis le Hub (ou n'importe quel SKILL.md)
        skill_name = AgentSkillsAdapter.import_from_standard("/tmp/my-skill/")

        # Exporter un skill Jarvis vers le standard
        skill_md = AgentSkillsAdapter.export_to_standard("web-research")
    """

    # ── Import : SKILL.md → Jarvis ────────────────────────────────────────────

    @classmethod
    def import_from_standard(cls, source: str | Path) -> str:
        """Installe un skill depuis un dossier ou fichier SKILL.md agentskills.io.

        Args:
            source : chemin vers un dossier contenant SKILL.md, ou vers SKILL.md
                     directement, ou chaîne contenant le contenu brut du SKILL.md.

        Returns:
            Nom du skill installé.

        Raises:
            ValueError  : si le SKILL.md est invalide (name manquant).
            FileNotFoundError : si le chemin source est invalide.
        """
        skill_md = cls._load_skill_md(source)
        fm = cls._parse_frontmatter(skill_md)
        body = cls._extract_body(skill_md)

        name = fm.get("name", "")
        if not _is_valid_name(name):
            raise ValueError(
                f"Nom de skill invalide ou manquant dans le SKILL.md : '{name}'. "
                "Le name doit être kebab-case, 1-64 chars, lettres minuscules/chiffres/tirets."
            )
        if not fm.get("description", "").strip():
            raise ValueError("Le champ 'description' est obligatoire dans le SKILL.md.")

        dest = SKILLS_INSTALLED_DIR / name
        dest.mkdir(parents=True, exist_ok=True)

        (dest / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (dest / "skill.yaml").write_text(
            yaml.dump(
                cls._standard_to_jarvis_yaml(fm, body),
                Dumper=_BlockDumper,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (dest / "skill.py").write_text(
            _generate_skill_py(name),
            encoding="utf-8",
        )

        # Copie les sous-dossiers (scripts/, references/, assets/) si source est un dossier
        _is_raw_content = isinstance(source, str) and "\n" in source
        src_path = (
            Path(source)
            if not _is_raw_content and isinstance(source, str) and Path(source).exists()
            else (source if isinstance(source, Path) else None)
        )
        if src_path and src_path.is_dir():
            for subdir in ("scripts", "references", "assets"):
                if (src_path / subdir).exists():
                    import shutil

                    shutil.copytree(src_path / subdir, dest / subdir, dirs_exist_ok=True)

        logger.info("Skill importé depuis standard agentskills.io", name=name, dest=str(dest))
        return name

    # ── Export : Jarvis → SKILL.md ────────────────────────────────────────────

    @classmethod
    def export_to_standard(cls, skill_name: str) -> str:
        """Exporte un skill Jarvis au format SKILL.md agentskills.io.

        Args:
            skill_name : nom kebab-case du skill dans skills/installed/.

        Returns:
            Contenu complet du SKILL.md (prêt à écrire dans un fichier).

        Raises:
            FileNotFoundError : si le skill n'est pas installé.
        """
        skill_dir = SKILLS_INSTALLED_DIR / skill_name
        skill_yaml_path = skill_dir / "skill.yaml"
        if not skill_yaml_path.exists():
            raise FileNotFoundError(
                f"Skill '{skill_name}' introuvable dans {SKILLS_INSTALLED_DIR}."
            )

        # Priorité : SKILL.md existant > génération depuis skill.yaml
        existing_skill_md = skill_dir / "SKILL.md"
        if existing_skill_md.exists():
            content = existing_skill_md.read_text(encoding="utf-8")
            # Vérifie et complète le frontmatter si nécessaire
            return cls._ensure_standard_frontmatter(content, skill_name, skill_yaml_path)

        with skill_yaml_path.open(encoding="utf-8") as f:
            jarvis_meta: dict = yaml.safe_load(f) or {}

        return cls._jarvis_yaml_to_skill_md(jarvis_meta)

    # ── Helpers internes ──────────────────────────────────────────────────────

    @staticmethod
    def _load_skill_md(source: str | Path) -> str:
        """Charge le contenu SKILL.md depuis un chemin ou une chaîne brute.

        Détecte le contenu brut SKILL.md si la chaîne commence par '---' et
        contient des newlines (trop long/compliqué pour être un chemin valide).
        """
        if isinstance(source, str):
            stripped = source.strip()
            # Contenu brut : commence par '---' et contient des sauts de ligne
            if stripped.startswith("---") and "\n" in stripped:
                return source
            path = Path(source)
        else:
            path = source

        if path.exists():
            if path.is_dir():
                skill_md_file = path / "SKILL.md"
                if not skill_md_file.exists():
                    raise FileNotFoundError(f"SKILL.md absent dans {path}")
                return skill_md_file.read_text(encoding="utf-8")
            return path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Source introuvable : {source}")

    @staticmethod
    def _parse_frontmatter(skill_md: str) -> dict:
        m = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
        if not m:
            return {}
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            logger.warning("Frontmatter YAML invalide", error=str(exc))
            return {}

    @staticmethod
    def _extract_body(skill_md: str) -> str:
        m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", skill_md, re.DOTALL)
        return m.group(1).strip() if m else skill_md.strip()

    @staticmethod
    def _standard_to_jarvis_yaml(fm: dict, body: str) -> dict:
        """Convertit frontmatter agentskills.io → skill.yaml Jarvis."""
        metadata = fm.get("metadata") or {}
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        version = str(metadata.get("version", "1.0.0"))
        if re.match(r"^\d+\.\d+$", version):
            version += ".0"
        return {
            "name": fm.get("name", "unknown-skill"),
            "version": version,
            "author": str(metadata.get("author", "unknown")),
            "description": str(fm.get("description", "")),
            "tags": tags,
            "type": "conversational",
            "system_prompt": body,
            "capabilities": [],
            "requires_env": [],
            "requires_tools": [],
            # Champs agentskills.io conservés pour la traçabilité
            "license": fm.get("license", ""),
            "compatibility": fm.get("compatibility", ""),
        }

    @staticmethod
    def _jarvis_yaml_to_skill_md(meta: dict) -> str:
        """Génère un SKILL.md agentskills.io depuis un skill.yaml Jarvis."""
        name = meta.get("name", "unknown-skill")
        description = meta.get("description", "")
        author = meta.get("author", "unknown")
        version = meta.get("version", "1.0.0")
        tags = meta.get("tags", [])
        license_ = meta.get("license", "MIT")
        system_prompt = meta.get("system_prompt", "")

        # Frontmatter agentskills.io
        fm_dict = {
            "name": name,
            "description": description,
            "license": license_,
            "metadata": {
                "author": author,
                "version": version,
                "tags": tags,
            },
        }
        fm_yaml = yaml.dump(
            fm_dict, Dumper=_BlockDumper, allow_unicode=True, sort_keys=False
        ).rstrip()
        body = system_prompt.strip() or f"# {name}\n\n{description}"

        return f"---\n{fm_yaml}\n---\n\n{body}\n"

    @classmethod
    def _ensure_standard_frontmatter(
        cls, content: str, skill_name: str, skill_yaml_path: Path
    ) -> str:
        """S'assure que le SKILL.md respecte le standard (name + description présents)."""
        fm = cls._parse_frontmatter(content)
        if fm.get("name") and fm.get("description"):
            return content
        # Frontmatter incomplet : le reconstruire depuis skill.yaml
        with skill_yaml_path.open(encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        return cls._jarvis_yaml_to_skill_md(meta)


# ── Helpers module-level ──────────────────────────────────────────────────────


def _is_valid_name(name: str) -> bool:
    """Valide un nom de skill selon le standard agentskills.io.

    Règles : kebab-case, 1-64 chars, minuscules/chiffres/tirets,
    pas en début/fin, pas de tirets consécutifs.
    """
    if not name or len(name) > 64:
        return False
    if not re.match(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", name):
        return False
    # Interdit les tirets consécutifs
    return "--" not in name


def _generate_skill_py(skill_name: str) -> str:
    """Génère un skill.py Jarvis minimaliste depuis le nom du skill."""
    class_name = "".join(part.capitalize() for part in skill_name.split("-")) + "Skill"
    return textwrap.dedent(f'''\
        from __future__ import annotations
        from jarvis.capabilities.skills.base import SkillBase


        class {class_name}(SkillBase):
            """Skill importé depuis le standard agentskills.io."""

            @property  # type: ignore[override]
            def SYSTEM_PROMPT(self) -> str:
                return self.metadata.get("system_prompt", "")

            def get_system_prompt(self) -> str:  # noqa: D102
                return self.SYSTEM_PROMPT.strip()

            def is_active(self) -> bool:  # noqa: D102
                return bool(self.SYSTEM_PROMPT)
    ''')
