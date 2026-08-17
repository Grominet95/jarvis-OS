# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Garde-fou : les deux téléchargeurs de bundle doivent viser la même archive.

Le bundle offline se télécharge par deux chemins distincts :
  - le wizard, via `jarvis.kernel.bundle_download` (Python) ;
  - le lanceur Windows, via `scripts/download_bundle.ps1` (PowerShell).

Chacun porte sa propre copie de la version, de l'URL et de la taille attendue.
Rien ne les relie : au prochain build de bundle, mettre à jour l'une sans
l'autre donne un lanceur qui télécharge une archive périmée, ou qui rejette la
bonne archive sur un contrôle de taille obsolète — et l'échec n'apparaît que
sur une machine Windows sans bundle, que la CI n'exerce pas.

Ce test ne supprime pas la duplication, il la rend bruyante.
"""

from __future__ import annotations

import re

from jarvis.kernel import bundle_download as py
from jarvis.kernel.paths import PROJECT_ROOT

PS1 = PROJECT_ROOT / "scripts" / "download_bundle.ps1"


def _ps_source() -> str:
    return PS1.read_text(encoding="utf-8")


def _ps_scalar(nom: str) -> str:
    """Valeur d'un `$script:<nom> = ...` dans le script PowerShell."""
    m = re.search(rf'^\$script:{nom}\s*=\s*"?([^"\r\n]+)"?\s*$', _ps_source(), re.M)
    assert m is not None, f"${nom} introuvable dans {PS1.name}"
    return m.group(1).strip()


def test_meme_version_de_bundle() -> None:
    assert _ps_scalar("BundleReleaseVersion") == py.BUNDLE_RELEASE_VERSION


def test_meme_taille_attendue() -> None:
    assert int(_ps_scalar("BundleZipBytes")) == py.BUNDLE_ZIP_BYTES


def test_meme_url_d_archive() -> None:
    """L'URL PowerShell est un gabarit — on la reconstruit et on compare."""
    m = re.search(r'return\s+"(https://[^"]+)"', _ps_source())
    assert m is not None, "URL introuvable dans download_bundle.ps1"
    url_ps = m.group(1).replace("$Version", py.BUNDLE_RELEASE_VERSION)
    assert url_ps == py.BUNDLE_ZIP_URL


def test_memes_membres_d_archive_rejetes() -> None:
    """Les deux filtres anti-traversée doivent refuser le même ensemble.

    On ne peut pas exécuter le PowerShell ici ; on vérifie que son filtre
    mentionne les trois formes d'évasion que la version Python rejette, pour
    qu'un durcissement d'un côté ne laisse pas l'autre en arrière.
    """
    src = _ps_source()
    for motif, quoi in (
        (r"\[A-Za-z\]:", "lettre de lecteur Windows"),
        (r'Contains\("\.\."\)', "remontée .."),
        (r'StartsWith\("/"\)', "chemin enraciné"),
    ):
        assert re.search(motif, src), f"filtre PowerShell : {quoi} non rejeté"

    # Et côté Python, les mêmes entrées doivent bien être filtrées.
    for nom in ("C:/Windows/evil.dll", "bundle/../../evil", "/etc/cron.d/evil"):
        assert py._zip_member_dest(nom) is None, nom
