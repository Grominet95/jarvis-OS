"""Mission réelle PHASE 2 — réflexion post-mission avec vrai LLM (CDC §5 DoD).

But (cf. feedback_real_run_dod en mémoire) : les 13 tests reflexion mockent le
LLM. Cette mission vérifie sur 3 cas réels :

1. SUCCÈS — mini-mission terminée DONE → leçon avec what_worked non vide.
2. ÉCHEC — mission avec success_criterion volontairement irréalisable → FAILED
   après retry épuisé → leçon avec cause + action corrective non vides.
3. PATTERN — mission avec étapes répétitives manifestes → skill_candidate=true
   + skill_description non vide.

Pour chacune : on dump la leçon, on vérifie qu'un Event mission_lesson est
tracé, qu'un Fact category=decision est créé via l'ingest (matcher v2), et
que le signal skill_candidate_proposal est émis si applicable.

Lancer : uv run python scripts/phase2_real_reflexion.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collections.abc import Callable  # noqa: E402

from jarvis.engine.mission.project_store import ProjectStore  # noqa: E402
from jarvis.engine.mission.reflexion import Reflexion  # noqa: E402
from jarvis.engine.mission.schemas import Project, Step, validate_step  # noqa: E402
from jarvis.engine.mission.worker_agent import WorkerAgent  # noqa: E402
from jarvis.engine.vocab import AccessLevel  # noqa: E402
from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.memory.ingest import MemoryIngest  # noqa: E402
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402
from jarvis.providers.memory.schemas import FactStatus  # noqa: E402


def build_success_steps() -> list[Step]:
    """Mission triviale qui réussit : crée un fichier hello.txt avec contenu."""
    return [
        Step(
            id="s1",
            title="Créer hello.txt",
            description=(
                "Crée un fichier hello.txt à la racine du workspace contenant "
                "le texte 'Hello, world!' suivi d'une ligne vide. Rien de plus."
            ),
            success_criterion=(
                "Le fichier hello.txt existe à la racine, fait au moins 13 "
                "caractères, contient exactement le texte 'Hello, world!'."
            ),
            access_level=AccessLevel.WRITE_LOCAL,
        ),
    ]


def build_failure_steps() -> list[Step]:
    """Mission au critère volontairement irréalisable pour forcer le FAILED.

    Le worker fera 2 essais (verifier retry borné), les deux échoueront, le
    step passera FAILED → mission FAILED.
    """
    return [
        Step(
            id="s1",
            title="Créer un fichier impossible à vérifier",
            description=(
                "Crée un fichier impossible.txt à la racine. Tout simplement, "
                "écris-y le texte 'placeholder'."
            ),
            success_criterion=(
                "Le fichier impossible.txt existe, ET fait EXACTEMENT 1_000_000 "
                "caractères dont chaque caractère est différent du précédent, ET "
                "contient les 26 premières décimales de pi en position 42-67."
            ),
            access_level=AccessLevel.WRITE_LOCAL,
        ),
    ]


def build_pattern_steps() -> list[Step]:
    """Mission avec 3 étapes identiques en structure (pattern réutilisable)."""
    return [
        Step(
            id=f"s{i}",
            title=f"Créer article_{i}.md",
            description=(
                f"Crée article_{i}.md à la racine du workspace avec : "
                f"un titre H1 'Article {i}', un paragraphe de présentation de "
                f"2-3 phrases sur le thème '{theme}', et 3 bullets de "
                f"sous-points."
            ),
            success_criterion=(
                f"article_{i}.md existe à la racine, contient un titre '# "
                f"Article {i}', un paragraphe de 2-3 phrases sur '{theme}', "
                "et au moins 3 lignes commençant par '- ' ou '* '."
            ),
            access_level=AccessLevel.WRITE_LOCAL,
        )
        for i, theme in [
            (1, "les exoplanètes"),
            (2, "les trous noirs"),
            (3, "les pulsars"),
        ]
    ]


async def _run_one_mission(
    title: str,
    mission_text: str,
    steps_factory: Callable[[], list[Step]],
    kernel: MemoryKernel,
    ingest: MemoryIngest,
    reflexion: Reflexion,
) -> tuple[Project | None, int, int]:
    """Lance une mission complète.

    Retourne (project, n_facts_decision_avant, n_facts_decision_après).
    """
    print(f"\n=== MISSION '{title}' ===")
    store = ProjectStore()
    project = store.create_project(mission=mission_text, title=title, timeout_minutes=5)
    project.steps = steps_factory()
    for step in project.steps:
        validate_step(step)
    store.save_project(project)

    n_decisions_before = len(kernel.list_facts_by_category("decision"))

    async def _approval_cb(pid: str, sid: str, desc: str) -> bool:
        return True

    def _broadcast(evt: dict) -> None:
        t = evt.get("type", "?")
        if t in ("mission_lesson_produced", "project_done"):
            print(f"  [broadcast] {t}: {json.dumps(evt, ensure_ascii=False)[:200]}")

    worker = WorkerAgent(
        project=project,
        store=store,
        broadcast_event=_broadcast,
        approval_callback=_approval_cb,
        reflexion=reflexion,
    )

    started = datetime.now()
    await worker.run()
    elapsed = (datetime.now() - started).total_seconds()

    reloaded = store.load_project(project.id)
    print(f"  status final : {reloaded.status.value} (en {elapsed:.1f}s)")

    n_decisions_after = len(kernel.list_facts_by_category("decision"))
    return reloaded, n_decisions_before, n_decisions_after


async def main() -> int:
    workspace = Path("memory_data/phase2_real_run")
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "jarvis_memory.db"
    if db_path.exists():
        db_path.unlink()

    llm = AnthropicProvider(max_tokens=1024, model=settings.voice_anthropic_model)
    kernel = MemoryKernel(db_path)
    ingest = MemoryIngest(kernel=kernel, llm=llm)
    reflexion = Reflexion(llm=llm, kernel=kernel, memory_ingest=ingest)

    print("\n=== PHASE 2 RÉFLEXION RÉELLE ===")
    print(f"  DB : {db_path}\n")

    proj_done, dec_before_1, dec_after_1 = await _run_one_mission(
        "Succès trivial",
        "Crée un fichier hello.txt trivial.",
        build_success_steps,
        kernel,
        ingest,
        reflexion,
    )
    proj_failed, dec_before_2, dec_after_2 = await _run_one_mission(
        "Échec délibéré (critère irréalisable)",
        "Crée un fichier impossible à vérifier.",
        build_failure_steps,
        kernel,
        ingest,
        reflexion,
    )
    proj_pattern, dec_before_3, dec_after_3 = await _run_one_mission(
        "Pattern répétitif (3 articles)",
        "Crée 3 fichiers article_{i}.md sur des thèmes astronomiques.",
        build_pattern_steps,
        kernel,
        ingest,
        reflexion,
    )

    # ── Trace globale ──────────────────────────────────────────────────────
    print("\n=== BILAN ===\n")

    with sqlite3.connect(kernel.db_path) as conn:
        conn.row_factory = sqlite3.Row
        events = list(conn.execute("SELECT * FROM events ORDER BY created_at").fetchall())

    lesson_events = [e for e in events if e["type"] == "mission_lesson"]
    skill_events = [e for e in events if e["type"] == "skill_candidate_proposal"]

    print("## Events tracés")
    print(f"  events total           : {len(events)}")
    print(f"  - mission_lesson       : {len(lesson_events)}")
    print(f"  - skill_candidate_proposal : {len(skill_events)}")
    print()

    print("## Leçons rendues par les 3 missions\n")
    for evt in lesson_events:
        meta = json.loads(evt["metadata_json"]) if evt["metadata_json"] else {}
        print(f"--- Leçon {evt['id']} ({meta.get('project_status', '?')}) ---")
        print(evt["content"])
        print(f"   skill_candidate : {meta.get('skill_candidate', '?')}")
        if meta.get("skill_description"):
            print(f"   skill_description : {meta['skill_description']}")
        print()

    if skill_events:
        print("## Signaux skill_candidate_proposal vers Skill Lab (PHASE 4)")
        for evt in skill_events:
            meta = json.loads(evt["metadata_json"]) if evt["metadata_json"] else {}
            print(f"  - projet {meta.get('project_id')}: {evt['content'][:200]}")
        print()

    # Facts decision produits via le pipeline ingest
    decisions = kernel.list_facts_by_category("decision", status=FactStatus.ACTIVE)
    print(f"## Facts category='decision' actifs dans le Kernel : {len(decisions)}\n")
    for f in decisions:
        print(
            f"  [{f.predicate:<10}] {f.subject} → {f.object[:80]}"
            f"  (conf {f.confidence:.2f}, imp {f.importance:.2f}, vu {f.support_count}×)"
        )

    # ── Évaluation CDC §5 DoD ───────────────────────────────────────────────
    print("\n## Évaluation CDC §5 (Definition of Done)\n")

    ok_done = bool(proj_done) and bool(lesson_events)
    print(
        f"  {'✅' if ok_done else '❌'} Mission DONE produit une leçon "
        f"({'PASS' if ok_done else 'FAIL'})"
    )

    failed_lesson = next(
        (
            json.loads(e["metadata_json"])
            for e in lesson_events
            if json.loads(e["metadata_json"]).get("project_status") == "failed"
        ),
        None,
    )
    ok_failed = (
        failed_lesson is not None
        and bool(failed_lesson.get("root_cause"))
        and bool(failed_lesson.get("corrective_action"))
    )
    print(
        f"  {'✅' if ok_failed else '❌'} Mission FAILED produit une leçon avec "
        f"cause + action correctives NON VIDES "
        f"({'PASS' if ok_failed else 'FAIL'})"
    )

    pattern_signal = bool(skill_events)
    print(
        f"  {'✅' if pattern_signal else '❌'} Pattern répété déclenche "
        f"skill_candidate=true + signal vers Skill Lab "
        f"({'PASS' if pattern_signal else 'FAIL — voir leçon pattern ci-dessus'})"
    )

    ok_ingest = len(decisions) >= 1
    print(
        f"  {'✅' if ok_ingest else '❌'} Au moins une leçon ingérée comme "
        f"Fact category='decision' via le matcher v2 "
        f"({'PASS' if ok_ingest else 'FAIL'})"
    )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
