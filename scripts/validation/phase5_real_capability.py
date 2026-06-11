"""Mission réelle PHASE 5 — Capability Engine sur vrai LLM (CDC §8 DoD).

But (cf. feedback_real_run_dod en mémoire) : les 22 tests engine mockent le
LLM. Cette mission vérifie sur 3 cas réels :

1. CAS NOMINAL — un gap verbalisé déclenche bien la détection, génère une
   candidate via le Lab (vrai LLM Haiku), passe le sandbox, et ATTEND la
   validation humaine. Aucune auto-installation.

2. CAS REFUS AUTO-INSTALL — même cas nominal mais on simule le flag
   auto_install_whitelisted_enabled=True ET une whitelist qui matche. CDC §8
   MVP : ZÉRO auto-install même quand tout devrait passer. On prouve que le
   flag est INERTE.

3. CAS DANGEROUS — une demande qui évoque INSTALL_PACKAGE est REFUSÉE avant
   même d'appeler le LLM (cap dur coût + sécurité). Aucune candidate générée,
   aucun fichier touché.

Le succès, c'est que la boucle propose. La VALEUR (et la vraie DoD §8), c'est
qu'elle refuse de s'auto-installer.

Lancer : uv run python scripts/phase5_real_capability.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.capabilities.skills.lab import SkillLab  # noqa: E402
from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillStatus  # noqa: E402
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer  # noqa: E402
from jarvis.engine.mission.capability_engine import (  # noqa: E402
    CapabilityEngine,
    ResolutionKind,
    Whitelist,
    WhitelistDomain,
)
from jarvis.kernel.settings import settings
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402


class _FakeSkillRegistry:
    def list_installed(self) -> list[dict]:
        return []  # cas test : aucune skill existante


class _FakeToolRegistry:
    def schemas(self) -> list[dict]:
        return []  # cas test : aucun tool natif


def _print_resolution(resolution, prefix: str = "  ") -> None:  # noqa: ANN001
    print(f"{prefix}kind          : {resolution.kind.value}")
    print(f"{prefix}target_name   : {resolution.target_name}")
    print(f"{prefix}event_id      : {resolution.event_id}")
    if resolution.candidate_record is not None:
        rec = resolution.candidate_record
        print(f"{prefix}record.status : {rec.status.value}")
        print(f"{prefix}record.notes  : {(rec.sandbox_notes or '')[:120]}")
    print(f"{prefix}notes         : {resolution.notes[:200]}")


def _check_installed_empty(installed_dir: Path) -> bool:
    return not installed_dir.exists() or not any(installed_dir.iterdir())


async def cas_nominal(workspace: Path) -> bool:
    """CAS NOMINAL — gap réel, candidate générée, ATTENTE humaine."""
    print("\n" + "=" * 70)
    print("  CAS NOMINAL — gap 'parser un format CSV custom'")
    print("=" * 70)

    db_path = workspace / "memory_nominal.db"
    if db_path.exists():
        db_path.unlink()
    cand_dir = workspace / "candidates_nominal"
    inst_dir = workspace / "installed_nominal"
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
    engine = CapabilityEngine(
        kernel=kernel,
        lab=lab,
        skill_registry=_FakeSkillRegistry(),
        tool_registry=_FakeToolRegistry(),
        whitelist=Whitelist(domains=[]),
        auto_install_enabled=False,
    )

    print("\n[appel] engine.detect_and_propose(...)")
    resolution = await engine.detect_and_propose(
        description=(
            "Parser un fichier CSV custom où les lignes sont séparées par ';;' "
            "et chaque cellule peut contenir du JSON imbriqué entre {} pour "
            "encoder des structures."
        ),
        example_input='id;;data;;tags\n42;;{"name":"foo"};;["a","b"]\n',
    )
    print("\n[résolution]")
    _print_resolution(resolution)

    print("\n[Évaluation CAS NOMINAL]")
    nominal_ok = resolution.kind == ResolutionKind.NEW_CANDIDATE
    print(
        f"  {'✅' if nominal_ok else '❌'} kind = NEW_CANDIDATE : "
        f"{'PASS' if nominal_ok else 'FAIL'}"
    )
    sandbox_ok = (
        resolution.candidate_record is not None
        and resolution.candidate_record.status == SkillStatus.SANDBOXED_PASS
    )
    print(
        f"  {'✅' if sandbox_ok else '❌'} candidate sandbox vert : "
        f"{'PASS' if sandbox_ok else 'FAIL'}"
    )
    not_installed = _check_installed_empty(inst_dir)
    print(
        f"  {'✅' if not_installed else '❌'} ZÉRO installation auto "
        f"(attend promote() humain) : {'PASS' if not_installed else 'FAIL — DoD §8 percée'}"
    )
    not_promoted = (
        resolution.candidate_record is None or resolution.candidate_record.promoted_at is None
    )
    print(
        f"  {'✅' if not_promoted else '❌'} lifecycle.promoted_at est None : "
        f"{'PASS' if not_promoted else 'FAIL — auto-promotion détectée'}"
    )
    return nominal_ok and sandbox_ok and not_installed and not_promoted


async def cas_refus_auto_install(workspace: Path) -> bool:
    """CAS REFUS AUTO-INSTALL — flag ON + whitelist match → encore zéro install."""
    print("\n" + "=" * 70)
    print("  CAS REFUS AUTO-INSTALL — flag ON + whitelist match")
    print("=" * 70)

    db_path = workspace / "memory_refus.db"
    if db_path.exists():
        db_path.unlink()
    cand_dir = workspace / "candidates_refus"
    inst_dir = workspace / "installed_refus"
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
    # Whitelist qui matche explicitement notre demande
    whitelist = Whitelist(
        domains=[
            WhitelistDomain(
                name="format_parser",
                max_access_level="WRITE_LOCAL",
                allowed_categories=["agent_mission"],
                description_must_contain=["parser", "format", "convertir"],
            )
        ]
    )
    # Flag ON — sensé être inerte en MVP
    engine = CapabilityEngine(
        kernel=kernel,
        lab=lab,
        skill_registry=_FakeSkillRegistry(),
        tool_registry=_FakeToolRegistry(),
        whitelist=whitelist,
        auto_install_enabled=True,  # ← FLAG ON
    )

    print("\n[setup] flag auto_install_whitelisted_enabled = True")
    print("[setup] whitelist matche 'parser' / 'format' / 'convertir'")
    print("\n[appel] engine.detect_and_propose(...)")
    resolution = await engine.detect_and_propose(
        description=(
            "Convertir un format de log Apache en JSON structuré "
            "pour permettre des requêtes faciles."
        )
    )
    print("\n[résolution]")
    _print_resolution(resolution)

    print("\n[Évaluation CAS REFUS AUTO-INSTALL]")
    # Vrai test : MÊME avec flag ON + whitelist match + sandbox vert,
    # AUCUNE installation auto en MVP
    sandbox_ok = (
        resolution.candidate_record is not None
        and resolution.candidate_record.status == SkillStatus.SANDBOXED_PASS
    )
    print(
        f"  {'✅' if sandbox_ok else '❌'} sandbox vert (donc le test n'est "
        f"pas dégénéré) : {'PASS' if sandbox_ok else 'FAIL'}"
    )
    not_installed = _check_installed_empty(inst_dir)
    print(
        f"  {'✅' if not_installed else '❌'} ZÉRO installation MÊME avec flag ON : "
        f"{'PASS' if not_installed else 'FAIL — flag inerte percé'}"
    )
    not_promoted = (
        resolution.candidate_record is None or resolution.candidate_record.promoted_at is None
    )
    print(
        f"  {'✅' if not_promoted else '❌'} pas de promotion auto MÊME avec "
        f"whitelist match : {'PASS' if not_promoted else 'FAIL'}"
    )
    return sandbox_ok and not_installed and not_promoted


async def cas_dangerous(workspace: Path) -> bool:
    """CAS DANGEROUS — INSTALL_PACKAGE refusé AVANT appel LLM."""
    print("\n" + "=" * 70)
    print("  CAS DANGEROUS — 'pip install requests'")
    print("=" * 70)

    db_path = workspace / "memory_danger.db"
    if db_path.exists():
        db_path.unlink()
    cand_dir = workspace / "candidates_danger"
    inst_dir = workspace / "installed_danger"
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    if inst_dir.exists():
        shutil.rmtree(inst_dir)

    # On COMPTE les appels LLM pour prouver qu'aucun n'est fait
    llm = AnthropicProvider(max_tokens=512, model=settings.voice_anthropic_model)
    llm_call_count = [0]
    original_complete = llm.complete

    async def counting_complete(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        llm_call_count[0] += 1
        return await original_complete(*args, **kwargs)

    llm.complete = counting_complete  # type: ignore[assignment]

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
    engine = CapabilityEngine(
        kernel=kernel,
        lab=lab,
        skill_registry=_FakeSkillRegistry(),
        tool_registry=_FakeToolRegistry(),
    )

    print("\n[appel] engine.detect_and_propose('installer un nouveau paquet pip ...')")
    resolution = await engine.detect_and_propose(
        description="Installer un nouveau paquet Python pour faire des requêtes HTTP"
    )
    print("\n[résolution]")
    _print_resolution(resolution)

    print("\n[diagnostic LLM]")
    print(f"  appels LLM faits : {llm_call_count[0]}")

    print("\n[Évaluation CAS DANGEROUS]")
    blocked_ok = resolution.kind == ResolutionKind.BLOCKED_DANGEROUS
    print(
        f"  {'✅' if blocked_ok else '❌'} kind = BLOCKED_DANGEROUS : "
        f"{'PASS' if blocked_ok else 'FAIL — gate dangerous percé'}"
    )
    no_llm = llm_call_count[0] == 0
    print(
        f"  {'✅' if no_llm else '❌'} ZÉRO appel LLM (cap dur coût + sécurité) : "
        f"{'PASS' if no_llm else 'FAIL'}"
    )
    no_candidate = len(lifecycle.list_all()) == 0
    print(
        f"  {'✅' if no_candidate else '❌'} ZÉRO candidate dans le lifecycle : "
        f"{'PASS' if no_candidate else 'FAIL'}"
    )
    no_files = not cand_dir.exists() or not any(cand_dir.iterdir())
    print(
        f"  {'✅' if no_files else '❌'} ZÉRO fichier candidate écrit sur disque : "
        f"{'PASS' if no_files else 'FAIL'}"
    )
    not_installed = _check_installed_empty(inst_dir)
    print(
        f"  {'✅' if not_installed else '❌'} ZÉRO installation : "
        f"{'PASS' if not_installed else 'FAIL'}"
    )
    return blocked_ok and no_llm and no_candidate and no_files and not_installed


async def main() -> int:
    workspace = Path("memory_data/phase5_real_run")
    workspace.mkdir(parents=True, exist_ok=True)

    print("\n=== PHASE 5 CAPABILITY ENGINE — MISSION RÉELLE ===")
    print(f"  workspace : {workspace}\n")

    nominal = await cas_nominal(workspace)
    refus = await cas_refus_auto_install(workspace)
    danger = await cas_dangerous(workspace)

    # ── Trace globale : events tracés ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  EVENTS capability_gap_recorded TRACÉS (audit Kernel)")
    print("=" * 70)
    for label, dbname in [
        ("nominal", "memory_nominal.db"),
        ("refus", "memory_refus.db"),
        ("danger", "memory_danger.db"),
    ]:
        db = workspace / dbname
        if not db.exists():
            continue
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT metadata_json FROM events WHERE type='capability_gap_recorded'"
            ).fetchall()
        for r in rows:
            meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
            print(
                f"  [{label}] resolution={meta.get('resolution_kind'):<22} "
                f"target={meta.get('target_name')}"
            )

    print("\n" + "=" * 70)
    print("  BILAN GLOBAL")
    print("=" * 70)
    print(f"  CAS NOMINAL          : {'✅ PASS' if nominal else '❌ FAIL'}")
    print(f"  CAS REFUS AUTO-INSTALL: {'✅ PASS' if refus else '❌ FAIL'}")
    print(f"  CAS DANGEROUS        : {'✅ PASS' if danger else '❌ FAIL'}")
    all_ok = nominal and refus and danger
    if all_ok:
        print(
            "\n  ✅ DoD §8 — la boucle propose, mais refuse de s'auto-installer. C'est la valeur."
        )
    else:
        print("\n  ❌ DoD §8 non satisfaite — investiguer.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
