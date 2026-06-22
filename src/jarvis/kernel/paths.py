# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Chemins runtime du projet — source de vérité unique (CDC §B.5).

Ce module évite le piège n°1 de la migration Phase B : tous les
`Path(__file__).parent...` qui cassent dès que le fichier source se déplace.

`PROJECT_ROOT` est résolu en remontant depuis ce fichier jusqu'au premier
parent contenant `pyproject.toml`. Robuste à la profondeur du package
(que `kernel/paths.py` soit à `kernel/`, `src/jarvis/kernel/` ou ailleurs).

Toute constante de chemin du projet vit ici. Plus AUCUN `Path("memory_data/...")`
ou `Path(__file__).parent.parent / "..."` ne doit subsister hors de ce module
en fin de Phase B (GATE B7a vérifie).
"""

from __future__ import annotations

from pathlib import Path


def _find_project_root() -> Path:
    """Remonte depuis ce fichier jusqu'au premier parent contenant pyproject.toml.

    Plus robuste qu'un chemin relatif à profondeur fixe (`parent.parent.parent...`) :
    survit à un déplacement du module kernel dans la hiérarchie.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError(
        f"PROJECT_ROOT introuvable : aucun pyproject.toml trouvé en remontant depuis {here}"
    )


PROJECT_ROOT: Path = _find_project_root()

# ── Données utilisateur (gitignored, hors package) ─────────────────────────
MEMORY_DATA_DIR: Path = PROJECT_ROOT / "memory_data"
SKILLS_DATA_DIR: Path = PROJECT_ROOT / "skills_data"
SKILLS_INSTALLED_DIR: Path = SKILLS_DATA_DIR / "installed"
SKILLS_CANDIDATES_DIR: Path = SKILLS_DATA_DIR / "candidates"
VISION_DATA_DIR: Path = PROJECT_ROOT / "vision_data"
FACES_DIR: Path = VISION_DATA_DIR / "faces"
WORKSPACE_DIR: Path = PROJECT_ROOT / "workspace"

# ── Assets / code-as-data (trackés en git) ────────────────────────────────
PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"
CONFIG_DIR: Path = PROJECT_ROOT / "config"
NOTICES_DIR: Path = PROJECT_ROOT / "notices"

# ── UI statique (déplacée vers src/jarvis/interfaces/ui/ en B) ──────────────
UI_DIR: Path = PROJECT_ROOT / "src" / "jarvis" / "interfaces" / "ui"
UI_STATIC_DIR: Path = UI_DIR / "static"
