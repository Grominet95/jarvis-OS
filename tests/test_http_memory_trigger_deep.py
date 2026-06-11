"""Tests de l'endpoint /api/memory/trigger-deep (MOUVEMENT 2 option D).

L'endpoint est un outil d'observation : il déclenche AutoDream.deep_analyze()
sans attendre 3h du mat. Mais il DOIT respecter le flag ingest_deep_enabled
— sinon on contourne l'interrupteur principal.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.interfaces.api.memory import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    # auto_dream fake : on attache un MagicMock pour ne pas bloquer sur l'import
    app.state.auto_dream = MagicMock()
    app.state.auto_dream.deep_analyze = AsyncMock(return_value=None)
    return TestClient(app)


def test_trigger_deep_refuse_si_flag_desactive(client: TestClient) -> None:
    """Si ingest_deep_enabled=False, l'endpoint refuse (503)."""
    with patch("jarvis.kernel.settings.settings.ingest_deep_enabled", False):
        r = client.post("/api/memory/trigger-deep")
    assert r.status_code == 503
    assert "désactivée" in r.json()["detail"].lower()


def test_trigger_deep_passe_si_flag_active(client: TestClient) -> None:
    """Si ingest_deep_enabled=True, l'endpoint déclenche deep_analyze()."""
    with patch("jarvis.kernel.settings.settings.ingest_deep_enabled", True):
        r = client.post("/api/memory/trigger-deep")
    assert r.status_code == 200
    assert r.json() == {"triggered": True, "scope": "deep"}
    # La task est créée — on ne await pas, mais on vérifie l'appel
    client.app.state.auto_dream.deep_analyze.assert_called_once()


def test_trigger_deep_503_si_pas_d_autodream() -> None:
    """Si app.state.auto_dream absent, 503 même avec le flag actif."""
    app = FastAPI()
    app.include_router(router)
    # Pas de auto_dream injecté
    c = TestClient(app)
    with patch("jarvis.kernel.settings.settings.ingest_deep_enabled", True):
        r = c.post("/api/memory/trigger-deep")
    assert r.status_code == 503
    assert "autodream" in r.json()["detail"].lower()


def test_trigger_deep_flag_off_court_circuite_avant_lookup_autodream() -> None:
    """Même sans auto_dream injecté, le check du flag passe en premier.

    C'est important : le message d'erreur doit pointer le flag, pas un
    'AutoDream non disponible' qui désorienterait Barth.
    """
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    with patch("jarvis.kernel.settings.settings.ingest_deep_enabled", False):
        r = c.post("/api/memory/trigger-deep")
    assert r.status_code == 503
    # Le message doit mentionner le flag, pas l'absence d'auto_dream
    assert "ingest_deep_enabled" in r.json()["detail"].lower()
