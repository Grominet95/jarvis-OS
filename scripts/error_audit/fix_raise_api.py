#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[2] / "src" / "jarvis" / "interfaces" / "api"


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text = text
    new_text = re.sub(
        r"raise_api_error\(([^)]+)\)\s+from\s+None",
        r"raise_api_error(\1)",
        new_text,
    )
    new_text = re.sub(
        r"raise_api_error\((\"JRV-[^\"]+\",\s*\d+,\s*[^)]+)\)\s+from\s+(\w+)",
        r"raise_api_error(\1, cause=\2)",
        new_text,
    )
    new_text = re.sub(
        r"^\s*collector\.error\([^\n]+\n(\s*raise_api_error)",
        r"\1",
        new_text,
        flags=re.MULTILINE,
    )
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> None:
    for path in sorted(API.rglob("*.py")):
        if fix_file(path):
            print(path.relative_to(API.parent.parent.parent))


if __name__ == "__main__":
    main()
