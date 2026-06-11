#!/usr/bin/env python3
"""Snapshot trié de toutes les routes FastAPI (méthode + path).

Usage : uv run python scripts/migration/snapshot_routes.py > routes.txt

Tout gate de routes ultérieur (B5b, C7b, E2b) est un `diff` contre
la baseline capturée en Phase A — sortie vide exigée.
"""

from __future__ import annotations

try:
    from jarvis.app import app  # lazy: fallback main pour compat Phase A
except ImportError:
    from main import app  # lazy: fallback main pour compat Phase A

rows: list[str] = []
for r in app.routes:
    methods = getattr(r, "methods", None)
    if methods:
        rows += [f"{m:7} {r.path}" for m in sorted(methods)]
    else:
        rows.append(f"{type(r).__name__:7} {r.path}")

print("\n".join(sorted(set(rows))))
