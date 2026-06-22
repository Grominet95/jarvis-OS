# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Zone d'extensions dev (extensions liées en symlink).

Sépare le store officiel (skills/installed/) d'une zone optionnelle pour
les contributeurs développant dans `jarvis-skills` :

    ~/.jarvis/extensions/dev/
        skills/<name>   -> symlink vers ../jarvis-skills/skills/<name>
        presets/<name>  -> symlink vers ../jarvis-skills/skills/<name>
        views/<name>    -> symlink vers ../jarvis-skills/views/<name>

Inerte par défaut : si la zone n'existe pas ou est vide, toutes les
fonctions sont no-op et le comportement de Jarvis est strictement
identique au scan de `skills/installed/` seul.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from loguru import logger


def dev_root() -> Path:
    """Racine de la zone dev. Override possible via JARVIS_DEV_EXTENSIONS_DIR (pour les tests)."""
    override = os.environ.get("JARVIS_DEV_EXTENSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".jarvis" / "extensions" / "dev"


def _iter_subdir(parent: Path) -> Iterator[Path]:
    if not parent.is_dir():
        return
    for child in sorted(parent.iterdir()):
        if child.is_dir() or child.is_symlink():
            yield child


def iter_dev_skills_and_presets() -> Iterator[Path]:
    """Sous-dossiers de dev/skills/ et dev/presets/ (skills + presets Python)."""
    root = dev_root()
    yield from _iter_subdir(root / "skills")
    yield from _iter_subdir(root / "presets")


def iter_dev_views() -> Iterator[Path]:
    """Sous-dossiers de dev/views/ (assets JS/CSS d'une vue)."""
    yield from _iter_subdir(dev_root() / "views")


def mount_dev_views(app: object) -> int:
    """Monte chaque dossier dev/views/<name>/ sous /static/skills/<name>.

    À appeler AVANT le mount global `/`. Si la zone n'existe pas, aucun
    mount n'est ajouté et l'app FastAPI reste strictement identique.
    Retourne le nombre de mounts ajoutés (utile pour les tests).
    """
    from fastapi.staticfiles import StaticFiles

    added = 0
    for view_dir in iter_dev_views():
        target = view_dir.resolve()
        if not target.is_dir():
            continue
        mount_path = f"/static/skills/{view_dir.name}"
        app.mount(mount_path, StaticFiles(directory=str(target)), name=f"dev_view_{view_dir.name}")
        logger.info("Vue dev montée", name=view_dir.name, path=str(target))
        added += 1
    return added


__all__ = [
    "dev_root",
    "iter_dev_skills_and_presets",
    "iter_dev_views",
    "mount_dev_views",
]
