# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Shim de compatibilité racine — voir CDC §B.2 (4).

Le vrai code vit dans `src/jarvis/app.py`. Ce shim existe pour les
appelants externes qui font encore `python main.py`. Retrait → BACKLOG
(post-refonte).

À partir de B.4, le CLI `jarvis` et le Makefile invoquent
`python -m jarvis.app` directement et ne dépendent plus de ce shim.

L'export `app` (instance FastAPI) est re-exporté pour les snippets qui
font `from main import app` (notamment scripts/migration/snapshot_routes.py
avant que `from jarvis.app import app` ne devienne disponible).
"""

from __future__ import annotations

from jarvis.app import app, main  # noqa: F401

if __name__ == "__main__":
    main()
