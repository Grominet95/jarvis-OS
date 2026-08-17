# Copyright (C) 2026 Barthélemy Houot
# Tests for JRV error doc lookup (registry + optional SQLite).

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.kernel.error_doc_lookup import (
    extract_jrv_codes,
    format_jrv_reply,
    lookup_code,
    normalize_code,
    parse_jrv_command,
)


def test_normalize_code() -> None:
    assert normalize_code("jrv-krn-011") == "JRV-KRN-011"


def test_lookup_known_code() -> None:
    spec = lookup_code("JRV-KRN-011")
    assert spec is not None
    assert spec.get("domain") == "KRN"


def test_format_jrv_reply_known() -> None:
    text = format_jrv_reply("JRV-KRN-011")
    assert "JRV-KRN-011" in text
    assert "Résolution" in text


def test_format_jrv_reply_unknown() -> None:
    text = format_jrv_reply("JRV-ZZZ-999")
    assert "inconnu" in text


def test_extract_jrv_codes() -> None:
    assert extract_jrv_codes("log: [JRV-TOL-001] failed") == ["JRV-TOL-001"]


def test_parse_jrv_command_slash() -> None:
    reply = parse_jrv_command("/error JRV-KRN-011")
    assert reply is not None
    assert "JRV-KRN-011" in reply


def test_parse_jrv_command_bare_code() -> None:
    reply = parse_jrv_command("JRV-KRN-011")
    assert reply is not None
    assert "JRV-KRN-011" in reply


def test_parse_jrv_command_normal_message() -> None:
    assert parse_jrv_command("Quelle est la météo ?") is None


def test_format_jrv_reply_uses_sqlite_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "doc_index.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE error_codes (
              code TEXT PRIMARY KEY,
              domain TEXT NOT NULL,
              severity TEXT NOT NULL,
              title_fr TEXT NOT NULL,
              message_fr TEXT NOT NULL,
              resolution_fr TEXT NOT NULL,
              docs TEXT NOT NULL DEFAULT '',
              since TEXT NOT NULL DEFAULT '',
              modules TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO error_codes (
              code, domain, severity, title_fr, message_fr, resolution_fr, docs, since, modules
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "JRV-KRN-011",
                "KRN",
                "error",
                "SQLite title",
                "msg",
                "fix",
                "09-operations/troubleshooting.md",
                "0.3.3",
                "kernel/preflight.py",
            ),
        )

    import jarvis.kernel.error_doc_lookup as mod

    monkeypatch.setattr(mod, "DOC_INDEX_PATH", db_path)
    text = format_jrv_reply("JRV-KRN-011")
    assert "troubleshooting.md" in text
