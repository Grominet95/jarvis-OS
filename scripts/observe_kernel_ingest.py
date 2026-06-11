"""Trace d'observation de l'ingestion Kernel (MOUVEMENT 2 option D).

À lancer APRÈS 3-5 jours d'usage réel avec settings.ingest_deep_enabled=true.
Dump une trace lisible pour jugement signal/bruit, comme demandé par
[[feedback_real_run_dod]] — un mouvement de mise en prod n'est "fait" que
quand on a regardé une trace réelle.

Affiche :
- Volume : nb facts extraits, par catégorie, par jour.
- Fréquence : nb d'appels arbitre LLM totaux + ratio par batch deep.
- Doublons : nb facts confirmés (support_count > 1) — signal que le matcher
  v2 fait son travail sur du vrai langage.
- Supersessions : combien d'anciens facts archivés par de nouveaux.
- ÉCHANTILLON aléatoire de facts récents pour jugement humain du signal/bruit.

Lancer : uv run python scripts/observe_kernel_ingest.py
"""

from __future__ import annotations

import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.kernel.settings import settings  # noqa: E402
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402
from jarvis.providers.memory.schemas import FactStatus  # noqa: E402


def _fmt_date(iso: str) -> str:
    return iso[:10] if iso else "?"


def main() -> int:
    db_path = Path(settings.memory_dir) / "jarvis_memory.db"
    if not db_path.exists():
        print(f"❌ Kernel DB inexistant : {db_path}")
        print("   Vérifie que main.py a tourné au moins une fois.")
        return 1

    kernel = MemoryKernel(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    print(f"\n=== OBSERVATION INGESTION KERNEL — {now} ===")
    print(f"  DB : {db_path}")
    print(f"  flag ingest_deep_enabled = {settings.ingest_deep_enabled}")
    print()

    # ── Volume global ─────────────────────────────────────────────────────
    n_events_total = kernel.count_events()
    n_facts_total = kernel.count_facts()
    n_active = kernel.count_facts(FactStatus.ACTIVE)
    n_super = kernel.count_facts(FactStatus.SUPERSEDED)
    n_review = kernel.count_facts(FactStatus.NEEDS_REVIEW)

    print("## Volume global")
    print(f"  events tracés       : {n_events_total}")
    print(f"  facts total         : {n_facts_total}")
    print(f"    - active          : {n_active}")
    print(f"    - superseded      : {n_super}")
    print(f"    - needs_review    : {n_review}")

    # ── Events par type + source ──────────────────────────────────────────
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        types = list(
            conn.execute(
                "SELECT type, COUNT(*) AS n FROM events GROUP BY type ORDER BY n DESC"
            ).fetchall()
        )
        sources = list(
            conn.execute(
                "SELECT source, COUNT(*) AS n FROM events GROUP BY source ORDER BY n DESC LIMIT 10"
            ).fetchall()
        )
    print("\n## Events par type")
    for row in types:
        print(f"  {row['type']:<30} : {row['n']}")
    print("\n## Top 10 sources d'events")
    for row in sources:
        print(f"  {row['source']:<40} : {row['n']}")

    # ── Sessions ingérées (event_type = session_summary) ──────────────────
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        n_session_events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type=?", ("session_summary",)
        ).fetchone()[0]
        # Premier / dernier event session_summary
        first_session = conn.execute(
            "SELECT created_at FROM events WHERE type=? ORDER BY created_at ASC LIMIT 1",
            ("session_summary",),
        ).fetchone()
        last_session = conn.execute(
            "SELECT created_at FROM events WHERE type=? ORDER BY created_at DESC LIMIT 1",
            ("session_summary",),
        ).fetchone()
    print("\n## Ingestion BATCH DEEP")
    print(f"  events 'session_summary' : {n_session_events}")
    if first_session and last_session:
        first = first_session[0]
        last = last_session[0]
        try:
            span = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).days
            print(
                f"  période couverte    : {_fmt_date(first)} → {_fmt_date(last)} ({span} jour(s))"
            )
        except ValueError:
            print(f"  période             : {_fmt_date(first)} → {_fmt_date(last)}")

    # ── Doublons (support_count > 1) ──────────────────────────────────────
    confirmed = [f for f in kernel.list_facts_by_status(FactStatus.ACTIVE) if f.support_count > 1]
    print("\n## Confirmations (signal que le matcher v2 fait son travail)")
    print(f"  facts ré-observés (support_count > 1) : {len(confirmed)}")
    if confirmed:
        max_support = max(f.support_count for f in confirmed)
        print(f"  support_count max  : {max_support}")
        top = sorted(confirmed, key=lambda f: -f.support_count)[:5]
        for f in top:
            print(f"    {f.subject} {f.predicate} {f.object[:60]:<60}  vu {f.support_count}×")

    # ── Supersessions ─────────────────────────────────────────────────────
    superseded = kernel.list_facts_by_status(FactStatus.SUPERSEDED)
    print("\n## Supersessions (corrections de la mémoire)")
    print(f"  facts archivés : {len(superseded)}")
    if superseded:
        # Échantillon
        for f in superseded[:5]:
            relations = kernel.list_relations(f.id)
            successor = None
            for rel in relations:
                if rel.to_fact_id == f.id:
                    successor = kernel.get_fact(rel.from_fact_id)
                    break
            line = f"    {f.subject} {f.predicate} {f.object[:50]}"
            if successor:
                line += f"  →  {successor.object[:50]}"
            print(line)

    # ── Distribution par catégorie ────────────────────────────────────────
    actives = kernel.list_facts_by_status(FactStatus.ACTIVE)
    cats = Counter(f.category for f in actives)
    print("\n## Facts actifs par catégorie")
    for cat, n in cats.most_common():
        print(f"  {cat:<20} : {n}")

    # ── Échantillon aléatoire pour jugement signal/bruit ─────────────────
    print("\n## ÉCHANTILLON aléatoire — 15 facts actifs (jugement signal/bruit)")
    print("   (Lis-les : sont-ils pertinents ou bruités ?)\n")
    sample_size = min(15, len(actives))
    sample = random.sample(actives, sample_size) if actives else []
    for f in sample:
        meta = (
            f"conf {f.confidence:.2f} · imp {f.importance:.2f} · "
            f"vu {f.support_count}× · cat {f.category}"
        )
        print(f"  • {f.subject} {f.predicate} {f.object}")
        print(f"      ({meta})")

    # ── Needs review (vocab hors liste) ───────────────────────────────────
    if n_review:
        print("\n## ⚠️ facts en NEEDS_REVIEW (vocabulaire hors liste, à curer)")
        for f in kernel.list_facts_by_status(FactStatus.NEEDS_REVIEW)[:10]:
            print(f"  {f.subject} {f.predicate} {f.object} (cat={f.category})")

    # ── Récents (24 dernières heures) ─────────────────────────────────────
    recent_cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    with sqlite3.connect(db_path) as conn:
        n_recent_facts = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE created_at > ?", (recent_cutoff,)
        ).fetchone()[0]
        n_recent_events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE created_at > ?", (recent_cutoff,)
        ).fetchone()[0]
    print("\n## Dernières 24h")
    print(f"  events tracés    : {n_recent_events}")
    print(f"  facts créés      : {n_recent_facts}")

    print("\n=== FIN OBSERVATION ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
