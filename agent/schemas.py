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
