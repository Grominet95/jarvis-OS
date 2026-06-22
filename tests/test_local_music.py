# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from jarvis.interfaces.api import local_music

# En-tête PNG minimal (signature + IHDR partiel) pour le sniff de type.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_backend_prefers_macos_when_nowplaying_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    assert local_music._backend() == "macos"


def test_backend_is_linux_when_no_nowplaying_cli_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "platform", "linux")
    assert local_music._backend() == "linux"


def test_backend_none_when_no_tool_and_not_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert local_music._backend() is None


def test_state_from_mpris_playing_track() -> None:
    metadata = {
        "xesam:title": "bad guy",
        "xesam:artist": ["BillieEilishVEVO"],
        "xesam:album": "WHEN WE ALL FALL ASLEEP",
        "mpris:artUrl": "https://i.example/cover.jpg",
        "mpris:length": 205941000,  # microsecondes
    }
    state = local_music._state_from_mpris("Playing", metadata, 155009342)
    assert state == {
        "connected": True,
        "is_playing": True,
        "track": "bad guy",
        "artist": "BillieEilishVEVO",
        "album": "WHEN WE ALL FALL ASLEEP",
        "album_art": "https://i.example/cover.jpg",
        "progress_ms": 155009,
        "duration_ms": 205941,
    }


def test_resolve_art_passes_http_through() -> None:
    assert local_music._resolve_art("https://x/y.jpg") == "https://x/y.jpg"


def test_resolve_art_embeds_local_file_as_data_uri(tmp_path: Path) -> None:
    f = tmp_path / "cover"
    f.write_bytes(_PNG_BYTES)
    result = local_music._resolve_art(f.as_uri())
    assert result is not None
    assert result.startswith("data:image/png;base64,")


def test_resolve_art_none_for_missing_file() -> None:
    assert local_music._resolve_art("file:///tmp/does-not-exist-xyz.png") is None


def test_resolve_art_none_for_empty_or_other_scheme() -> None:
    assert local_music._resolve_art("") is None
    assert local_music._resolve_art("ftp://x/y") is None


def test_state_from_mpris_joins_multiple_artists() -> None:
    metadata = {"xesam:title": "Song", "xesam:artist": ["A", "B"], "mpris:length": 0}
    state = local_music._state_from_mpris("Paused", metadata, 0)
    assert state["artist"] == "A, B"
    assert state["is_playing"] is False
    assert state["album_art"] is None


def test_state_from_mpris_no_title_means_nothing_playing() -> None:
    state = local_music._state_from_mpris("Stopped", {"xesam:title": ""}, 0)
    assert state == {"connected": True, "is_playing": False, "track": None}
