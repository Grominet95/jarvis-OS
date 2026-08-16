# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "scripts" / "error_audit" / "error-codes.yaml"
REQUIRED = ("domain", "severity", "title_fr", "message_fr", "resolution_fr", "docs", "since")

_ASCII_FR_FORBIDDEN = (
    "non geree",
    "interceptee",
    "echec ",
    " echec",
    "echec.",
    " cle ",
    "depasse",
    "detecte",
    "verifie ",
    "regenerer ",
    "dependances",
    " generique",
    "peripherique",
    "deja ",
)


def test_registry_unique_codes() -> None:
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    assert len(raw) == len(set(raw.keys()))


def test_all_codes_have_required_fields() -> None:
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    for code, spec in raw.items():
        assert code.startswith("JRV-"), code
        for field in REQUIRED:
            assert field in spec and spec[field], f"{code} missing {field}"


def test_french_fields_avoid_ascii_placeholders() -> None:
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    for code, spec in raw.items():
        for field in ("title_fr", "message_fr", "resolution_fr"):
            text = spec[field].lower()
            for bad in _ASCII_FR_FORBIDDEN:
                assert bad.lower() not in text, f"{code}.{field} contains ASCII placeholder '{bad}'"


def test_registry_minimum_coverage() -> None:
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    assert len(raw) >= 70, f"expected at least 70 codes, got {len(raw)}"
