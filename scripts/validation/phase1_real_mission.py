"""Mission réelle PHASE 1 — test du verifier couche 3 (sémantique) sur un vrai LLM.

But : observer si le grader LLM attrape un step "plausible mais faux" sur un vrai
artefact, ou s'il valide trop facilement. C'est le seul vrai test de la PHASE 1
au-delà des 52 tests câblage.

Stratégie : on contourne la planification automatique pour fabriquer des steps
HAND-CRAFTED avec des critères de succès EXIGEANTS, sans verification_command
(couche 2 sautée → focus sémantique). On exécute, on dump la trace.

Lancer : uv run python scripts/phase1_real_mission.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Path bootstrap pour exécution directe.
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.engine.mission.project_store import ProjectStore  # noqa: E402
from jarvis.engine.mission.quality_checker import QualityChecker
from jarvis.engine.mission.schemas import Project, Step, validate_step  # noqa: E402
from jarvis.engine.mission.verifier import Verifier
from jarvis.engine.mission.worker_agent import WorkerAgent  # noqa: E402
from jarvis.engine.vocab import AccessLevel  # noqa: E402
from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import AnthropicProvider

# ── Mission ──────────────────────────────────────────────────────────────────

MISSION_TEXT = (
    "Crée un mini-site HTML statique qui présente 3 articles fictifs courts sur "
    "l'astronomie (un sur les exoplanètes, un sur les trous noirs, un sur les pulsars). "
    "Chaque article doit avoir un titre, un auteur fictif, une date, et un paragraphe "
    "de résumé de 3-5 phrases avec du contenu factuel réel sur le sujet."
)


def build_steps() -> list[Step]:
    """Plan hand-crafted, critères exigeants, sans verification_command."""
    return [
        Step(
            id="s1",
            title="Créer index.html",
            description=(
                "Crée index.html à la racine du workspace. Il doit contenir 3 sections "
                "d'article distinctes (balise <article> ou <section class='article'>) "
                "présentant : exoplanètes, trous noirs, pulsars. Chaque section doit "
                "porter un <h2> titre, des métadonnées (auteur fictif + date), et un "
                "<p> de résumé de 3-5 phrases avec du contenu factuel réel."
            ),
            success_criterion=(
                "Le fichier index.html existe à la racine. Il contient strictement 3 "
                "sections d'article distinctes (3 balises <article> OU 3 balises "
                "<section class='article'>). Chaque section a un <h2> avec un titre "
                "non vide, un sous-élément avec l'auteur et la date, et un <p> de 3-5 "
                "phrases qui présente des faits réels sur le sujet (pas du Lorem Ipsum, "
                "pas de placeholder vide, pas un seul mot, pas une phrase générique "
                "'ceci est un article')."
            ),
            access_level=AccessLevel.WRITE_LOCAL,
        ),
        Step(
            id="s2",
            title="Ajouter style.css avec mise en forme cohérente",
            description=(
                "Crée style.css à la racine avec une feuille de style cohérente : "
                "typographie lisible, espacement entre articles, distinction visuelle "
                "entre titre/métadonnées/contenu. Référence-la depuis index.html."
            ),
            success_criterion=(
                "Le fichier style.css existe, fait au moins 20 lignes de règles CSS "
                "effectives (pas que des commentaires/blancs), et style au moins : le "
                "<body>, les articles, et les <h2>. index.html doit avoir un "
                "<link rel='stylesheet' href='style.css'> qui pointe vers ce fichier."
            ),
            access_level=AccessLevel.WRITE_LOCAL,
        ),
    ]


# ── Boucle d'exécution ───────────────────────────────────────────────────────


async def main() -> int:
    # On laisse Docker tomber en fallback V1 (pas de docker daemon ici, file ops ok).
    store = ProjectStore()
    project = store.create_project(
        mission=MISSION_TEXT,
        title="Phase 1 — Mission astronomie",
        timeout_minutes=10,
    )
    project.steps = build_steps()

    # Validation du plan (PHASE 1 §4.2)
    for step in project.steps:
        validate_step(step)

    store.save_project(project)
    print(f"\n=== PROJECT {project.id} créé ===")
    print(f"  workspace : {project.workspace_path}")
    print(f"  audit log : {project.workspace_path}/.jarvis/audit.jsonl")
    print(f"  steps     : {len(project.steps)}\n")

    # Approval callback : refuse tout (pour rendre tout audit visible — mais
    # tous les steps sont WRITE_LOCAL/agent_mission/ALWAYS donc gate=auto, jamais demandé)
    async def _approval_cb(pid: str, sid: str, desc: str) -> bool:
        print(f"  [APPROVAL DEMANDÉE] {sid} : {desc[:80]}")
        return False

    # Broadcast = print pour observer
    def _broadcast(evt: dict) -> None:
        t = evt.get("type", "?")
        if t in ("project_done", "budget_hard_stop"):
            print(f"  [broadcast] {t}")

    worker = WorkerAgent(
        project=project,
        store=store,
        broadcast_event=_broadcast,
        approval_callback=_approval_cb,
    )

    print("=== EXÉCUTION ===\n")
    started = datetime.now()
    await worker.run()
    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n=== TERMINÉ en {elapsed:.1f}s ===\n")

    # ── Dump trace ─────────────────────────────────────────────────────────
    reloaded = store.load_project(project.id)
    assert reloaded is not None

    print(f"## État final : {reloaded.status.value}")
    for s in reloaded.steps:
        print(f"\n### Step {s.id} — {s.title}")
        print(f"  status            : {s.status.value}")
        print(f"  access_level      : {s.access_level.name} ({int(s.access_level)})")
        print(f"  verified          : {s.verified}")
        print(f"  success_criterion : {s.success_criterion[:200]}...")
        print(f"  verification_notes: {(s.verification_notes or '(none)')[:300]}")
        if s.error:
            print(f"  error             : {s.error[:200]}")
        if s.output:
            print(f"  output            : {s.output[:200]}")

    # Workspace files
    print("\n## Fichiers produits dans le workspace :")
    ws = Path(reloaded.workspace_path)
    for f in sorted(ws.rglob("*")):
        if f.is_file() and ".jarvis" not in str(f):
            print(f"  {f.relative_to(ws)} ({f.stat().st_size} B)")

    # Audit log
    audit_path = ws / ".jarvis" / "audit.jsonl"
    if audit_path.exists():
        print(f"\n## Audit log ({audit_path.name}) :")
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            print(
                f"  [{d['decision']:<8}] {d['context_id']:<60} "
                f"risk={d['risk_decision']:<8} cat={d['category_decision']:<8} "
                f"budget={d['budget_decision']}"
            )

    # Worker logs (dernières lignes pertinentes)
    log_path = ws / ".jarvis" / "logs.jsonl"
    if log_path.exists():
        print("\n## Worker logs (filtrés sur 'vérif' et 'gate') :")
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("msg", "")
            lv = d.get("level", "")
            if "Vérif" in msg or "vérif" in msg or "Gate" in msg or "gate" in msg or "✓" in msg:
                print(f"  [{lv:<8}] {msg[:140]}")

    # ── PIÈGE : artefact plausible-mais-faux, le verifier doit le rejeter ────
    await _trap_test(reloaded)

    return 0


async def _trap_test(project: Project) -> None:
    """Test délibéré : on remplace index.html par un stub plausible-mais-faux
    et on rappelle directement le verifier. Le grader DOIT rejeter."""

    print("\n=== TRAP TEST — artefact plausible mais faux ===")
    ws = Path(project.workspace_path)
    # On écrase index.html avec un stub : structure HTML valide mais critère NON atteint
    # (juste 1 article au lieu de 3, contenu vide, Lorem Ipsum)
    stub = (
        "<!DOCTYPE html>\n<html><head><title>Astronomie</title></head>\n"
        "<body>\n"
        "<article><h2>Article 1</h2><p>Lorem ipsum dolor sit amet.</p></article>\n"
        "</body></html>\n"
    )
    (ws / "index.html").write_text(stub)

    fake_step = Step(
        id="trap",
        title="Étape piégée",
        description="(trap)",
        success_criterion=project.steps[0].success_criterion,  # même critère que s1
        output="J'ai créé un site avec 3 articles complets sur l'astronomie.",
        # ↑ auto-rapport mensonger pour tester si le grader se fait avoir
    )

    llm = AnthropicProvider(max_tokens=1024, model=settings.voice_anthropic_model)
    quality = QualityChecker(str(ws))
    verifier = Verifier(quality_checker=quality, llm=llm, cli_executor=None)

    result = await verifier.verify(project, fake_step, files_before=[])
    print(f"  verified : {result.verified}")
    print(f"  layer    : {result.layer}")
    print(f"  issues   : {result.issues[:3]}")
    print(f"  notes    : {result.notes[:300]}")
    if not result.verified:
        print("\n  ✅ Le grader sémantique a CORRECTEMENT rejeté l'artefact stub.")
    else:
        print("\n  ❌ ÉCHEC : le grader a validé un artefact plausible-mais-faux.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
