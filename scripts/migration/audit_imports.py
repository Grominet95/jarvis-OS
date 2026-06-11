#!/usr/bin/env python3
"""Détecteur AST des imports différés inter-packages.

Remplace le grep ligne-à-ligne historique de `audit_imports.sh` qui matchait
aussi du texte à l'intérieur des docstrings et des chaînes (`textwrap.dedent`,
f-strings multilignes contenant un skill.py généré, etc.). L'AST ne voit que
les vrais ImportFrom du code — pas les chaînes — donc un compteur à 0 reste
à 0, sans « 3 faux positifs connus ».

Un import est compté comme **différé inter-packages** ssi :
  - c'est un `ast.ImportFrom` (pas un `Import`),
  - son module non-vide commence par un des packages de PKGS,
  - il a au moins un ancêtre `FunctionDef` ou `AsyncFunctionDef`
    (lazy au sens architectural : ne s'exécute que sur appel),
  - aucun ancêtre n'est `if TYPE_CHECKING:` (zéro coût runtime — autorisé),
  - la ligne source ne contient pas `# lazy:` (échappement explicite
    documenté pour les deps lourdes optionnelles ou patterns défensifs).

Format de sortie identique à l'ancien grep pour les downstream consumers
(`cut -d: -f1 | sort -u | wc -l`, etc.) :
    ./relative/path.py:LINENO:source-line

Exit code : 0.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

PKGS: frozenset[str] = frozenset(
    {
        "core",
        "memory",
        "tools",
        "skills",
        "agent",
        "api",
        "proactive",
        "channels",
        "background",
        "llm",
        "config",
        "audio",
        "vision",
        "kernel",
        "jarvis",
    }
)

EXCLUDE_DIRS: frozenset[str] = frozenset({".git", "tests", ".venv", "__pycache__", "workspace"})


def _is_inter_pkg(module: str | None) -> bool:
    if not module:
        return False
    root = module.split(".", 1)[0]
    return root in PKGS


def _build_parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _is_type_checking_if(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    return isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


def _ancestors(node: ast.AST, parents: dict[int, ast.AST]) -> Iterator[ast.AST]:
    cur = parents.get(id(node))
    while cur is not None:
        yield cur
        cur = parents.get(id(cur))


def collect(file_path: Path, source: str, source_lines: list[str]) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    parents = _build_parents(tree)
    results: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not _is_inter_pkg(node.module):
            continue
        in_function = False
        in_type_checking = False
        for anc in _ancestors(node, parents):
            if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef)):
                in_function = True
            if _is_type_checking_if(anc):
                in_type_checking = True
        if not in_function:
            continue
        if in_type_checking:
            continue
        line_idx = node.lineno - 1
        if line_idx < 0 or line_idx >= len(source_lines):
            continue
        source_line = source_lines[line_idx]
        if "# lazy:" in source_line:
            continue
        results.append((node.lineno, source_line))

    return results


def iter_py_files(base: Path) -> Iterator[Path]:
    for path in base.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.relative_to(base).parts):
            continue
        yield path


def main(argv: list[str]) -> int:
    base = Path(argv[1] if len(argv) > 1 else ".").resolve()
    for path in sorted(iter_py_files(base)):
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = src.splitlines()
        hits = collect(path, src, lines)
        if not hits:
            continue
        try:
            rel = path.relative_to(base)
        except ValueError:
            rel = path
        for lineno, line in hits:
            print(f"./{rel}:{lineno}:{line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
