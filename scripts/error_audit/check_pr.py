#!/usr/bin/env python3
"""PR gate: registry sync + scan coverage."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
GENERATED = ROOT / "src" / "jarvis" / "kernel" / "_error_codes_generated.py"
GENERATE = SCRIPT_DIR / "generate_registry.py"
GENERATE_DOCS = SCRIPT_DIR / "generate_docs.py"
ERROR_CODES_MD = ROOT / "Documentation_Helper" / "09-operations" / "error-codes.md"
ERROR_CODES_JSON = ROOT / "scripts" / "doc_helper" / "error_codes.json"
SCAN = SCRIPT_DIR / "scan.py"


def check_registry_sync() -> int:
    if not GENERATED.exists():
        print(f"Missing {GENERATED}", file=sys.stderr)
        return 1
    before = GENERATED.read_bytes()
    proc = subprocess.run([sys.executable, str(GENERATE)], cwd=ROOT)
    if proc.returncode != 0:
        return proc.returncode
    after = GENERATED.read_bytes()
    if before != after:
        GENERATED.write_bytes(before)
        print(
            "ERROR: _error_codes_generated.py is out of sync with error-codes.yaml.\n"
            "Run: uv run python scripts/error_audit/generate_registry.py",
            file=sys.stderr,
        )
        return 1
    print("Registry sync OK")
    return 0


def check_scan() -> int:
    proc = subprocess.run([sys.executable, str(SCAN), "--check"], cwd=ROOT)
    return proc.returncode


def check_docs_export_sync() -> int:
    targets = (
        (ERROR_CODES_JSON, "error_codes.json"),
        (ERROR_CODES_MD, "error-codes.md"),
    )
    before: dict[Path, bytes] = {}
    for path, _ in targets:
        if path.exists():
            before[path] = path.read_bytes()
    proc = subprocess.run([sys.executable, str(GENERATE_DOCS)], cwd=ROOT)
    if proc.returncode != 0:
        return proc.returncode
    for path, label in targets:
        if not path.exists():
            print(f"ERROR: {label} was not generated", file=sys.stderr)
            return 1
        if path in before and before[path] != path.read_bytes():
            path.write_bytes(before[path])
            print(
                f"ERROR: {label} is out of sync with error-codes.yaml.\n"
                "Run: uv run python scripts/error_audit/generate_docs.py",
                file=sys.stderr,
            )
            return 1
    print("Docs export sync OK")
    return 0


def main() -> int:
    for fn in (check_registry_sync, check_docs_export_sync, check_scan):
        rc = fn()
        if rc != 0:
            return rc
    print("JRV error audit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
