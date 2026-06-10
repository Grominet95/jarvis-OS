"""Pendant la Phase B de la refonte (CDC), on bascule progressivement les
packages de la racine vers src/jarvis/ via `git mv`. Ce sitecustomize ajoute
`src/` au sys.path pour que `from jarvis.<pkg> import ...` fonctionne dès
qu'un package a été déplacé, sans dépendre d'un `pip install -e .` à jour.

Python charge automatiquement `sitecustomize.py` au démarrage s'il est sur
sys.path. La racine du repo est implicitement sur sys.path quand on lance
Python depuis là (`uv run python ...`, `python main.py`, etc.).

À RETIRER en Phase B.3 quand pyproject.toml passe au src-layout strict
(`packages = ["src/jarvis"]`) et que `pip install -e .` rend ce hack inutile.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
