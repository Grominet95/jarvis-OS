# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import socket
from pathlib import Path

import pytest

import jarvis.kernel.preflight as preflight


def test_check_port_uses_dotenv_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PORT=59999\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PORT", raising=False)
    preflight.load_dotenv(env_path)
    assert preflight.check_port() is True


def test_check_port_detects_occupied_port(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        monkeypatch.setenv("PORT", str(port))
        assert preflight.check_port() is False
    finally:
        sock.close()
