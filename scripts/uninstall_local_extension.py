#!/usr/bin/env python3
"""Retire un symlink d'extension dev créé par install_local_extension.py.

Usage :
    python scripts/uninstall_local_extension.py mon-skill
    python scripts/uninstall_local_extension.py mon-preset
    python scripts/uninstall_local_extension.py ma-vue

Refuse d'agir sur autre chose qu'un symlink (sécurité).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def dev_root() -> Path:
    override = os.environ.get("JARVIS_DEV_EXTENSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".jarvis" / "extensions" / "dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retire un symlink d'extension dev.")
    parser.add_argument("name", help="Nom de l'extension à délier.")
    args = parser.parse_args(argv)

    removed: list[Path] = []
    refused: list[Path] = []

    for kind in ("skills", "presets", "views"):
        candidate = dev_root() / kind / args.name
        if candidate.is_symlink():
            candidate.unlink()
            removed.append(candidate)
        elif candidate.exists():
            refused.append(candidate)

    if refused:
        for p in refused:
            sys.stderr.write(f"Refus : '{p}' existe mais n'est pas un symlink. Ignoré.\n")

    if not removed:
        sys.stderr.write(f"Aucun lien dev pour '{args.name}'.\n")
        return 1 if not refused else 2

    for p in removed:
        print(f"Délié : {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
