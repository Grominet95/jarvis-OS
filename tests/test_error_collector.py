# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import sys

import pytest

from jarvis.kernel.error_collector import ErrorCollector
from jarvis.kernel.error_emit import emit_to_stderr
from jarvis.kernel.error_hooks import install_error_hooks


def test_emit_to_stderr_format(capsys: pytest.CaptureFixture[str]) -> None:
    emit_to_stderr("JRV-LLM-001", "Rate limit", level="error")
    err = capsys.readouterr().err
    assert "[JRV-LLM-001]" in err
    assert "Rate limit" in err


def test_collector_emits_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    c = ErrorCollector()
    c.error("JRV-GWY-001", "Gateway failed")
    err = capsys.readouterr().err
    assert "[JRV-GWY-001]" in err


def test_collector_warning_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    c = ErrorCollector()
    c.warning("JRV-PRO-001", "Collector offline")
    err = capsys.readouterr().err
    assert "[JRV-PRO-001]" in err
    assert "WARN" in err


def test_excepthook_prints_code(capsys: pytest.CaptureFixture[str]) -> None:
    install_error_hooks()
    try:
        raise ValueError("test uncaught")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    err = capsys.readouterr().err
    assert "JRV-UNK-001" in err
