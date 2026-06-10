"""Vocabulaires fermés, niveaux d'accès et d'autonomie — contrat PHASE 0 (§3.1–§3.3)."""

from __future__ import annotations

from enum import IntEnum

# Prédicats fermés — imposés à tout extracteur (§3.1).
# Tout terme hors de cet ensemble est mis en needs_review à l'ingestion.
PREDICATES: frozenset[str] = frozenset(
    {
        "is",
        "has",
        "prefers",
        "dislikes",
        "uses",
        "works_on",
        "targets",
        "plans",
        "believes",
        "needs",
        "struggles_with",
        "decided",
        "changed",
        "values",
        "communicates_as",
        "requires_validation_for",
    }
)

# Catégories fermées — classification des facts (§3.1).
CATEGORIES: frozenset[str] = frozenset(
    {
        "identity",
        "preference",
        "project",
        "goal",
        "habit",
        "constraint",
        "belief",
        "relationship",
        "tool",
        "persona",
        "decision",
        "health_fitness",
        "work_style",
        "memory_correction",
    }
)


class AccessLevel(IntEnum):
    """Niveaux d'accès ordonnés par risque croissant (§3.2).

    Tout niveau ≤ AUTO_MAX_LEVEL peut s'exécuter sans validation humaine.
    """

    READ_ONLY = 0
    WRITE_LOCAL = 1
    EXECUTE_CODE = 2
    NETWORK = 3
    INSTALL_PACKAGE = 4
    MODIFY_CORE = 5


# Niveau maximum auto-exécutable sans validation humaine.
AUTO_MAX_LEVEL: AccessLevel = AccessLevel.EXECUTE_CODE


class AutonomyLevel(IntEnum):
    """Niveaux d'autonomie pour les initiatives proactives (§3.3).

    5 = action externe (publier / payer / contacter / supprimer) → validation obligatoire.
    """

    RESPOND_ONLY = 0
    SUGGEST = 1
    DRAFT = 2
    SANDBOX = 3
    MODIFY_PROJECT = 4
    EXTERNAL_ACTION = 5
