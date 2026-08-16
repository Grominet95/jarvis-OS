#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "jarvis"
PAT = re.compile(
    r'collector\.(error|warning)\("(?P<code>JRV-[^"]+)", '
    r'"Exception in handler \((?P=code)\)"(?:, cause=(?P<cause>\w+))?\)'
)


def main() -> None:
    total = 0
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        def repl(m: re.Match[str]) -> str:
            cause = f", cause={m.group('cause')}" if m.group("cause") else ""
            return f'collector.{m.group(1)}("{m.group("code")}", "{m.group("code")}"{cause})'

        new_text, n = PAT.subn(repl, text)
        if n:
            path.write_text(new_text, encoding="utf-8")
            total += n
    print(f"Shortened {total} collector calls")


if __name__ == "__main__":
    main()
