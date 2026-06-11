#!/usr/bin/env python3
"""Affiche la séquence qu'un preset exécuterait, sans rien lancer (CDC §3).

Usage :
    python scripts/dry_run_preset.py mon-preset

Visualisation seulement — aucun side-effect. Cherche le preset d'abord
dans ~/.jarvis/extensions/dev/presets/<name>, puis dans skills/installed/
<name>. La sécurité réelle reste assurée par :
  - le validateur statique côté jarvis-skills (champ requires_confirmation),
  - la confirmation à l'exécution réelle.
Le dry-run signale, il ne bloque pas.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).parent.parent

# Heuristique destructif : motifs sur la commande CLI résolue. Non exhaustif —
# c'est un signalement visuel, pas un garde-fou.
_DESTRUCTIVE_PATTERNS = [
    re.compile(r"\brm\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\b"),
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bmkdir\b"),
    re.compile(r"\s>\s|\s>>\s"),  # redirection vers un fichier
    re.compile(r"osascript -e .*\b(delete|quit|shutdown)\b", re.IGNORECASE),
]


def dev_root() -> Path:
    override = os.environ.get("JARVIS_DEV_EXTENSIONS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".jarvis" / "extensions" / "dev"


def find_preset(name: str) -> Path | None:
    """Cherche le preset dans la zone dev d'abord, puis dans installed."""
    candidates = [
        dev_root() / "presets" / name,
        dev_root() / "skills" / name,  # certains presets vivent côté skills/ (cf. jarvis-skills)
        REPO / "skills" / "installed" / name,
    ]
    for c in candidates:
        if (c / "skill.yaml").exists():
            return c
    return None


def _resolve_cli(step: dict) -> tuple[str | None, str]:
    """Renvoie (commande, raison-si-skip)."""
    cmd = step.get("command")
    if cmd:
        return cmd, ""
    platforms_map = step.get("platforms") or {}
    if platforms_map:
        system = platform.system().lower()
        key = "mac" if system == "darwin" else system
        if key in platforms_map:
            return platforms_map[key], ""
        return None, f"non supporté sur {system}"
    return None, "ni command ni platforms"


def _is_destructive(cmd: str) -> bool:
    return any(p.search(cmd) for p in _DESTRUCTIVE_PATTERNS)


@dataclass
class FormattedStep:
    index: int
    name: str
    type: str
    body: str
    tags: list[str]


def format_step(i: int, step: dict) -> FormattedStep:
    stype = step.get("type", "?")
    name = step.get("name") or f"step-{i}"
    tags: list[str] = []
    if step.get("requires_confirmation"):
        tags.append("CONFIRMATION")

    if stype == "cli":
        cmd, skip_reason = _resolve_cli(step)
        if cmd is None:
            body = f"(skip — {skip_reason})"
        else:
            body = f"$ {cmd}"
            if _is_destructive(cmd):
                tags.append("DESTRUCTIF (heuristique)")
    elif stype == "spotify":
        action = step.get("action", "play")
        query = step.get("query", "")
        body = f"spotify_control(action={action!r}, query={query!r})"
    elif stype == "tts":
        body = f"TTS : {step.get('text', '')[:120]}"
    elif stype == "ai":
        body = f"LLM prompt : {step.get('prompt', '')[:120]}"
    elif stype == "wait":
        secs = max(0, min(int(step.get("seconds", 1)), 30))
        body = f"sleep {secs}s"
    elif stype == "notify":
        body = f"notif : title={step.get('title', '')!r} body={step.get('body', '')!r}"
    else:
        body = f"(type inconnu : {stype})"

    return FormattedStep(index=i, name=name, type=stype, body=body, tags=tags)


def print_dry_run(name: str, preset_dir: Path, yaml_meta: dict) -> None:
    print(f"\nDry-run preset : {name}")
    print(f"Source         : {preset_dir}")
    print("Visualisation seulement — aucun effet de bord.")
    print(
        "Sécurité réelle = requires_confirmation (validé statiquement amont) "
        "+ confirmation à l'exécution.\n"
    )

    apps = yaml_meta.get("requires_apps") or []
    if apps:
        print("Applications requises :")
        for a in apps:
            label = a.get("name") if isinstance(a, dict) else a
            print(f"  - {label}")
        print()

    steps = yaml_meta.get("steps") or []
    if not steps:
        print("(aucun step déclaré dans skill.yaml)")
        return

    total = len(steps)
    print(f"Séquence ({total} step{'s' if total > 1 else ''}) :")
    for i, raw in enumerate(steps, 1):
        fs = format_step(i, raw)
        tag_str = "  " + "  ".join(f"[{t}]" for t in fs.tags) if fs.tags else ""
        print(f"  {fs.index:>2}. [{fs.type}] {fs.name}{tag_str}")
        print(f"        {fs.body}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Affiche la séquence d'un preset sans l'exécuter.")
    parser.add_argument("name", help="Nom du preset (ex. mode-streameur).")
    args = parser.parse_args(argv)

    preset_dir = find_preset(args.name)
    if preset_dir is None:
        sys.stderr.write(
            f"Preset '{args.name}' introuvable dans la zone dev "
            f"(~/.jarvis/extensions/dev/) ni dans skills/installed/.\n"
        )
        return 1

    with (preset_dir / "skill.yaml").open() as f:
        yaml_meta = yaml.safe_load(f) or {}

    # Sanity check : on ne dry-run que des presets (pas des skills conversationnels).
    declared_type = (yaml_meta.get("type") or "").lower()
    has_steps = bool(yaml_meta.get("steps"))
    if declared_type and declared_type != "preset" and not has_steps:
        sys.stderr.write(
            f"'{args.name}' n'est pas un preset (type={declared_type!r}, sans steps). "
            "Le dry-run est réservé aux presets.\n"
        )
        return 2

    print_dry_run(args.name, preset_dir, yaml_meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
