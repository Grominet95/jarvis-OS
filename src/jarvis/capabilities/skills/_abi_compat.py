# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Alias de namespace `skills` → `jarvis.capabilities.skills` — CDC §B.2bis.

Les 8 skills installés par l'utilisateur dans `skills_data/installed/`
contiennent du code utilisateur sur disque qui importe :

    from jarvis.capabilities.skills.base import SkillBase, PresetSkill

Ce code est HORS de la portée des sed/find-replace de la Phase B
(c'est du code utilisateur, pas du code du package). Sans cet alias,
chaque skill installé casserait silencieusement à `exec_module()` après
la migration `skills/` → `jarvis/capabilities/skills/`.

Solution retenue (CDC) : enregistrer `skills` comme alias de
`jarvis.capabilities.skills` dans `sys.modules` AVANT tout chargement de
skill. Le namespace `skills.*` devient ainsi une **API publique stable**
(ABI), pas un shim de migration.

Documentation : voir `docs/architecture/skills-abi.md`.
Garantie de stabilité : `skills.base.SkillBase`, `skills.base.PresetSkill`.
Politique de dépréciation : jamais sans version majeure + outil de migration.

GATE C9 exclut ce module nommément (cf. CDC §C.2 GATE C9, ligne `grep -v
"capabilities/skills/_loader.py"` — note : nous utilisons `_abi_compat.py`,
voir docs pour ajuster le grep si nécessaire).
"""

from __future__ import annotations

import sys

import jarvis.capabilities.skills as _skills_pkg

# setdefault : ne remplace pas si déjà présent (test où un autre alias existait).
sys.modules.setdefault("skills", _skills_pkg)

# Modules importés explicitement par le code utilisateur des skills installés —
# on les expose aussi pour permettre `from skills.base import ...` de résoudre
# vers le sous-module réel.
from jarvis.capabilities.skills import base as _base  # noqa: E402

sys.modules.setdefault("skills.base", _base)

del _skills_pkg, _base, sys
