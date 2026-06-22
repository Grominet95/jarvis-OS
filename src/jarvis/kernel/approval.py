# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Singleton accessor pour l'ApprovalChecker — Phase F.

L'IMPLÉMENTATION (`ApprovalChecker` concret, avec broadcast UI et logique
de pending) reste dans `jarvis.engine.approval_checker`. Ce module-ci
expose UNIQUEMENT l'accessor singleton, parce que :

  - les tools plugin (`capabilities/tools/{subagent, fusion, printer}`)
    sont instanciés SANS ARGS par des skills utilisateur depuis
    `skills_data/installed/*/skill.py` ; on ne peut pas leur injecter
    l'ApprovalChecker par constructeur sans casser le contrat plugin ;
  - capabilities/ n'a le droit d'importer QUE jarvis.kernel (RÈGLE 2) ;
  - donc l'accessor singleton (sans concrete dependency) vit ici, le
    bootstrap appelle `set_approval_checker(...)` après construction.

Le Protocol structurel `ApprovalChecker` est dans `kernel.contracts`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.kernel.contracts import ApprovalChecker

_checker: ApprovalChecker | None = None


def get_approval_checker() -> ApprovalChecker | None:
    """Retourne l'ApprovalChecker actif, ou None si non câblé (mode dégradé)."""
    return _checker


def set_approval_checker(checker: ApprovalChecker) -> None:
    """Injecté par bootstrap.build() après construction du container."""
    global _checker
    _checker = checker
