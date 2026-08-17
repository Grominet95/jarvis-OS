# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Garde-fou : aucun appel au collector ne doit vivre dans une chaîne de code.

Plusieurs modules embarquent du Python sous forme de chaîne, exécuté ailleurs
que dans ce processus : le script sandbox de `skills/lab.py` (sous-processus
isolé, éventuellement Docker) et les wrappers Fusion 360 de `tools/fusion.py`
(interpréteur d'Autodesk). Ces scripts n'importent pas `jarvis.kernel`.

Y insérer `collector.error(...)` — ce qu'a fait l'autofix du registre JRV —
lève un NameError au moment précis où l'on gère déjà une erreur : le sandbox
n'émet plus son JSON et l'échec se reclasse en « parse » au lieu du vrai
étage, et le wrapper Fusion rend un NameError au lieu du `FUSION_ERROR:`
attendu par le MCP.

Ce test balaie tout `src/` plutôt que les seuls sites connus : c'est la classe
de bug qu'on interdit, pas ses trois occurrences d'origine.
"""

from __future__ import annotations

import ast

from jarvis.kernel.paths import PROJECT_ROOT

SRC = PROJECT_ROOT / "src" / "jarvis"


def test_aucun_collector_dans_une_chaine_de_code() -> None:
    coupables: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            arbre = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — fichier non parsable
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Constant) or not isinstance(noeud.value, str):
                continue
            if "collector." not in noeud.value:
                continue
            rel = path.relative_to(PROJECT_ROOT)
            coupables.append(f"{rel}:{noeud.lineno} (chaîne)")

    assert not coupables, (
        "Appel au collector inséré dans une chaîne contenant du code — "
        "ces scripts s'exécutent hors de ce processus et n'importent pas "
        "jarvis.kernel, donc l'appel lève un NameError :\n  " + "\n  ".join(coupables)
    )
