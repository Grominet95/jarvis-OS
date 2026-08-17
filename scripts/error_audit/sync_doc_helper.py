#!/usr/bin/env python3
"""Regenerate error-codes exports and rebuild Documentation_Helper/doc_index.sqlite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC_HELPER = ROOT / "scripts" / "doc_helper"


def main() -> int:
    steps: list[tuple[list[str], Path]] = [
        ([sys.executable, str(ROOT / "scripts" / "error_audit" / "generate_docs.py")], ROOT),
        (["npm", "run", "build-index"], DOC_HELPER),
    ]
    for cmd, cwd in steps:
        print(f">>> {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=cwd)
        if proc.returncode != 0:
            return proc.returncode
    print("Documentation_Helper sync OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
