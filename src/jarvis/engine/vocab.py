# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Ré-export de kernel.vocab — CDC §A.1.3.

Le foyer canonique des vocabulaires fermés (PREDICATES, CATEGORIES,
AccessLevel, AUTO_MAX_LEVEL, AutonomyLevel) est `kernel/vocab.py`
depuis la Phase A. Ce fichier reste pour préserver les imports existants
(`from core.vocab import …`) jusqu'à la Phase B (§B.1).
"""

from __future__ import annotations

from jarvis.kernel.vocab import (  # noqa: F401
    AUTO_MAX_LEVEL,
    CATEGORIES,
    PREDICATES,
    AccessLevel,
    AutonomyLevel,
)
