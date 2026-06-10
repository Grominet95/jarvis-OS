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
