# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""jarvis.capabilities.skills — gestion des skills installés.

L'import de ce package pose immédiatement l'alias ABI `skills` →
`jarvis.capabilities.skills` dans `sys.modules` (CDC §B.2bis) pour
permettre le chargement des skills utilisateur qui font
`from skills.base import SkillBase`.
"""

from __future__ import annotations

from jarvis.capabilities.skills import (
    _abi_compat,  # noqa: F401 — side-effect import (sys.modules setup)
)
