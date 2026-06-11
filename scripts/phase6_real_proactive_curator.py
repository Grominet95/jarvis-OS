"""Mission réelle PHASE 6 — Proactive Engine & Curator (CDC §10).

But (cf. feedback_real_run_dod en mémoire) : les 19 tests PHASE 6 mockent une
partie de l'écosystème. Cette mission vérifie sur 3 cas RÉELS bout-en-bout :

1. CAS NOMINAL (initiative niveau 5) — une initiative EXTERNAL_ACTION avec
   budget/permission/risk/deadline/next_action est créée via InitiativeStore,
   le CommandCenter l'agrège dans son snapshot avec tous les champs §10.1,
   et needs_human_validation() retourne True PAR PRINCIPE (CDC §10).

2. CAS CURATOR RÉEL — un MemoryKernel réel est seedé avec :
     - 1 fact ACTIVE FAST decay très âgé → propose ARCHIVE_FACT
     - 1 skill ACTIVE non utilisée depuis 35j → propose MARK_SKILL_STALE
     - 1 skill STALE depuis 100j → propose ARCHIVE_SKILL
     - 1 candidate SANDBOXED_PASS depuis 20j → propose REJECT_STALE_CANDIDATE
     - 1 initiative PENDING depuis 5j → propose REVIEW_INITIATIVE
   On lance curator.scan() et on vérifie que le rapport contient bien les
   patches attendus, persisté sur disque, lisible via latest_report().

3. CAS NÉGATIF (refus auto-apply) — le cœur de la DoD §10. Pour CHAQUE patch
   du rapport, curator.apply_patch(idx, report) DOIT renvoyer (False, ...).
   On forge en plus un patch ciblant le noyau §11 (config/settings.py) et on
   vérifie que apply_patch refuse aussi explicitement "noyau protégé §11".
   ET on vérifie qu'une initiative niveau 5 avec requires_validation=False
   exige TOUJOURS validation humaine (override par AutonomyLevel).

Le succès, c'est que le Curator propose. La VALEUR, c'est qu'il refuse de
s'auto-appliquer — y compris sur du decay "réversible et confiné".

Lancer : uv run python scripts/phase6_real_proactive_curator.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillStatus  # noqa: E402
from jarvis.engine.mission.project_store import ProjectStore  # noqa: E402
from jarvis.engine.proactive.command_center import CommandCenter  # noqa: E402
from jarvis.engine.proactive.curator import (  # noqa: E402
    Curator,
    CuratorPatch,
    PatchKind,
    is_protected_path,
)
from jarvis.engine.proactive.schemas import (  # noqa: E402
    ExecutionMode,
    Initiative,
    InitiativeType,
    Priority,
    needs_human_validation,
)
from jarvis.engine.proactive.store import InitiativeStore  # noqa: E402
from jarvis.engine.vocab import AutonomyLevel  # noqa: E402
from jarvis.providers.memory.kernel import MemoryKernel  # noqa: E402
from jarvis.providers.memory.schemas import DecayPolicy, Fact, FactStatus  # noqa: E402


def _separator(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ── CAS A : initiative niveau 5 réelle gérée via Command Center ─────────────


def cas_a_initiative_niveau_5(workspace: Path) -> bool:
    _separator("CAS A — Initiative niveau 5 (EXTERNAL_ACTION) gérée Command Center")

    # Workspace dédié — on isole INITIATIVES_DIR pour ne pas polluer
    initiatives_dir = workspace / "initiatives_a"
    if initiatives_dir.exists():
        shutil.rmtree(initiatives_dir)
    initiatives_dir.mkdir(parents=True, exist_ok=True)

    # Patche le dossier global du store pour ce run
    import jarvis.engine.proactive.store as proactive_store

    proactive_store.INITIATIVES_DIR = initiatives_dir
    store = InitiativeStore()

    # Initiative EXTERNAL_ACTION réaliste : envoyer un mail au client
    initiative = Initiative(
        id=f"ini_{uuid.uuid4().hex[:8]}",
        type=InitiativeType.DRAFT_RESPONSE,
        title="Envoyer le récap hebdo au client Acme",
        context="Mail prévu vendredi 18h, draft prêt en pending",
        reasoning="Récap requis par le contrat, client attend une trace écrite",
        action="Envoyer mail récap",
        priority=Priority.HIGH,
        execution_mode=ExecutionMode.VALIDATE,
        autonomy_level=AutonomyLevel.EXTERNAL_ACTION,  # niveau 5
        permission_required="email_send",
        cost_max_usd=0.20,
        risk="medium",
        deadline=datetime.now() + timedelta(days=2),
        next_action="Relire le draft puis cliquer 'Envoyer'",
        requires_validation=False,  # même False, niveau 5 force la validation
    )
    print(f"\n[setup] initiative créée : {initiative.id}")
    print(f"  autonomy_level    : {int(initiative.autonomy_level)} (EXTERNAL_ACTION)")
    print(f"  permission        : {initiative.permission_required}")
    print(f"  cost_max_usd      : ${initiative.cost_max_usd}")
    print(f"  risk              : {initiative.risk}")
    print(f"  deadline          : {initiative.deadline.isoformat()}")
    print(f"  next_action       : {initiative.next_action}")
    print(f"  requires_validation (champ brut) : {initiative.requires_validation}")

    store.save(initiative)

    # Vérifie roundtrip JSONL
    reloaded = store.get_by_id(initiative.id)
    assert reloaded is not None, "initiative non rechargée"
    roundtrip_ok = (
        reloaded.autonomy_level == AutonomyLevel.EXTERNAL_ACTION
        and reloaded.permission_required == "email_send"
        and reloaded.cost_max_usd == 0.20
        and reloaded.risk == "medium"
        and reloaded.next_action == initiative.next_action
    )
    print(
        f"\n  {'✅' if roundtrip_ok else '❌'} JSONL roundtrip §10.1 : "
        f"{'PASS' if roundtrip_ok else 'FAIL'}"
    )

    # CommandCenter — agrège l'initiative
    cc = CommandCenter(
        initiative_store=store,
        project_store=ProjectStore(),
        budget_guard=None,
        skill_lifecycle=None,
    )
    snap = cc.snapshot(days=7)
    print(f"\n[snapshot] {len(snap.initiatives)} initiative(s) agrégée(s)")
    if snap.initiatives:
        s = snap.initiatives[0]
        print(f"  title             : {s.title}")
        print(f"  autonomy_level    : {s.autonomy_level}")
        print(f"  permission        : {s.permission_required}")
        print(f"  cost_max_usd      : ${s.cost_max_usd}")
        print(f"  risk              : {s.risk}")
        print(f"  deadline          : {s.deadline}")
        print(f"  next_action       : {s.next_action}")

    snapshot_ok = (
        len(snap.initiatives) == 1
        and snap.initiatives[0].autonomy_level == 5
        and snap.initiatives[0].permission_required == "email_send"
    )
    print(
        f"\n  {'✅' if snapshot_ok else '❌'} CommandCenter expose les champs §10.1 : "
        f"{'PASS' if snapshot_ok else 'FAIL'}"
    )

    # Règle CDC §10 : niveau 5 exige TOUJOURS validation
    needs_validation = needs_human_validation(reloaded)
    print(
        f"\n  {'✅' if needs_validation else '❌'} needs_human_validation(niveau 5) "
        f"= True PAR PRINCIPE (même avec requires_validation=False) : "
        f"{'PASS' if needs_validation else 'FAIL — auto-modification déguisée'}"
    )

    return roundtrip_ok and snapshot_ok and needs_validation


# ── CAS B : Curator nocturne réel produit un rapport ─────────────────────────


def _seed_aged_fact(kernel: MemoryKernel, age_days: float) -> Fact:
    """Insère un fact ACTIVE FAST decay très âgé pour déclencher ARCHIVE_FACT."""
    now = datetime.now()
    last_seen = now - timedelta(days=age_days)
    fact = Fact(
        id=f"fact_{uuid.uuid4().hex[:8]}",
        subject="user",
        predicate="prefers_tool",
        object="emacs avec config legacy abandonnée 2022",
        category="preference",
        status=FactStatus.ACTIVE,
        confidence=0.6,
        support_count=1,
        decay_policy=DecayPolicy.FAST,  # halflife 14j → 3×14j = 42j seuil
        importance=0.3,
        created_at=now - timedelta(days=age_days + 5),
        last_seen_at=last_seen,
        updated_at=last_seen,
    )
    kernel.insert_fact(fact)
    return fact


def _seed_skill(
    lifecycle: SkillLifecycle,
    name: str,
    target_status: SkillStatus,
    age_days: float,
) -> None:
    """Crée une skill avec un last_used_at / created_at âgé. On hack en SQL
    pour pouvoir antédater (l'API ne le permet pas naturellement)."""
    import sqlite3

    lifecycle.create_candidate(name=name)
    aged = (datetime.now() - timedelta(days=age_days)).isoformat()
    with sqlite3.connect(lifecycle.db_path) as conn:
        conn.execute(
            "UPDATE skills SET status = ?, last_used_at = ?, "
            "promoted_at = ?, created_at = ?, updated_at = ? WHERE name = ?",
            (target_status.value, aged, aged, aged, aged, name),
        )
        conn.commit()


async def cas_b_curator_real_scan(workspace: Path) -> bool:
    _separator("CAS B — Curator scan nocturne réel (facts + skills + initiatives)")

    db_path = workspace / "memory_b.db"
    if db_path.exists():
        db_path.unlink()
    initiatives_dir = workspace / "initiatives_b"
    if initiatives_dir.exists():
        shutil.rmtree(initiatives_dir)
    initiatives_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "curator_reports_b"
    if reports_dir.exists():
        shutil.rmtree(reports_dir)

    import jarvis.engine.proactive.store as proactive_store

    proactive_store.INITIATIVES_DIR = initiatives_dir
    store = InitiativeStore()

    kernel = MemoryKernel(db_path=db_path)
    lifecycle = SkillLifecycle(db_path=db_path)

    # Seed : 1 fact FAST decay vieux de 60j → archive proposé (seuil 42j)
    aged_fact = _seed_aged_fact(kernel, age_days=60.0)
    print(f"\n[seed] fact {aged_fact.id} : FAST decay, last_seen il y a 60j")

    # Seed : 1 fact ACTIVE jeune → pas de patch
    young_fact = Fact(
        id=f"fact_{uuid.uuid4().hex[:8]}",
        subject="user",
        predicate="works_with",
        object="laptop M1 max 64gb",
        category="identity",
        status=FactStatus.ACTIVE,
        decay_policy=DecayPolicy.NONE,
    )
    kernel.insert_fact(young_fact)
    print(f"[seed] fact {young_fact.id} : NONE decay (identité) — pas de patch")

    # Seed : 1 skill ACTIVE inutilisée depuis 35j → MARK_STALE
    _seed_skill(lifecycle, "ancien_summarizer", SkillStatus.ACTIVE, age_days=35)
    print("[seed] skill 'ancien_summarizer' : ACTIVE inutilisée depuis 35j")

    # Seed : 1 skill STALE depuis 100j → ARCHIVE
    _seed_skill(lifecycle, "vieux_csv_parser", SkillStatus.STALE, age_days=100)
    print("[seed] skill 'vieux_csv_parser' : STALE depuis 100j")

    # Seed : 1 candidate SANDBOXED_PASS depuis 20j → REJECT_STALE_CANDIDATE
    _seed_skill(lifecycle, "candidate_oubliee", SkillStatus.SANDBOXED_PASS, age_days=20)
    print("[seed] skill 'candidate_oubliee' : SANDBOXED_PASS en attente depuis 20j")

    # Seed : 1 initiative pending depuis 5j → REVIEW_INITIATIVE
    old_ini = Initiative(
        id=f"ini_{uuid.uuid4().hex[:8]}",
        type=InitiativeType.SUGGESTION,
        title="Vieille suggestion oubliée",
        context="ctx",
        reasoning="r",
        action="action",
        priority=Priority.LOW,
        execution_mode=ExecutionMode.NOTIFY,
        created_at=datetime.now() - timedelta(days=5),
        autonomy_level=AutonomyLevel.SUGGEST,
    )
    # On écrit en bypass save() pour antédater le fichier
    legacy_file = initiatives_dir / (
        (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d") + ".jsonl"
    )
    with legacy_file.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "id": old_ini.id,
                    "type": old_ini.type,
                    "title": old_ini.title,
                    "context": old_ini.context,
                    "reasoning": old_ini.reasoning,
                    "action": old_ini.action,
                    "priority": old_ini.priority,
                    "execution_mode": old_ini.execution_mode,
                    "draft_content": None,
                    "mission_description": None,
                    "status": "pending",
                    "created_at": old_ini.created_at.isoformat(),
                    "autonomy_level": int(old_ini.autonomy_level),
                    "permission_required": old_ini.permission_required,
                    "cost_max_usd": None,
                    "risk": "low",
                    "deadline": None,
                    "next_action": "",
                    "requires_validation": False,
                }
            )
            + "\n"
        )
    print(f"[seed] initiative {old_ini.id} : pending depuis 5j (legacy_file)")

    # Curator scan
    curator = Curator(
        kernel=kernel,
        skill_lifecycle=lifecycle,
        initiative_store=store,
        budget_guard=None,
        reports_dir=reports_dir,
    )
    print("\n[appel] curator.scan()")
    report = await curator.scan()

    print("\n[rapport]")
    print(f"  generated_at        : {report.generated_at}")
    print(f"  duration_s          : {report.duration_seconds:.3f}")
    print(f"  facts_active        : {report.facts_active}")
    print(f"  facts_archive_proposed : {report.facts_archive_proposed}")
    print(f"  skills_active       : {report.skills_active}")
    print(f"  skills_stale_proposed   : {report.skills_stale_proposed}")
    print(f"  skills_archive_proposed : {report.skills_archive_proposed}")
    print(f"  candidates_pending  : {report.candidates_pending}")
    print(f"  candidates_to_reject: {report.candidates_to_reject}")
    print(f"  initiatives_pending : {report.initiatives_pending}")
    print(f"  patches             : {len(report.patches)}")
    print(f"  refused_protected   : {len(report.refused_protected_patches)}")
    for i, p in enumerate(report.patches):
        print(f"  [#{i}] {p.kind.value:<25} target={p.target} (auto={p.auto_appliable})")
        print(f"       {p.description[:120]}")

    # Vérifications
    has_archive_fact = any(p.kind == PatchKind.ARCHIVE_FACT for p in report.patches)
    has_skill_stale = any(p.kind == PatchKind.MARK_SKILL_STALE for p in report.patches)
    has_skill_archive = any(p.kind == PatchKind.ARCHIVE_SKILL for p in report.patches)
    has_reject_cand = any(p.kind == PatchKind.REJECT_STALE_CANDIDATE for p in report.patches)
    has_review_ini = any(p.kind == PatchKind.REVIEW_INITIATIVE for p in report.patches)

    print("\n[Évaluation CAS B]")
    print(f"  {'✅' if has_archive_fact else '❌'} ARCHIVE_FACT proposé (decay FAST 60j)")
    print(f"  {'✅' if has_skill_stale else '❌'} MARK_SKILL_STALE proposé")
    print(f"  {'✅' if has_skill_archive else '❌'} ARCHIVE_SKILL proposé")
    print(f"  {'✅' if has_reject_cand else '❌'} REJECT_STALE_CANDIDATE proposé")
    print(f"  {'✅' if has_review_ini else '❌'} REVIEW_INITIATIVE proposé")

    # Persistance
    persisted = curator.latest_report()
    persisted_ok = persisted is not None and len(persisted.patches) == len(report.patches)
    print(
        f"  {'✅' if persisted_ok else '❌'} rapport persisté + relisible via "
        f"latest_report() : {'PASS' if persisted_ok else 'FAIL'}"
    )

    return all(
        [
            has_archive_fact,
            has_skill_stale,
            has_skill_archive,
            has_reject_cand,
            has_review_ini,
            persisted_ok,
        ]
    )


# ── CAS C (CŒUR DoD §10) : refus auto-apply ─────────────────────────────────


async def cas_c_refus_auto_apply(workspace: Path) -> bool:
    _separator("CAS C — CŒUR DoD §10 : refus systématique d'auto-apply")

    db_path = workspace / "memory_c.db"
    if db_path.exists():
        db_path.unlink()
    initiatives_dir = workspace / "initiatives_c"
    if initiatives_dir.exists():
        shutil.rmtree(initiatives_dir)
    initiatives_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "curator_reports_c"
    if reports_dir.exists():
        shutil.rmtree(reports_dir)

    import jarvis.engine.proactive.store as proactive_store

    proactive_store.INITIATIVES_DIR = initiatives_dir
    store = InitiativeStore()

    kernel = MemoryKernel(db_path=db_path)
    lifecycle = SkillLifecycle(db_path=db_path)

    # Reproduit un patch propre type ARCHIVE_FACT (auto_appliable=True dans le code)
    _seed_aged_fact(kernel, age_days=80.0)

    curator = Curator(
        kernel=kernel,
        skill_lifecycle=lifecycle,
        initiative_store=store,
        budget_guard=None,
        reports_dir=reports_dir,
    )
    report = await curator.scan()
    print(f"\n[scan] {len(report.patches)} patch(es) proposés")
    assert report.patches, "le seed devait produire au moins un patch — sinon test dégénéré"

    # 1) Refus auto-apply sur CHAQUE patch (même ceux marqués auto_appliable=True)
    print("\n[Refus auto-apply patch par patch]")
    all_refused = True
    for i, patch in enumerate(report.patches):
        applied, reason = curator.apply_patch(i, report)
        print(
            f"  patch #{i} {patch.kind.value:<25} auto_appliable={patch.auto_appliable} → "
            f"applied={applied} reason={reason[:80]!r}"
        )
        if applied:
            print(f"     ❌ FAIL — patch {i} ({patch.kind.value}) a été auto-appliqué")
            all_refused = False

    print(
        f"\n  {'✅' if all_refused else '❌'} TOUS les patches refusés en MVP "
        f"(y compris auto_appliable=True) : {'PASS' if all_refused else 'FAIL — DoD §10 percée'}"
    )

    # 2) Refus apply sur patch ciblant le noyau §11
    print("\n[Refus sur cible noyau §11]")
    protected_target = "config/settings.py"
    assert is_protected_path(protected_target), (
        "is_protected_path() doit reconnaître config/settings.py"
    )

    # Forge un patch qui touche un chemin protégé et l'injecte dans le rapport
    forged = CuratorPatch(
        kind=PatchKind.REVIEW_CONTRADICTION,
        target=protected_target,
        description="Patch forgé pour test : touche le noyau (devrait être refusé)",
        auto_appliable=True,  # même marqué True, doit être refusé §11
        reason="forged",
    )
    report.patches.append(forged)
    forged_index = len(report.patches) - 1
    applied, reason = curator.apply_patch(forged_index, report)
    print(f"  forged patch target='{protected_target}' → applied={applied} reason={reason!r}")
    protected_refused = (not applied) and "noyau" in reason.lower()
    print(
        f"\n  {'✅' if protected_refused else '❌'} patch noyau §11 refusé "
        f"explicitement : {'PASS' if protected_refused else 'FAIL'}"
    )

    # 3) Initiative niveau 5 — needs_human_validation True même si requires_validation=False
    print("\n[Initiative niveau 5 exige validation par principe]")
    niv5 = Initiative(
        id="ini_lvl5_test",
        type=InitiativeType.ALERT,
        title="Publier sur LinkedIn (test)",
        context="x",
        reasoning="r",
        action="post",
        priority=Priority.MEDIUM,
        execution_mode=ExecutionMode.VALIDATE,
        autonomy_level=AutonomyLevel.EXTERNAL_ACTION,
        requires_validation=False,  # MÊME en False, niveau 5 doit forcer validation
    )
    forced = needs_human_validation(niv5)
    print(f"  niveau=5 requires_validation=False → needs_human_validation={forced}")
    forced_ok = forced is True
    print(
        f"\n  {'✅' if forced_ok else '❌'} niveau 5 force validation par principe : "
        f"{'PASS' if forced_ok else 'FAIL — auto-modification déguisée'}"
    )

    # 4) Bonus : index hors borne → False propre, pas d'exception
    print("\n[Index patch hors borne]")
    applied_oob, reason_oob = curator.apply_patch(9999, report)
    oob_ok = (not applied_oob) and "hors borne" in reason_oob.lower()
    print(f"  apply_patch(9999) → applied={applied_oob} reason={reason_oob!r}")
    print(
        f"\n  {'✅' if oob_ok else '❌'} index hors borne renvoie False propre : "
        f"{'PASS' if oob_ok else 'FAIL'}"
    )

    return all_refused and protected_refused and forced_ok and oob_ok


# ── Main ─────────────────────────────────────────────────────────────────────


async def main() -> int:
    workspace = Path("memory_data/phase6_real_run")
    workspace.mkdir(parents=True, exist_ok=True)

    print("\n=== PHASE 6 PROACTIVE ENGINE & CURATOR — MISSION RÉELLE ===")
    print(f"  workspace : {workspace}\n")

    a = cas_a_initiative_niveau_5(workspace)
    b = await cas_b_curator_real_scan(workspace)
    c = await cas_c_refus_auto_apply(workspace)

    _separator("BILAN GLOBAL")
    print(f"  CAS A — initiative niveau 5 gouvernée : {'✅ PASS' if a else '❌ FAIL'}")
    print(f"  CAS B — Curator scan réel + rapport   : {'✅ PASS' if b else '❌ FAIL'}")
    print(f"  CAS C — refus auto-apply (DoD §10)    : {'✅ PASS' if c else '❌ FAIL'}")

    all_ok = a and b and c
    if all_ok:
        print(
            "\n  ✅ DoD §10 — le Curator propose, refuse l'auto-application, "
            "le noyau §11 reste intouchable, niveau 5 force validation. "
            "C'est la valeur."
        )
    else:
        print("\n  ❌ DoD §10 non satisfaite — investiguer.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
