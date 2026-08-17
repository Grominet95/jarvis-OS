#!/usr/bin/env python3
"""Insert collector calls into except handlers without rewriting whole files."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "jarvis"

SKIP = {
    "kernel/error_collector.py",
    "kernel/error_emit.py",
    "kernel/error_hooks.py",
    "kernel/error_handlers.py",
    "kernel/_error_codes_generated.py",
    "kernel/preflight.py",
    "jarvis/app.py",
}

IMPORT_LINE = "from jarvis.kernel.error_collector import collector  # jrv: autofix\n"

PATH_RULES: list[tuple[str, str, str]] = [
    ("kernel/preflight.py", "JRV-KRN-011", "warning"),
    ("kernel/", "JRV-KRN-002", "error"),
    ("bootstrap.py", "JRV-BTS-001", "error"),
    ("providers/llm/", "JRV-LLM-002", "error"),
    ("providers/memory/", "JRV-MEM-001", "warning"),
    ("providers/audio/", "JRV-AUD-001", "warning"),
    ("providers/vision/", "JRV-VIS-001", "warning"),
    ("capabilities/tools/", "JRV-TOL-001", "error"),
    ("capabilities/skills/", "JRV-SKL-001", "error"),
    ("engine/mission/project_store.py", "JRV-MSN-002", "warning"),
    ("engine/mission/", "JRV-MSN-001", "error"),
    ("engine/proactive/", "JRV-PRO-001", "warning"),
    ("engine/background/", "JRV-BG-001", "warning"),
    ("engine/gateway.py", "JRV-GWY-001", "error"),
    ("engine/agent.py", "JRV-AGT-001", "error"),
    ("engine/budget.py", "JRV-BGT-001", "error"),
    ("interfaces/api/websocket.py", "JRV-WS-001", "error"),
    ("interfaces/api/", "JRV-API-001", "error"),
    ("interfaces/voice/", "JRV-VOI-001", "error"),
    ("interfaces/channels/", "JRV-MSG-001", "warning"),
    ("hardware/", "JRV-HW-001", "warning"),
    ("analytics/", "JRV-OPS-001", "warning"),
    ("engine/", "JRV-ENG-000", "error"),
]

EXCEPT_RE = re.compile(r"^(\s*)except\b(.*):\s*(#.*)?$")
MAPPED_RE = re.compile(
    r"collector\.|emit_to_stderr\(|raise_api_error\(|JarvisError\(|\# jrv:",
)


def code_for(rel: str) -> tuple[str, str]:
    norm = rel.replace("\\", "/")
    for prefix, code, level in PATH_RULES:
        if prefix in norm:
            return code, level
    return "JRV-ENG-000", "error"


def ensure_import(lines: list[str]) -> list[str]:
    if any("error_collector import collector" in ln for ln in lines):
        return lines
    insert_at = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("from __future__"):
            insert_at = i + 1
            i += 1
            continue
        if ln.startswith(("import ", "from ")):
            insert_at = i + 1
            if "(" in ln and ")" not in ln:
                i += 1
                while i < len(lines) and ")" not in lines[i]:
                    i += 1
                if i < len(lines):
                    insert_at = i + 1
            i += 1
            continue
        if insert_at > 0 and ln.strip() and not ln.strip().startswith("#"):
            break
        i += 1
    if insert_at == 0:
        for i, ln in enumerate(lines):
            if ln.startswith(("import ", "from ")):
                insert_at = i + 1
    lines.insert(insert_at, IMPORT_LINE)
    return lines


def fix_file(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if any(rel.endswith(s) for s in SKIP):
        return False
    text = path.read_text(encoding="utf-8")
    if "# jrv: autofix" in text and "collector." in text:
        return False
    lines = text.splitlines(keepends=True)
    code, level = code_for(rel)
    method = "warning" if level == "warning" else "error"
    changed = False
    i = 0
    while i < len(lines):
        m = EXCEPT_RE.match(lines[i].rstrip("\n"))
        if not m:
            i += 1
            continue
        indent, tail, _comment = m.group(1), m.group(2), m.group(3)
        block_start = i
        i += 1
        block_lines: list[str] = []
        while i < len(lines):
            ligne = lines[i]
            hors_bloc = (
                ligne.strip()
                and not ligne.startswith(indent + " ")
                and not ligne.strip().startswith("#")
            )
            if hors_bloc:
                nouvel_except = (
                    EXCEPT_RE.match(ligne.rstrip("\n"))
                    or ligne.startswith(indent + "except ")
                    or ligne.startswith("except ")
                )
                if nouvel_except:
                    break
                if len(lines[i]) - len(lines[i].lstrip()) <= len(indent) and lines[i].strip():
                    break
            block_lines.append(lines[i])
            i += 1
        block_text = "".join([lines[block_start]] + block_lines)
        if MAPPED_RE.search(block_text):
            continue
        as_m = re.search(r"\bas\s+(\w+)", tail)
        if as_m:
            var = as_m.group(1)
            insert = f'{indent}    collector.{method}("{code}", "{code}", cause={var})\n'
        else:
            insert = f'{indent}    collector.{method}("{code}", "{code}")\n'
        lines.insert(block_start + 1, insert)
        changed = True
        i = block_start + 2
    if not changed:
        return False
    lines = ensure_import(lines)
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    count = 0
    for path in sorted(SRC.rglob("*.py")):
        if fix_file(path):
            count += 1
            print(f"fixed {path.relative_to(ROOT)}")
    print(f"Fixed {count} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
