#!/usr/bin/env python3
"""Lie une extension `jarvis-skills` dans la zone dev de Jarvis (symlink).

Usage :
    python scripts/install_local_extension.py ../jarvis-skills/skills/mon-skill
    python scripts/install_local_extension.py ../jarvis-skills/presets/mon-preset
    python scripts/install_local_extension.py ../jarvis-skills/views/ma-vue

Comportement (cf. CDC §1) :
  1. Détecte le type via le manifest (champ `type` en priorité, heuristique en
     fallback).
  2. Valide d'abord avec `<repo>/scripts/validate_catalog.py` du chantier
     `jarvis-skills`. Refus si le validateur n'existe pas ou retourne ≠ 0.
  3. Crée un symlink `~/.jarvis/extensions/dev/<type>/<name>` → source.
     Aucune copie. Lien existant remplacé proprement.
  4. Affiche la commande de test recommandée.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def detect_type(src: Path) -> str:
    """Renvoie 'skill' | 'preset' | 'view'.

    Source de vérité : champ `type` du manifest (alignement avec
    validate_catalog.py côté jarvis-skills). Heuristique en fallback.
    """
    # 1) skill.yaml (skills + presets)
    skill_yaml = src / "skill.yaml"
    if skill_yaml.exists():
        with skill_yaml.open() as f:
            meta = yaml.safe_load(f) or {}
        declared = (meta.get("type") or "").lower()
        if declared in {"preset"}:
            return "preset"
        if declared in {"view"}:
            return "view"
        if declared in {"conversational", "skill"}:
            return "skill"
        # Heuristique : steps présents → preset
        if meta.get("steps"):
            return "preset"
        return "skill"

    # 2) VIEW.md (format vue)
    view_md = src / "VIEW.md"
    if view_md.exists():
        return "view"

    # 3) Heuristique pure : présence de view.js
    if (src / "view.js").exists():
        return "view"

    raise SystemExit(
        f"Impossible de déterminer le type de '{src}'. "
        "Attendu : skill.yaml (avec champ type), ou VIEW.md, ou view.js."
    )


def read_name(src: Path, ext_type: str) -> str:
    """Nom canonique de l'extension. Manifest > nom du dossier."""
    if ext_type == "view":
        view_md = src / "VIEW.md"
        if view_md.exists():
            text = view_md.read_text(encoding="utf-8")
            if text.startswith("---"):
                _, _, rest = text.partition("---")
                yaml_block, _, _ = rest.partition("---")
                meta = yaml.safe_load(yaml_block) or {}
                # id prioritaire (utilisé par Jarvis.views.register), sinon name
                return meta.get("id") or meta.get("name") or src.name
    skill_yaml = src / "skill.yaml"
    if skill_yaml.exists():
        with skill_yaml.open() as f:
            meta = yaml.safe_load(f) or {}
        return meta.get("name") or src.name
    return src.name


def run_validate_catalog(src: Path) -> None:
    """Appelle <repo_jarvis-skills>/scripts/validate_catalog.py sur la source.

    Refuse proprement si le validateur n'existe pas (chantier jarvis-skills
    pas encore livré) ou si la validation échoue.
    """
    # <repo>/{skills|presets|views}/<name> → repo = src.parent.parent
    repo_root = src.parent.parent
    validator = repo_root / "scripts" / "validate_catalog.py"

    if not validator.exists():
        raise SystemExit(
            f"Validateur introuvable : {validator}\n"
            "Ce script suppose le chantier `jarvis-skills` livré "
            "(scripts/validate_catalog.py). Valide ton extension côté "
            "jarvis-skills d'abord, ou aligne le repo amont."
        )

    proc = subprocess.run(  # noqa: S603 — chemin contrôlé
        [sys.executable, str(validator), str(src)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(
            f"\nValidation refusée par validate_catalog.py (rc={proc.returncode}). "
            "Corrige l'extension côté jarvis-skills avant de la lier."
        )


def dev_root() -> Path:
    """Racine de la zone dev — aligné avec skills/dev_extensions.dev_root()."""
    import os

    override = os.environ.get("JARVIS_DEV_EXTENSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".jarvis" / "extensions" / "dev"


_DIR_BY_TYPE = {"skill": "skills", "preset": "presets", "view": "views"}


def link(src: Path, ext_type: str, name: str) -> Path:
    """Crée le symlink. Remplace un lien existant (même destination ou non)."""
    dst_parent = dev_root() / _DIR_BY_TYPE[ext_type]
    dst_parent.mkdir(parents=True, exist_ok=True)
    dst = dst_parent / name

    if dst.exists() or dst.is_symlink():
        if dst.is_symlink():
            dst.unlink()
        else:
            raise SystemExit(
                f"'{dst}' existe et n'est pas un symlink. "
                "Refuse d'écraser un vrai dossier — supprime-le à la main si voulu."
            )
    dst.symlink_to(src.resolve())
    return dst


def print_next_steps(ext_type: str, name: str, src: Path) -> None:
    print(f"\nExtension liée : {name} ({ext_type})")
    print("Étape suivante :")
    if ext_type == "skill":
        print(f"  Skill   : relance Jarvis et essaie : « utilise {name} pour … »")
    elif ext_type == "preset":
        print(f"  Preset  : python scripts/dry_run_preset.py {name}")
    elif ext_type == "view":
        print(f"  Vue     : python scripts/preview_view.py {src}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lie une extension jarvis-skills en zone dev.")
    parser.add_argument("source", type=Path, help="Chemin vers le dossier de l'extension.")
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Saute la validation (DANGEREUX — réservé aux tests internes).",
    )
    args = parser.parse_args(argv)

    src: Path = args.source
    if not src.is_dir():
        sys.stderr.write(f"Source introuvable ou pas un dossier : {src}\n")
        return 2

    ext_type = detect_type(src)
    name = read_name(src, ext_type)

    if not args.skip_validate:
        run_validate_catalog(src)

    dst = link(src, ext_type, name)
    print(f"Symlink créé : {dst} -> {src.resolve()}")
    print_next_steps(ext_type, name, src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
