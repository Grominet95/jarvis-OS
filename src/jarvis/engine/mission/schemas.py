# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Ré-export de kernel.schemas (section Agent) — CDC §A.1.3.

Le foyer canonique des contrats de données Mission Engine est
`kernel/schemas.py` depuis la Phase A. Ce fichier reste pour préserver
les imports existants (`from agent.schemas import …`) jusqu'à la Phase B.
"""

from __future__ import annotations

from jarvis.kernel.schemas import (  # noqa: F401
    LogEntry,
    Project,
    ProjectStatus,
    Step,
    StepStatus,
    validate_step,
)
