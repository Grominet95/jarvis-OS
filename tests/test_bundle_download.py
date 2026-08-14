# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from unittest.mock import patch

from jarvis.kernel.bundle_download import (
    BUNDLE_ZIP_BYTES,
    BUNDLE_ZIP_URL,
    _zip_member_dest,
    bundle_download_info,
    get_download_status,
    start_bundle_download,
)


def test_bundle_download_info_uses_zip() -> None:
    info = bundle_download_info()
    assert info["zip_url"] == BUNDLE_ZIP_URL
    assert info["zip_bytes"] == BUNDLE_ZIP_BYTES


def test_zip_member_dest_strips_bundle_prefix() -> None:
    assert _zip_member_dest("bundle/manifest.json") == "manifest.json"
    assert _zip_member_dest("manifest.json") == "manifest.json"
    assert _zip_member_dest("bundle/") is None


def test_start_bundle_download_when_already_present() -> None:
    with patch("jarvis.kernel.bundle_download.bundle_available", return_value=True):
        resp = start_bundle_download()
    assert resp["started"] is False
    assert resp["reason"] == "already_present"


def test_get_download_status_idle_by_default() -> None:
    with patch(
        "jarvis.kernel.bundle_download._state",
        {
            "running": False,
            "phase": "idle",
            "percent": 0,
            "message": "",
            "error": None,
            "bytes_downloaded": 0,
            "bytes_total": BUNDLE_ZIP_BYTES,
            "speed_mb_s": None,
            "eta_seconds": None,
        },
    ):
        with patch("jarvis.kernel.bundle_download.bundle_available", return_value=False):
            with patch("jarvis.kernel.bundle_download.prerequisites_status", return_value={}):
                st = get_download_status()
    assert st["phase"] == "idle"


def test_get_download_status_returns_done_once() -> None:
    with patch(
        "jarvis.kernel.bundle_download._state",
        {
            "running": False,
            "phase": "done",
            "percent": 100,
            "message": "Bundle installed",
            "error": None,
            "bytes_downloaded": BUNDLE_ZIP_BYTES,
            "bytes_total": BUNDLE_ZIP_BYTES,
            "speed_mb_s": None,
            "eta_seconds": None,
        },
    ):
        with patch("jarvis.kernel.bundle_download.bundle_available", return_value=True):
            with patch("jarvis.kernel.bundle_download.prerequisites_status", return_value={"can_continue": True}):
                st = get_download_status()
    assert st["phase"] == "done"
    assert st["prerequisites"]["can_continue"] is True
