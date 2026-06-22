# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests du serveur de preview de vue (scripts/preview_view.py).

Vérifie :
- GET / renvoie une page HTML qui référence /view.js et /_shared.js et qui
  contient le view_id.
- GET /view.js renvoie le fichier source.
- GET /_shared.js renvoie le vrai _shared.js du repo.
- GET /view.css → 404 quand absent (cf. CDC, view.css optionnel).
- WebSocket : un message envoyé est rebroadcasté (loopback fidèle à home.js).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from preview_view import build_app  # noqa: E402


def _make_view(tmp_path: Path, name: str = "ma-vue", with_css: bool = False) -> Path:
    src = tmp_path / name
    src.mkdir()
    (src / "view.js").write_text(
        "/* fake view */\nwindow.Jarvis?.views?.register('" + name + "', {});\n"
    )
    if with_css:
        (src / "view.css").write_text("body { color: red; }")
    return src


def test_index_referenced_assets(tmp_path: Path) -> None:
    src = _make_view(tmp_path)
    app = build_app(src, "ma-vue")
    client = TestClient(app)

    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "/view.js" in body
    assert "/_shared.js" in body
    assert "ma-vue" in body  # view_id présent (titre + JS)
    assert "/ws/preview" in body


def test_view_js_served(tmp_path: Path) -> None:
    src = _make_view(tmp_path)
    app = build_app(src, "ma-vue")
    client = TestClient(app)

    r = client.get("/view.js")
    assert r.status_code == 200
    assert "fake view" in r.text


def test_shared_js_served(tmp_path: Path) -> None:
    src = _make_view(tmp_path)
    app = build_app(src, "ma-vue")
    client = TestClient(app)

    r = client.get("/_shared.js")
    assert r.status_code == 200
    # _shared.js contient le contrat Jarvis.views.register
    assert "Jarvis.views" in r.text


def test_view_css_optionnel_404(tmp_path: Path) -> None:
    src = _make_view(tmp_path, with_css=False)
    app = build_app(src, "ma-vue")
    client = TestClient(app)
    assert client.get("/view.css").status_code == 404


def test_view_css_servi_si_present(tmp_path: Path) -> None:
    src = _make_view(tmp_path, with_css=True)
    app = build_app(src, "ma-vue")
    client = TestClient(app)
    r = client.get("/view.css")
    assert r.status_code == 200
    assert "color: red" in r.text


def test_ws_loopback(tmp_path: Path) -> None:
    """Un client envoie un message → il le reçoit (le serveur broadcast à tous
    les clients connectés, c'est le contrat fidèle à home.js)."""
    src = _make_view(tmp_path)
    app = build_app(src, "ma-vue")
    client = TestClient(app)

    with client.websocket_connect("/ws/preview") as ws:
        payload = {
            "type": "view_command",
            "view_id": "ma-vue",
            "command": "fly_to",
            "params": {"location": "Paris"},
        }
        ws.send_text(json.dumps(payload))
        echoed = ws.receive_text()
        assert json.loads(echoed) == payload
