# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests du garde-fou réseau Bearer (core/auth.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from main import app

pytestmark = pytest.mark.integration  # CDC §A.1.5 — exercice HTTP middleware réel


@pytest.fixture
def client() -> TestClient:
    """Client HTTP de test."""
    return TestClient(app)


# ── Auth désactivée (défaut) ──────────────────────────────────


def test_auth_disabled_health_ok(client: TestClient) -> None:
    """Sans auth, /api/health est accessible sans aucun token."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = False
        mock.api_token = SecretStr("")
        r = client.get("/api/health")
    assert r.status_code == 200


def test_auth_disabled_sessions_accessible(client: TestClient) -> None:
    """Sans auth activée, une route API standard passe sans token."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = False
        mock.api_token = SecretStr("")
        r = client.get("/api/sessions")
    # 200 ou autre code métier — jamais 401
    assert r.status_code != 401


# ── Auth activée ─────────────────────────────────────────────


def test_auth_enabled_missing_token_returns_401(client: TestClient) -> None:
    """Avec auth activée, requête sans header Authorization → 401."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = True
        mock.api_token = SecretStr("test-secret-token")
        r = client.get("/api/sessions")
    assert r.status_code == 401


def test_auth_enabled_wrong_token_returns_401(client: TestClient) -> None:
    """Avec auth activée, mauvais token → 401."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = True
        mock.api_token = SecretStr("test-secret-token")
        r = client.get("/api/sessions", headers={"Authorization": "Bearer mauvais-token"})
    assert r.status_code == 401


def test_auth_enabled_correct_token_passes(client: TestClient) -> None:
    """Avec auth activée, le bon token n'est pas rejeté (pas 401)."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = True
        mock.api_token = SecretStr("test-secret-token")
        r = client.get("/api/sessions", headers={"Authorization": "Bearer test-secret-token"})
    assert r.status_code != 401


# ── Exemptions ───────────────────────────────────────────────


def test_health_exempt_even_with_auth_enabled(client: TestClient) -> None:
    """/api/health reste accessible sans token même quand auth activée."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = True
        mock.api_token = SecretStr("test-secret-token")
        r = client.get("/api/health")
    assert r.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/", "/dashboard", "/settings", "/command", "/capabilities", "/admin"],
)
def test_ui_html_exempt_with_auth_enabled(client: TestClient, path: str) -> None:
    """Les pages HTML de l'UI restent servies sans token Bearer."""
    with patch("jarvis.engine.auth.settings") as mock_auth, patch(
        "jarvis.interfaces.api.ui.settings"
    ) as mock_ui:
        mock_auth.api_auth_enabled = True
        mock_auth.api_token = SecretStr("test-secret-token")
        mock_ui.api_auth_enabled = True
        mock_ui.api_token = SecretStr("test-secret-token")
        r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_ui_html_injects_api_token(client: TestClient) -> None:
    """Le token API est injecté dans le HTML rendu quand auth activée."""
    with patch("jarvis.engine.auth.settings") as mock_auth, patch(
        "jarvis.interfaces.api.ui.settings"
    ) as mock_ui:
        mock_auth.api_auth_enabled = True
        mock_auth.api_token = SecretStr("test-secret-token")
        mock_ui.api_auth_enabled = True
        mock_ui.api_token = SecretStr("test-secret-token")
        r = client.get("/")
    assert r.status_code == 200
    assert "window.JARVIS_API_TOKEN" in r.text
    assert "test-secret-token" in r.text


def test_ui_html_no_token_when_auth_disabled(client: TestClient) -> None:
    """Sans auth, le HTML n'embarque pas de token."""
    with patch("jarvis.engine.auth.settings") as mock_auth, patch(
        "jarvis.interfaces.api.ui.settings"
    ) as mock_ui:
        mock_auth.api_auth_enabled = False
        mock_auth.api_token = SecretStr("")
        mock_ui.api_auth_enabled = False
        mock_ui.api_token = SecretStr("")
        r = client.get("/")
    assert r.status_code == 200
    assert 'window.JARVIS_API_TOKEN=""' in r.text


# ── Route sensible (exécution) ────────────────────────────────


def test_tools_execute_blocked_without_token(client: TestClient) -> None:
    """Avec auth activée, /api/tools/execute (exécution code) est protégée sans token."""
    with patch("jarvis.engine.auth.settings") as mock:
        mock.api_auth_enabled = True
        mock.api_token = SecretStr("test-secret-token")
        r = client.post("/api/tools/execute", json={"tool": "cli_runner", "args": {}})
    assert r.status_code == 401
