#!/usr/bin/env python3
# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Baseline de l'état runtime sur disque — CDC §A.1.4.

L'état runtime (memory_data/, config/*.json, skills/installed/, vision_data/faces/)
est gitignoré : invisible à git, aux tests automatiques et à tous les gates
de pré-commit. Seule une comparaison explicite contre une baseline capturée
en début de migration peut prouver qu'aucune donnée utilisateur ne s'est
silencieusement perdue.

Sortie : `scripts/migration/data_state.baseline.txt` (comptes uniquement →
committable, le contenu réel reste local).

ATTENTION (CDC §0.5) : ce script produit une baseline [LOCAL] — elle dépend
de l'état runtime de la machine, n'est PAS reproductible en CI. La GATE A8
capture la baseline, la GATE B8 (libellé à proposer en fin de Phase A)
compare contre elle, en exerçant réellement les artefacts (charger les 8
skills, relire un fait, résoudre un token) — pas juste en comparant des
comptes (cf. feedback de Barth § "attraper, pas passer").
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "scripts" / "migration" / "data_state.baseline.txt"


def count_facts() -> tuple[int, dict[str, int]]:
    """Compte les facts du Memory Kernel, total + ventilation par statut."""
    db = ROOT / "memory_data" / "jarvis_memory.db"
    if not db.exists():
        return 0, {}
    conn = sqlite3.connect(str(db))
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
        rows = conn.execute("SELECT status, COUNT(*) FROM facts GROUP BY status").fetchall()
        by_status = {str(s): int(c) for s, c in rows}
        return total, by_status
    finally:
        conn.close()


def count_events() -> int:
    db = ROOT / "memory_data" / "jarvis_memory.db"
    if not db.exists():
        return 0
    conn = sqlite3.connect(str(db))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    finally:
        conn.close()


def list_tokens() -> list[tuple[str, int]]:
    """Présence + taille des fichiers tokens OAuth dans config/. Jamais le contenu."""
    candidates = [
        "google_credentials.json",
        "google_token.json",
        "google_gmail_token.json",
        "spotify_token.json",
        "deezer_token.json",
    ]
    out: list[tuple[str, int]] = []
    for name in candidates:
        path = ROOT / "config" / name
        out.append((name, path.stat().st_size if path.exists() else -1))
    return out


def list_installed_skills() -> tuple[int, list[str]]:
    """Sous-dossiers de skills_data/installed/ + chargement via le loader réel."""
    sk_dir = ROOT / "skills_data" / "installed"
    if not sk_dir.exists():
        return 0, []
    subs = sorted(d.name for d in sk_dir.iterdir() if d.is_dir())

    # On veut PROUVER que les skills se chargent — pas juste qu'ils existent.
    sys.path.insert(0, str(ROOT))
    try:
        from jarvis.capabilities.skills.registry import SkillRegistry  # lazy: diagnostic

        reg = SkillRegistry()
        reg.load_all()
        loaded = sorted(reg.get_all().keys())
    except Exception as e:  # noqa: BLE001 — on capture pour signaler la régression
        loaded = [f"ERREUR: {type(e).__name__}: {e}"]
    return len(subs), loaded


def count_faces() -> int:
    d = ROOT / "vision_data" / "faces"
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and not p.name.startswith("."))


def main() -> None:
    fact_total, fact_by_status = count_facts()
    event_total = count_events()
    tokens = list_tokens()
    sk_count, sk_loaded = list_installed_skills()
    faces = count_faces()

    lines = [
        "# Baseline runtime — capturée en Phase A pour la GATE B8 (continuité des données).",
        "# Ce fichier est committable (comptes uniquement). Le contenu réel reste local.",
        "",
        f"facts.total = {fact_total}",
        f"facts.by_status = {sorted(fact_by_status.items())}",
        f"events.total = {event_total}",
        "",
        "tokens (-1 = absent) :",
    ]
    for name, size in tokens:
        lines.append(f"  {name} = {size}")

    lines += [
        "",
        f"skills.installed.dirs = {sk_count}",
        f"skills.installed.loaded_by_registry = {sk_loaded}",
        "",
        f"vision_data.faces.files = {faces}",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
