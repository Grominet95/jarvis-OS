# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path

import yaml
from loguru import logger

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def _parse_skill_md(path: Path) -> dict | None:
    """Parse un SKILL.md et retourne {name, description, instructions} ou None."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Cannot read skill", path=str(path))
        return None

    m = _FRONTMATTER_RE.match(raw)
    if not m:
        logger.warning("Skill sans frontmatter YAML valide", path=str(path))
        return None

    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning("Skill YAML invalide", path=str(path), error=str(e))
        return None

    name = meta.get("name", path.parent.name)
    description = meta.get("description", "")
    instructions = m.group(2).strip()

    return {
        "name": name,
        "description": description,
        "instructions": instructions,
        "meta": meta,
        "dir": path.parent,
    }


def _check_requirements(meta: dict) -> tuple[bool, str]:
    """Vérifie les exigences openclaw. Retourne (ok, raison_si_non_ok)."""
    openclaw = meta.get("metadata", {}).get("openclaw", {})
    if not openclaw:
        return True, ""

    os_filter = openclaw.get("os", [])
    if os_filter:
        current = "darwin" if platform.system() == "Darwin" else platform.system().lower()
        if current not in os_filter:
            return False, f"OS {current!r} non supporté (requis: {os_filter})"

    requires = openclaw.get("requires", {})
    for bin_name in requires.get("bins", []):
        if not shutil.which(bin_name):
            return False, f"Binaire manquant: {bin_name}"

    for key in requires.get("config", []):
        if not os.getenv(key):
            return False, f"Variable d'env manquante: {key}"

    return True, ""


def load_skills(skills_dir: Path) -> list[dict]:
    """Scanne le dossier skills/, parse les SKILL.md, filtre selon les requirements.

    Retourne une liste de skills actifs avec {name, description, instructions}.
    Les sous-dossiers préfixés par '_' sont ignorés (fichiers internes du système).
    """
    if not skills_dir.exists():
        logger.debug("Skills dir absent — aucun skill chargé", dir=str(skills_dir))
        return []

    active: list[dict] = []

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        folder = skill_md.parent
        if folder.name.startswith("_"):
            continue

        skill = _parse_skill_md(skill_md)
        if skill is None:
            continue

        ok, reason = _check_requirements(skill["meta"])
        if not ok:
            logger.info("Skill ignoré (requirements)", name=skill["name"], reason=reason)
            continue

        logger.debug("Skill chargé", name=skill["name"])
        active.append(
            {
                "name": skill["name"],
                "description": skill["description"],
                "instructions": skill["instructions"],
                "dir": skill["dir"],
            }
        )

    logger.info("Skills chargés", count=len(active))
    return active
