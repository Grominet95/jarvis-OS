# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import jarvis.kernel.preflight as preflight

ROOT = Path(__file__).resolve().parents[1]


def test_check_python_emits_krn003(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight.sys, "version_info", (3, 10, 0))
    assert preflight.check_python() is False
    err = capsys.readouterr().err
    assert "JRV-KRN-003" in err


def test_preflight_module_exits_zero_or_emits_krn() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "jarvis.kernel.preflight"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        assert "OK" in proc.stderr or "vérifié" in proc.stderr.lower()
    else:
        assert "JRV-KRN-" in proc.stderr or "JRV-SET-" in proc.stderr
