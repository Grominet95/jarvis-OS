# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Lookup and formatting for JRV error codes (registry + optional doc_index SQLite)."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from jarvis.kernel._error_codes_generated import ERROR_REGISTRY, ErrorSpec
from jarvis.kernel.paths import PROJECT_ROOT

JRV_CODE_RE = re.compile(r"JRV-[A-Z]{3}-\d{3}", re.IGNORECASE)
JRV_COMMAND_PREFIXES = ("/error", "!error", "/jrv", "!jrv")

DOC_INDEX_PATH = PROJECT_ROOT / "Documentation_Helper" / "doc_index.sqlite"


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def lookup_code(code: str) -> ErrorSpec | None:
    return ERROR_REGISTRY.get(normalize_code(code))


def extract_jrv_codes(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in JRV_CODE_RE.findall(text):
        norm = normalize_code(match)
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _sqlite_row(code: str) -> dict[str, Any] | None:
    if not DOC_INDEX_PATH.is_file():
        return None
    try:
        with sqlite3.connect(DOC_INDEX_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT code, domain, severity, title_fr, message_fr, resolution_fr, docs, modules
                FROM error_codes WHERE code = ?
                """,
                (normalize_code(code),),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:  # jrv: JRV-KRN-002 optional doc_index read
        return None


def format_jrv_reply(code: str) -> str:
    norm = normalize_code(code)
    if not JRV_CODE_RE.fullmatch(norm):
        return "Format attendu : `JRV-XXX-NNN` (ex. `JRV-KRN-011`)."

    spec = lookup_code(norm)
    if spec is None:
        return f"Code `{norm}` inconnu dans le registre JRV."

    sqlite_row = _sqlite_row(norm)
    title = spec.get("title_fr") or (sqlite_row or {}).get("title_fr") or norm
    message = spec.get("message_fr") or ""
    resolution = spec.get("resolution_fr") or ""
    severity = spec.get("severity") or "error"
    domain = spec.get("domain") or ""
    docs = list(spec.get("docs") or [])
    modules = list(spec.get("modules") or [])

    if sqlite_row:
        if sqlite_row.get("docs"):
            docs = [d for d in sqlite_row["docs"].split("|") if d]
        if sqlite_row.get("modules"):
            modules = [m for m in sqlite_row["modules"].split("|") if m]

    lines = [
        f"*{norm}* ({severity}, {domain})",
        f"*{title}*",
        "",
        message,
        "",
        f"*Résolution* — {resolution}",
    ]
    if docs:
        lines.extend(["", "*Docs*", *[f"• `{d}`" for d in docs]])
    if modules:
        lines.extend(["", "*Modules*", *[f"• `{m}`" for m in modules]])
    return "\n".join(lines)


def parse_jrv_command(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None

    lower = stripped.lower()
    for prefix in JRV_COMMAND_PREFIXES:
        if lower.startswith(prefix):
            rest = stripped[len(prefix) :].strip()
            if not rest:
                return "Usage : `/error JRV-XXX-NNN`"
            return format_jrv_reply(rest.split()[0])

    if JRV_CODE_RE.fullmatch(stripped):
        return format_jrv_reply(stripped)

    return None


def lookup_codes_json() -> dict[str, ErrorSpec]:
    return dict(ERROR_REGISTRY)
