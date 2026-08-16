#!/usr/bin/env python3
"""Scan src/jarvis for unmapped error sites (except/raise without JRV emit)."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "jarvis"
INVENTORY = Path(__file__).resolve().parent / "inventory.json"

MAPPED_MARKERS = (
    "collector.",
    "emit_to_stderr(",
    "_emit_stderr(",
    "_err(",
    "_warn(",
    "JarvisError(",
    "raise JarvisError",
    "raise_api_error(",
    "# jrv:",
    "jrv-error:",
)

PATH_DEFAULT_CODE: list[tuple[str, str]] = [
    ("kernel/preflight.py", "JRV-KRN-011"),
    ("kernel/", "JRV-KRN-002"),
    ("bootstrap.py", "JRV-BTS-001"),
    ("providers/llm/", "JRV-LLM-002"),
    ("providers/memory/", "JRV-MEM-001"),
    ("providers/audio/", "JRV-AUD-001"),
    ("providers/vision/", "JRV-VIS-001"),
    ("capabilities/tools/", "JRV-TOL-001"),
    ("capabilities/skills/", "JRV-SKL-001"),
    ("engine/mission/", "JRV-MSN-001"),
    ("engine/proactive/", "JRV-PRO-001"),
    ("engine/background/", "JRV-BG-001"),
    ("engine/gateway.py", "JRV-GWY-001"),
    ("engine/agent.py", "JRV-AGT-001"),
    ("engine/budget.py", "JRV-BGT-001"),
    ("interfaces/api/websocket.py", "JRV-WS-001"),
    ("interfaces/api/", "JRV-API-001"),
    ("interfaces/voice/", "JRV-VOI-001"),
    ("interfaces/channels/", "JRV-MSG-001"),
    ("hardware/", "JRV-HW-001"),
    ("analytics/", "JRV-OPS-001"),
    ("engine/", "JRV-ENG-000"),
]


@dataclass
class Site:
    file: str
    line: int
    kind: str
    snippet: str
    mapped: bool
    suggested_code: str


def default_code(rel: str) -> str:
    norm = rel.replace("\\", "/")
    for prefix, code in PATH_DEFAULT_CODE:
        if prefix in norm:
            return code
    return "JRV-ENG-000"


def body_mapped(source: str, node: ast.AST) -> bool:
    if isinstance(node, ast.Raise):
        return True
    try:
        segment = ast.get_source_segment(source, node) or ""
    except (TypeError, ValueError):
        segment = ""
    return any(m in segment for m in MAPPED_MARKERS)


def http_raise_mapped(source: str, node: ast.Raise) -> bool:
    segment = ast.get_source_segment(source, node) or ""
    if "raise_api_error(" in segment or "[JRV-" in segment:
        return True
    if "raise_api_error" in source and "HTTPException" not in segment:
        return False
    return False


def scan_file(path: Path) -> list[Site]:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    sites: list[Site] = []
    code = default_code(rel)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            mapped = body_mapped(source, node)
            if not mapped and node.body:
                mapped = all(body_mapped(source, b) for b in node.body)
            snippet = (ast.get_source_segment(source, node) or "")[:120].replace("\n", " ")
            sites.append(
                Site(
                    file=rel,
                    line=node.lineno,
                    kind="except",
                    snippet=snippet,
                    mapped=mapped,
                    suggested_code=code,
                )
            )
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            func = node.exc.func
            name = getattr(func, "id", None) or getattr(func, "attr", None) or ""
            if name == "HTTPException":
                snippet = (ast.get_source_segment(source, node) or "")[:120]
                sites.append(
                    Site(
                        file=rel,
                        line=node.lineno,
                        kind="raise_http",
                        snippet=snippet,
                        mapped=http_raise_mapped(source, node),
                        suggested_code=code,
                    )
                )
            elif name == "JarvisError":
                mapped = "JRV-" in (ast.get_source_segment(source, node) or "")
                sites.append(
                    Site(
                        file=rel,
                        line=node.lineno,
                        kind="raise_jarvis",
                        snippet=(ast.get_source_segment(source, node) or "")[:120],
                        mapped=mapped,
                        suggested_code=code,
                    )
                )

    if "# jrv: file-mapped" in source:
        for s in sites:
            s.mapped = True
    return sites


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    all_sites: list[Site] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name.startswith("_error_codes"):
            continue
        if path.name == "http_errors.py":
            continue
        all_sites.extend(scan_file(path))

    unmapped = [s for s in all_sites if not s.mapped]
    payload = {
        "total": len(all_sites),
        "unmapped_count": len(unmapped),
        "sites": [asdict(s) for s in all_sites],
    }

    if args.write or not args.check:
        INVENTORY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {INVENTORY} — {len(unmapped)} unmapped / {len(all_sites)} total")

    if args.check:
        if unmapped:
            print(f"FAIL: {len(unmapped)} unmapped error sites", file=sys.stderr)
            for s in unmapped[:30]:
                print(f"  {s.file}:{s.line} [{s.kind}] -> {s.suggested_code}", file=sys.stderr)
            if len(unmapped) > 30:
                print(f"  ... and {len(unmapped) - 30} more", file=sys.stderr)
            return 1
        print(f"OK: all {len(all_sites)} sites mapped")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
