# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import inspect
import socket
from pathlib import Path

import pytest

import jarvis.kernel.preflight as preflight


def test_check_port_uses_dotenv_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Le port controle vient bien du .env, pas du defaut.

    Assertion volontairement sur un port OCCUPE : `check_port() is True` ne
    prouverait rien, puisque le defaut 8000 est libre la plupart du temps et
    renverrait True lui aussi. En occupant le port declare dans le .env, seul
    un check_port() qui a reellement lu ce port peut renvoyer False.
    """
    occupe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupe.bind(("127.0.0.1", 0))
    port = occupe.getsockname()[1]
    try:
        env_path = tmp_path / ".env"
        env_path.write_text(f"PORT={port}\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PORT", raising=False)
        preflight.load_dotenv(env_path)
        assert preflight.check_port() is False
    finally:
        occupe.close()


def test_main_charge_le_dotenv_avant_de_controler_le_port() -> None:
    """C'est CE test qui garde le correctif de la PR #62.

    Les deux tests de port passent meme si l'on retire `load_dotenv()` de
    `main()` : ils appellent `check_port()` directement. Le defaut corrige
    n'etait pas dans check_port mais dans l'ordre suivi par main(), qui
    controlait le port sur un environnement ou le .env n'avait jamais ete lu.
    Verifie ici sur la source, parce que l'ordre d'appel est justement ce qui
    ne se voit pas en appelant les fonctions une a une.
    """
    source = inspect.getsource(preflight.main)
    appels = [
        ligne.strip()
        for ligne in source.splitlines()
        if "load_dotenv()" in ligne or "check_port" in ligne
    ]
    assert appels, "ni load_dotenv() ni check_port introuvables dans main()"
    assert appels[0].startswith("load_dotenv()"), (
        "main() doit charger le .env AVANT de controler le port — sinon "
        f"check_port lit un PORT non defini et retombe sur 8000. Trouve : {appels}"
    )


def test_check_port_detects_occupied_port(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        monkeypatch.setenv("PORT", str(port))
        assert preflight.check_port() is False
    finally:
        sock.close()
