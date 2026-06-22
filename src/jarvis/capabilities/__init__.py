# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""L1 — Capabilities : outils et skills exposés à l'engine.

Sous-packages :
- skills/ — gestion des skills installés (registry, lifecycle, lab, synth).
- tools/  — outils (Tool) exposés à l'agent via tool_registry.

L'API publique de chaque sous-package est définie dans son propre
`__init__.py` ; ce module-ci ne réagrège pas — l'engine reçoit ces
objets par injection (RÈGLE 3), pas par import direct.
"""

from __future__ import annotations

__all__: list[str] = []
