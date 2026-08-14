# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Garde-fou : aucune archive ne doit pouvoir écrire hors de bundle/.

L'extraction du bundle se fait membre par membre (pour suivre la progression),
donc sans l'assainissement que `zipfile.extractall()` applique tout seul. Un
membre nommé `bundle/../../evil` ou `/etc/cron.d/evil` s'écrirait alors où il
veut — et l'archive contient un venv Python et des binaires destinés à être
exécutés. Ces tests exercent le filtre et la résolution du chemin final.
"""

from __future__ import annotations

import pytest

from jarvis.kernel.bundle_download import _safe_dest, _zip_member_dest

ÉVASIONS = [
    "bundle/../../evil.txt",
    "../evil.txt",
    "../../../../../../tmp/evil.txt",
    "bundle/sub/../../../evil.txt",
    "/etc/cron.d/evil",
    "//etc/evil",
    "C:/Windows/System32/evil.dll",
    "C:evil.dll",
    r"bundle\..\..\evil.txt",
    r"..\..\evil.txt",
]

LÉGITIMES = [
    ("bundle/manifest.json", "manifest.json"),
    ("bundle/python/python.exe", "python/python.exe"),
    ("bundle/.venv/Scripts/activate", ".venv/Scripts/activate"),
    ("manifest.json", "manifest.json"),
    (r"bundle\python\python.exe", "python/python.exe"),
]


@pytest.mark.parametrize("nom", ÉVASIONS)
def test_membre_hors_bundle_est_rejete(nom: str) -> None:
    assert _zip_member_dest(nom) is None, f"{nom!r} aurait dû être filtré"


@pytest.mark.parametrize(("nom", "attendu"), LÉGITIMES)
def test_membre_legitime_conserve(nom: str, attendu: str) -> None:
    assert _zip_member_dest(nom) == attendu


@pytest.mark.parametrize("nom", ÉVASIONS)
def test_aucune_evasion_ne_survit_a_safe_dest(nom: str) -> None:
    """Seconde barrière : même si le filtre laissait passer, _safe_dest refuse."""
    rel = _zip_member_dest(nom)
    if rel is None:
        return  # déjà bloqué en amont
    with pytest.raises(RuntimeError, match="escapes bundle directory"):
        _safe_dest(rel)


def test_safe_dest_accepte_un_chemin_interne() -> None:
    from jarvis.kernel.bundle import BUNDLE_DIR

    dest = _safe_dest("python/python.exe")
    assert str(dest).startswith(str(BUNDLE_DIR.resolve()))
