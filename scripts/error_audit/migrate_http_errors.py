#!/usr/bin/env python3
"""Migrate raise HTTPException to raise_api_error with JRV codes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "src" / "jarvis" / "interfaces" / "api"

IMPORT = "from jarvis.kernel.http_errors import raise_api_error\n"

STATUS_CODE = {
    400: "JRV-API-004",
    401: "JRV-API-002",
    403: "JRV-PRM-001",
    404: "JRV-API-003",
    422: "JRV-API-004",
    503: "JRV-API-005",
}


def code_for_status(status: int) -> str:
    return STATUS_CODE.get(status, "JRV-API-001")


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "raise HTTPException" not in text:
        return False

    def repl_positional(m: re.Match[str]) -> str:
        status = int(m.group(1))
        detail = m.group(2)
        code = code_for_status(status)
        return f'raise_api_error("{code}", {status}, {detail})'

    def repl_keyword(m: re.Match[str]) -> str:
        status = int(m.group(1))
        detail = m.group(2)
        code = code_for_status(status)
        return f'raise_api_error("{code}", {status}, {detail})'

    new_text = text
    new_text = re.sub(
        r"raise HTTPException\(status_code=(\d+),\s*detail=([^)]+)\)",
        repl_keyword,
        new_text,
    )
    new_text = re.sub(
        r"raise HTTPException\((\d+),\s*([^)]+)\)",
        repl_positional,
        new_text,
    )

    if new_text == text:
        return False

    if "raise_api_error" not in text:
        lines = new_text.splitlines(keepends=True)
        insert_at = 0
        for i, ln in enumerate(lines):
            if ln.startswith("from __future__"):
                insert_at = i + 1
            elif ln.startswith(("import ", "from ")) and insert_at > 0:
                insert_at = i + 1
        lines.insert(insert_at, IMPORT)
        new_text = "".join(lines)

    new_text = new_text.replace(
        "from fastapi import APIRouter, HTTPException",
        "from fastapi import APIRouter",
    )
    new_text = new_text.replace(
        "from fastapi import HTTPException, ",
        "from fastapi import ",
    )
    new_text = new_text.replace(
        ", HTTPException",
        "",
    )
    if "HTTPException" in new_text and "raise HTTPException" not in new_text:
        new_text = re.sub(r"from fastapi import HTTPException\n", "", new_text)

    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    count = 0
    for path in sorted(API.rglob("*.py")):
        if migrate_file(path):
            count += 1
            print(f"migrated {path.relative_to(ROOT)}")
    print(f"Migrated {count} files")


if __name__ == "__main__":
    main()
