"""Generate Documentation_Helper module cards and file-to-doc.yaml."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

ROOT = Path("src/jarvis")
DOC = Path("Documentation_Helper")
TODAY = str(date.today())
COMMIT = "local"

LAYER_MAP = {
    "kernel": "L0",
    "providers": "L1",
    "capabilities": "L1",
    "analytics": "L1",
    "hardware": "L1",
    "engine": "L2",
    "interfaces": "L3",
}


def layer_for(rel: Path) -> str:
    parts = rel.parts
    if not parts:
        return "L3"
    return LAYER_MAP.get(parts[0], "L3")


def doc_path_for(rel: Path) -> Path:
    parts = rel.parts
    if rel.stem == "__init__":
        name = (parts[-2] + "__init__") if len(parts) >= 2 else "jarvis__init__"
    else:
        name = rel.stem
    if parts[0] == "kernel":
        return DOC / "02-kernel" / "modules" / f"{name}.md"
    if parts[0] == "providers":
        if len(parts) == 1:
            return DOC / "03-providers" / f"{name}.md"
        if parts[-1] == "__init__.py":
            if len(parts) == 2:
                return DOC / "03-providers" / f"{name}.md"
            sub = "/".join(parts[1:-1])
            return DOC / "03-providers" / sub / f"{name}.md"
        if len(parts) > 2:
            sub = "/".join(parts[1:-1])
            return DOC / "03-providers" / sub / f"{name}.md"
        return DOC / "03-providers" / f"{name}.md"
    if parts[0] == "capabilities":
        sub = parts[1] if len(parts) > 1 else "root"
        if sub == "tools":
            return DOC / "04-capabilities" / "tools" / f"{name}.md"
        if sub == "skills":
            return DOC / "04-capabilities" / "skills" / f"{name}.md"
        return DOC / "04-capabilities" / f"{name}.md"
    if parts[0] == "engine":
        if len(parts) > 2 and parts[1] in ("mission", "proactive", "background"):
            return DOC / "05-engine" / parts[1] / f"{name}.md"
        return DOC / "05-engine" / f"{name}.md"
    if parts[0] == "interfaces":
        if len(parts) > 2 and parts[1] == "api":
            if parts[2] == "config":
                return DOC / "06-interfaces" / "api" / "config" / f"{name}.md"
            return DOC / "06-interfaces" / "api" / f"{name}.md"
        if len(parts) > 1 and parts[1] == "voice":
            return DOC / "06-interfaces" / f"voice_{name}.md"
        if len(parts) > 1 and parts[1] == "channels":
            return DOC / "06-interfaces" / f"channels_{name}.md"
        return DOC / "06-interfaces" / f"{name}.md"
    if parts[0] == "analytics":
        return DOC / "06-interfaces" / "analytics" / f"{name}.md"
    if parts[0] == "hardware":
        sub = parts[1] if len(parts) > 1 else "root"
        return DOC / "06-interfaces" / "hardware" / sub / f"{name}.md"
    return DOC / "06-interfaces" / f"{name}.md"


def analyze(path: Path) -> dict:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"doc": "", "classes": [], "functions": []}
    doc = ast.get_docstring(tree) or ""
    classes: list[str] = []
    funcs: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            funcs.append(node.name)
    first_line = doc.strip().split("\n")[0] if doc else ""
    return {"doc": first_line, "classes": classes[:8], "functions": funcs[:12]}


def main() -> None:
    yaml_lines = ["# Auto-generated file-to-doc mapping", "mappings:"]
    count = 0
    for py in sorted(ROOT.rglob("*.py")):
        rel = py.relative_to(ROOT)
        info = analyze(py)
        layer = layer_for(rel)
        dpath = doc_path_for(rel)
        dpath.parent.mkdir(parents=True, exist_ok=True)
        purpose = info["doc"] or f"Module `{rel.as_posix()}`."
        symbols: list[str] = []
        if info["classes"]:
            symbols.append("Classes: " + ", ".join(f"`{c}`" for c in info["classes"]))
        if info["functions"]:
            symbols.append("Functions: " + ", ".join(f"`{f}`" for f in info["functions"]))
        symbol_text = "; ".join(symbols) if symbols else "See source file."
        src_posix = rel.as_posix()
        lines = [
            f"# {rel.name}",
            "",
            f"- **Layer:** {layer}",
            f"- **Path:** `src/jarvis/{src_posix}`",
            f"- **Purpose:** {purpose}",
            f"- **Key symbols:** {symbol_text}",
            "- **Depends on:** See imports in source file (layer rules enforced by import-linter).",
            "- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.",
            "- **Config:** See `07-config/env-reference.md` if this module reads settings.",
            "- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.",
            "- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.",
            f"- **Source of truth:** [src/jarvis/{src_posix}](../../src/jarvis/{src_posix})",
            f"- **Last reviewed:** {TODAY} (jarvis-os @ {COMMIT})",
            "",
        ]
        dpath.write_text("\n".join(lines), encoding="utf-8")
        rel_doc = dpath.relative_to(DOC).as_posix()
        yaml_lines.append(f"  src/jarvis/{src_posix}: Documentation_Helper/{rel_doc}")
        count += 1

    (DOC / "maps").mkdir(parents=True, exist_ok=True)
    (DOC / "maps" / "file-to-doc.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    print(f"Generated {count} module cards")


if __name__ == "__main__":
    main()
