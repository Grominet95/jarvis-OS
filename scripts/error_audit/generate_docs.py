#!/usr/bin/env python3
"""Generate Documentation_Helper/09-operations/error-codes.md from YAML."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = Path(__file__).resolve().parent / "error-codes.yaml"
OUT_PATH = ROOT / "Documentation_Helper" / "09-operations" / "error-codes.md"
JSON_PATH = ROOT / "scripts" / "doc_helper" / "error_codes.json"


def main() -> int:
    if not YAML_PATH.exists():
        print(f"Missing {YAML_PATH}", file=sys.stderr)
        return 1

    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    lines = [
        "# Error codes reference",
        "",
        "Auto-generated from `scripts/error_audit/error-codes.yaml`. Do not edit manually.",
        "",
        "Terminal format: `[JRV-XXX-NNN] ERROR|WARN|IMPOSSIBLE: message`",
        "",
        "| Code | Severity | Title | Resolution | Docs |",
        "|------|----------|-------|------------|------|",
    ]

    for code in sorted(raw.keys()):
        spec = raw[code]
        sev = spec.get("severity", "error")
        title = spec.get("title_fr", "").replace("|", "\\|")
        resolution = spec.get("resolution_fr", "").replace("|", "\\|").replace("\n", " ")
        docs = ", ".join(f"`{d}`" for d in spec.get("docs", []))
        lines.append(f"| `{code}` | {sev} | {title} | {resolution} | {docs} |")

    lines += [
        "",
        "## Related docs",
        "",
        "- [troubleshooting.md](troubleshooting.md)",
        "- [logs-and-doctor.md](logs-and-doctor.md)",
        "- [error-collector-guide.md](../00-meta/error-collector-guide.md)",
        "",
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUT_PATH} ({len(raw)} codes)")
    print(f"Generated {JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
