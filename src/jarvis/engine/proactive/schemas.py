# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Ré-export de kernel.schemas (section Proactive) — CDC §A.1.3.

Le foyer canonique des contrats de données Proactive est
`kernel/schemas.py` depuis la Phase A. Ce fichier reste pour préserver
les imports existants (`from proactive.schemas import …`) jusqu'à la Phase B.
"""

from __future__ import annotations

from jarvis.kernel.schemas import (  # noqa: F401
    CollectionResult,
    ContextItem,
    ExecutionMode,
    Initiative,
    InitiativeType,
    ItemType,
    Priority,
    needs_human_validation,
)
