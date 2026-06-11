"""Mission réelle d'ingestion PHASE 3 — test du Kernel + réconciliation sur vrai LLM.

But (cf. feedback_real_run_dod en mémoire) : les tests unitaires prouvent le câblage
mais pas le jugement réel. Cette mission ingère une vraie série d'échanges sur
plusieurs jours simulés et vérifie :

- Les doublons s'accumulent-ils sur des répétitions ? (NON attendu — confirmation)
- La supersession se déclenche-t-elle au bon moment ? (sur catégorie stable)
- Un fait répété monte-t-il en confidence ? (OUI attendu)
- "Barth court" + "Barth fait du vélo" coexistent-ils ? (OUI attendu, non stable)
- Un terme hors vocabulaire → needs_review ? (OUI attendu)

Lancer : uv run python scripts/phase3_real_ingestion.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.memory.ingest import MemoryIngest  # noqa: E402
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402
from jarvis.providers.memory.mirror import MemoryMirror  # noqa: E402
from jarvis.providers.memory.retrieval import MemoryRetrieval  # noqa: E402
from jarvis.providers.memory.schemas import FactStatus  # noqa: E402

# ── Scénario simulé : 12 échanges sur ~2 semaines ────────────────────────────

# Chaque échange = (jour_relatif, texte). Les répétitions, contradictions et
# coexistences sont DÉLIBÉRÉMENT placées pour tester la réconciliation.
SCENARIO: list[tuple[int, str]] = [
    # Jour 1 — Premiers faits explicites
    (
        1,
        "Barth : Je suis développeur, et je préfère travailler en Python. "
        "Mon style de vie inclut beaucoup de course à pied — je vise sub-3h au marathon.",
    ),
    # Jour 2 — Nouveau fait compatible (vélo en plus de la course)
    (
        2,
        "Barth : Cette semaine j'ai aussi commencé le vélo le dimanche, "
        "en complément de mes sorties running. C'est une nouvelle habitude.",
    ),
    # Jour 3 — Répétition (même préférence Python) → doit confirmer pas dupliquer
    (3, "Barth : Encore Python aujourd'hui, je trouve ça vraiment efficace."),
    # Jour 5 — Préférence d'outil différente mais coexistante (sur tool, non stable)
    (5, "Barth : J'ai testé Go cette semaine, je l'utilise sur un side project."),
    # Jour 7 — Inférence faible (préférence implicite)
    (7, "Barth : Tu peux me résumer en quelques bullets ? Je préfère la concision."),
    # Jour 8 — Confirmation explicite de l'objectif marathon
    (8, "Barth : Pour info mon objectif marathon reste sub-3h pour cette année."),
    # Jour 10 — CONTRADICTION sur catégorie stable (goal) → supersession attendue
    (
        10,
        "Barth : Je révise mon objectif marathon. Je vise maintenant 3h10, "
        "sub-3h c'était trop ambitieux.",
    ),
    # Jour 11 — Identity stable (devrait créer fact identity persistant)
    (11, "Barth : Je suis aussi entrepreneur, je monte une boîte de hardware."),
    # Jour 12 — Répétition du nouveau goal → confirmation
    (12, "Barth : Mon objectif 3h10 au marathon tient toujours."),
    # Jour 13 — Hors périmètre (météo, éphémère) → l'ingest doit IGNORER
    (13, "Barth : Il pleut aujourd'hui, c'est moche."),
    # Jour 14 — Constraint (catégorie stable) — première occurrence
    (14, "Barth : Je ne peux pas courir le lundi à cause de mes entraînements en salle."),
]


async def main() -> int:
    # Workspace isolé pour cette mission
    workspace = Path("memory_data/phase3_real_run")
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "jarvis_memory.db"
    mirror_dir = workspace / "mirror"

    # Nettoyage si run précédent (sinon les répétitions s'accumulent en confirmations
    # à travers les runs et c'est ce qu'on veut tester proprement)
    if db_path.exists():
        db_path.unlink()

    print("\n=== INGESTION RÉELLE PHASE 3 ===")
    print(f"  DB     : {db_path}")
    print(f"  Mirror : {mirror_dir}")
    print(f"  Échanges à ingérer : {len(SCENARIO)}\n")

    # Vrai LLM (Anthropic Haiku par défaut)

    llm = AnthropicProvider(max_tokens=1024, model=settings.voice_anthropic_model)

    kernel = MemoryKernel(db_path)
    ingest = MemoryIngest(kernel, llm)

    # ── Boucle d'ingestion ──────────────────────────────────────────────────
    started = datetime.now()
    for day, text in SCENARIO:
        result = await ingest.ingest(content=text, source=f"day_{day}")
        print(
            f"  jour {day:>2}  | extraits={result.raw_extracted_count:>2}  "
            f"new={len(result.new_facts):>2}  confirmed={len(result.confirmed):>2}  "
            f"superseded={len(result.superseded_pairs):>2}  "
            f"needs_review={len(result.needs_review):>2}"
        )
    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n=== INGESTION TERMINÉE en {elapsed:.1f}s ===\n")
    print(f"## Appels LLM arbitre v2 (matcher étage 2) : {ingest.arbiter_calls}")

    # ── Export miroir MD ────────────────────────────────────────────────────
    mirror = MemoryMirror(kernel, mirror_dir)
    report = mirror.export()
    print(
        f"## Miroir MD exporté : {report.facts_exported} facts dans "
        f"{len(report.files_written)} fichiers\n"
    )
    for f in report.files_written:
        print(f"  - {f}")

    # ── Bilan global ────────────────────────────────────────────────────────
    print("\n## Bilan SQLite")
    print(f"  events     : {kernel.count_events()}")
    print(f"  facts total: {kernel.count_facts()}")
    print(f"  - active   : {kernel.count_facts(FactStatus.ACTIVE)}")
    print(f"  - superseded : {kernel.count_facts(FactStatus.SUPERSEDED)}")
    print(f"  - needs_review : {kernel.count_facts(FactStatus.NEEDS_REVIEW)}")

    # ── Détail facts actifs ─────────────────────────────────────────────────
    print("\n## Facts actifs (triés par importance × confidence)")
    actives = kernel.list_facts_by_status(FactStatus.ACTIVE)
    actives.sort(key=lambda f: -(f.importance * f.confidence))
    for f in actives:
        print(
            f"  [{f.category:<12}] {f.subject} {f.predicate} {f.object[:50]:<50}"
            f"  (conf {f.confidence:.2f}, imp {f.importance:.2f}, "
            f"vu {f.support_count}×, decay {f.decay_policy.value})"
        )

    # ── Détail facts superseded (la supersession a-t-elle marché ?) ────────
    superseded = kernel.list_facts_by_status(FactStatus.SUPERSEDED)
    if superseded:
        print("\n## Facts superseded (preuve d'archivage non destructif)")
        for f in superseded:
            print(
                f"  [{f.category}] {f.subject} {f.predicate} {f.object}  "
                f"(était à conf {f.confidence:.2f})"
            )
            for rel in kernel.list_relations(f.id):
                if rel.to_fact_id == f.id:
                    succ = kernel.get_fact(rel.from_fact_id)
                    if succ:
                        print(
                            f"     → remplacé par : {succ.subject} {succ.predicate} {succ.object}"
                        )

    if kernel.count_facts(FactStatus.NEEDS_REVIEW):
        print("\n## Facts en needs_review (hors vocabulaire fermé)")
        for f in kernel.list_facts_by_status(FactStatus.NEEDS_REVIEW):
            print(f"  {f.subject} {f.predicate} {f.object} ({f.category})")

    # ── Test retrieval sur quelques queries ────────────────────────────────
    retrieval = MemoryRetrieval(kernel)
    print("\n## Retrieval — test de saillance")
    for query in ["marathon", "python", "entrepreneur", "vélo"]:
        results = retrieval.retrieve(query, k=3)
        print(f"\n  query : '{query}'")
        for r in results:
            print(
                f"    score={r.score:.3f}  rel={r.relevance:.2f}  "
                f"rec={r.recency:.2f}  : {r.fact.subject} {r.fact.predicate} {r.fact.object}"
            )
            for c in r.contradictions:
                print(f"      ⚠ contradiction connue : {c.subject} {c.predicate} {c.object}")

    # ── Critères d'évaluation (CDC §6 DoD) ─────────────────────────────────
    print("\n## Évaluation CDC §6 (critères de réconciliation)")
    n_active = kernel.count_facts(FactStatus.ACTIVE)
    n_super = kernel.count_facts(FactStatus.SUPERSEDED)
    # Critère 1 : pas d'explosion de doublons (12 échanges → < 12 facts actifs attendus
    # grâce aux confirmations + supersessions)
    print(
        f"  ✓ Pas d'explosion de doublons : {n_active} facts actifs pour "
        f"{len(SCENARIO)} échanges {'PASS' if n_active <= len(SCENARIO) else 'FAIL'}"
    )
    # Critère 2 : supersession s'est produite au moins une fois
    print(
        f"  {'✅' if n_super > 0 else '❌'} Supersession déclenchée : "
        f"{n_super} fact(s) superseded "
        f"{'PASS' if n_super > 0 else 'FAIL — pas de supersession détectée'}"
    )
    # Critère 3 : coexistence (course + vélo, OU python + go) — au moins 2 facts
    # même subject+predicate avec objects différents
    coexist = sum(
        1
        for f in actives
        if any(
            g.id != f.id
            and g.subject == f.subject
            and g.predicate == f.predicate
            and g.category == f.category
            for g in actives
        )
    )
    print(
        f"  {'✅' if coexist >= 2 else '❌'} Coexistence préservée : "
        f"{coexist // 2} paire(s) coexistante(s) "
        f"{'PASS' if coexist >= 2 else 'FAIL'}"
    )
    # Critère 4 : au moins un fact a support_count > 1 (confirmation effective)
    confirmed_facts = [f for f in actives if f.support_count > 1]
    print(
        f"  {'✅' if confirmed_facts else '❌'} Confirmation effective : "
        f"{len(confirmed_facts)} fact(s) ré-observé(s) "
        f"{'PASS' if confirmed_facts else 'FAIL'}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
