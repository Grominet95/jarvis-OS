# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests unitaires de l'injection du token API dans le HTML UI (interfaces.api.ui)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from jarvis.interfaces.api import ui


def _fake_settings(enabled: bool, token: str, wakeup_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        api_auth_enabled=enabled,
        api_token=SecretStr(token),
        wakeup_enabled=wakeup_enabled,
    )


def test_inject_wakeup_enabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(False, "", wakeup_enabled=True))
    assert "window.JARVIS_WAKEUP_ENABLED=true" in ui.inject_client_config("<head></head>")
    monkeypatch.setattr(ui, "settings", _fake_settings(False, "", wakeup_enabled=False))
    assert "window.JARVIS_WAKEUP_ENABLED=false" in ui.inject_client_config("<head></head>")


def test_inject_adds_token_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(True, "secret-123"))
    out = ui.inject_client_config("<head></head><body></body>")
    assert "window.JARVIS_API_TOKEN" in out
    assert "secret-123" in out


def test_inject_empty_token_when_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(False, "secret-123"))
    out = ui.inject_client_config("<head></head>")
    assert 'window.JARVIS_API_TOKEN=""' in out
    assert "secret-123" not in out


def test_inject_before_head_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(True, "tok"))
    out = ui.inject_client_config("<head><title>x</title></head>")
    assert out.index("window.JARVIS_API_TOKEN") < out.index("</head>")


def test_inject_prepends_when_no_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(True, "tok"))
    out = ui.inject_client_config("<body>only</body>")
    assert out.startswith("<script>")
    assert "<body>only</body>" in out


def test_inject_token_is_json_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    tricky = 'a"b</script>'
    monkeypatch.setattr(ui, "settings", _fake_settings(True, tricky))
    out = ui.inject_client_config("<head></head>")
    assert json.dumps(tricky) in out


def test_inject_defines_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "settings", _fake_settings(False, ""))
    out = ui.inject_client_config("<head></head>")
    assert "window.JARVIS_API_BASE" in out
