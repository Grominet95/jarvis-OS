"""Mission réelle PHASE 4 — Skill Lab sur vrai LLM (CDC §7 DoD).

But (cf. feedback_real_run_dod en mémoire) : les 27 tests skill_lab/lifecycle
mockent le LLM. Cette mission vérifie sur 2 cas réels :

1. CAS NOMINAL — un signal skill_candidate_proposal Kernel (équivalent de ce
   que PHASE 2 produit pour un pattern récurrent comme "génération de N
   articles markdown") déclenche la pipeline complète : génération via
   SkillSynthesizer (vrai LLM Haiku), test sandbox, lifecycle SANDBOXED_PASS,
   skill prête pour validation humaine.

2. CAS REJET — on crée une candidate volontairement cassée (skill.py qui
   lève RuntimeError à l'import) et on lance test_in_sandbox. Le gate DOIT
   marquer SANDBOXED_FAIL. Sans ce cas négatif, on ne peut PAS affirmer que
   le gate marche : seul l'échec du faux test prouve la robustesse.

Lancer : uv run python scripts/phase4_real_skill_lab.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.capabilities.skills.lab import SkillLab  # noqa: E402
from jarvis.capabilities.skills.lifecycle import (  # noqa: E402
    SkillLifecycle,
    SkillRecord,
    SkillStatus,
)
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer  # noqa: E402
from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402


def _emit_skill_candidate_event(kernel: MemoryKernel) -> str:
    """Simule un signal PHASE 2 — équivalent de ce qu'aurait émis Reflexion
    après une mission contenant le pattern 'génération de N articles markdown'."""
    evt = kernel.log_event(
        type="skill_candidate_proposal",
        source="reflexion:proj_pattern_articles",
        content=(
            "Générateur d'articles markdown structurés : automatiser la création "
            "de N fichiers article_{i}.md avec titre H1, paragraphe thématique "
            "N-phrases, et M bullet points selon un modèle reproductible."
        ),
        metadata={
            "project_id": "proj_pattern_articles",
            "from_lesson_evt": "evt_simulated_lesson",
        },
    )
    return evt.id


def _print_record(record: SkillRecord | None, label: str = "") -> None:
    """Affiche un SkillRecord lisiblement."""
    if record is None:
        print(f"  {label}: None")
        return
    print(f"  {label or record.name}:")
    print(f"    status         : {record.status.value}")
    print(f"    confidence     : {record.confidence:.2f}")
    print(f"    support_count  : {record.support_count}")
    print(f"    source_event   : {record.source_event_id}")
    if record.sandbox_notes:
        notes = record.sandbox_notes[:200]
        print(f"    sandbox_notes  : {notes}")


def _show_candidate_files(cand_dir: Path, name: str) -> None:
    """Liste les fichiers générés pour la candidate."""
    target = cand_dir / name
    if not target.exists():
        print(f"  ❌ pas de dossier {target}")
        return
    print(f"  ✅ candidate écrite dans {target}")
    for f in sorted(target.iterdir()):
        if f.is_file():
            size = f.stat().st_size
            print(f"     - {f.name} ({size} B)")
    # Aperçu de SKILL.md
    skill_md = target / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        print("\n     SKILL.md (premières 600 chars) :")
        print("     " + content[:600].replace("\n", "\n     "))


async def cas_nominal(workspace: Path) -> bool:
    """CAS NOMINAL — pipeline complète sur vrai LLM."""
    print("\n" + "=" * 70)
    print("  CAS NOMINAL — pattern 'génération d'articles markdown'")
    print("=" * 70)

    db_path = workspace / "memory.db"
    if db_path.exists():
        db_path.unlink()
    cand_dir = workspace / "candidates"
    inst_dir = workspace / "installed"
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    if inst_dir.exists():
        shutil.rmtree(inst_dir)

    llm = AnthropicProvider(max_tokens=2048, model=settings.voice_anthropic_model)
    synth = SkillSynthesizer(llm=llm)
    kernel = MemoryKernel(db_path)
    lifecycle = SkillLifecycle(db_path=db_path)
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=cand_dir,
        installed_dir=inst_dir,
    )

    # 1) Émet le signal skill_candidate_proposal (équivalent PHASE 2)
    event_id = _emit_skill_candidate_event(kernel)
    print(f"\n[setup] Event skill_candidate_proposal émis : {event_id}\n")

    # 2) Le Lab scan le Kernel → trouve l'event → déclenche la pipeline
    started = datetime.now()
    result = await lab.scan_kernel()
    elapsed = (datetime.now() - started).total_seconds()
    print(f"[scan terminé en {elapsed:.1f}s]")
    print(f"  events_examined       : {result.events_examined}")
    print(f"  candidates_generated  : {result.candidates_generated}")
    print(f"  sandbox_passed        : {result.sandbox_passed}")
    print(f"  sandbox_failed        : {result.sandbox_failed}")
    print(f"  errors                : {result.errors}")

    # 3) Dump les SkillRecord créés
    all_records = lifecycle.list_all()
    print(f"\n[Lifecycle — {len(all_records)} skill(s) trackées]")
    for rec in all_records:
        _print_record(rec)
        _show_candidate_files(cand_dir, rec.name)

    # 4) Évaluation
    print("\n[Évaluation CAS NOMINAL]")
    nominal_ok = (
        result.candidates_generated == 1
        and result.sandbox_passed == 1
        and result.sandbox_failed == 0
    )
    print(
        f"  {'✅' if nominal_ok else '❌'} 1 candidate générée + sandbox vert : "
        f"{'PASS' if nominal_ok else 'FAIL'}"
    )
    not_installed_ok = not inst_dir.exists() or not any(inst_dir.iterdir())
    print(
        f"  {'✅' if not_installed_ok else '❌'} candidate PAS auto-installée "
        f"(attend validation humaine) : {'PASS' if not_installed_ok else 'FAIL'}"
    )
    return nominal_ok and not_installed_ok


async def cas_rejet(workspace: Path) -> bool:
    """CAS REJET — skill volontairement cassée doit être rejetée."""
    print("\n" + "=" * 70)
    print("  CAS REJET — skill.py qui crash à l'import")
    print("=" * 70)

    db_path = workspace / "memory_rejet.db"
    if db_path.exists():
        db_path.unlink()
    cand_dir = workspace / "candidates_rejet"
    if cand_dir.exists():
        shutil.rmtree(cand_dir)

    llm = AnthropicProvider(max_tokens=512, model=settings.voice_anthropic_model)
    synth = SkillSynthesizer(llm=llm)
    kernel = MemoryKernel(db_path)
    lifecycle = SkillLifecycle(db_path=db_path)
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=cand_dir,
        installed_dir=workspace / "installed_rejet",
    )

    # On construit MANUELLEMENT une candidate cassée (sans passer par le synthesizer)
    bad_name = "broken-on-purpose"
    bad_dir = cand_dir / bad_name
    bad_dir.mkdir(parents=True)
    (bad_dir / "skill.py").write_text(
        "# Cette skill DOIT être rejetée par le gate sandbox.\n"
        "raise RuntimeError('skill volontairement cassée — test du gate')\n",
        encoding="utf-8",
    )
    (bad_dir / "skill.yaml").write_text(
        f"name: {bad_name}\nversion: 1.0.0\ndescription: skill cassée\n",
        encoding="utf-8",
    )
    lifecycle.create_candidate(name=bad_name, source_event_id="evt_synthetic")
    print(f"\n[setup] Candidate cassée écrite dans {bad_dir}")

    # On lance le test sandbox directement
    record = await lab.test_in_sandbox(bad_name)
    print("\n[Résultat sandbox]")
    _print_record(record)

    # Tentative de promotion — doit refuser
    promote_attempt = lab.promote(bad_name)
    print("\n[Tentative promotion]")
    print(f"  promote() renvoie : {promote_attempt}")

    print("\n[Évaluation CAS REJET]")
    rejected_ok = record is not None and record.status == SkillStatus.SANDBOXED_FAIL
    print(
        f"  {'✅' if rejected_ok else '❌'} sandbox a marqué SANDBOXED_FAIL : "
        f"{'PASS' if rejected_ok else 'FAIL'}"
    )
    promote_refused = promote_attempt is None
    print(
        f"  {'✅' if promote_refused else '❌'} promote() REFUSE la skill cassée : "
        f"{'PASS' if promote_refused else 'FAIL — GATE PERCÉ'}"
    )
    return rejected_ok and promote_refused


async def main() -> int:
    workspace = Path("memory_data/phase4_real_run")
    workspace.mkdir(parents=True, exist_ok=True)

    print("\n=== PHASE 4 SKILL LAB — MISSION RÉELLE ===")
    print(f"  workspace : {workspace}\n")

    nominal = await cas_nominal(workspace)
    rejet = await cas_rejet(workspace)

    print("\n" + "=" * 70)
    print("  BILAN GLOBAL")
    print("=" * 70)
    print(f"  CAS NOMINAL : {'✅ PASS' if nominal else '❌ FAIL'}")
    print(f"  CAS REJET   : {'✅ PASS' if rejet else '❌ FAIL'}")
    if nominal and rejet:
        print("\n  ✅ DoD §7 — gate test-vert-sinon-rejet validé sur vrai LLM.")
    else:
        print("\n  ❌ DoD §7 non satisfaite — investiguer.")
    return 0 if (nominal and rejet) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
