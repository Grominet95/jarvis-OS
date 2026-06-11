"""Curator nocturne (CDC §10.3) — rapport + patches PROPOSÉS, jamais appliqués MVP.

Tourne dans la passe nocturne (scheduler à 3h10, après AutoDream deep 3h et
Skill Lab scan 3h05). Produit un rapport de maintenance sur :

- Facts à archiver par decay (interroge Kernel, lit la DecayPolicy par catégorie)
- Skills stale ou candidates à expirer (interroge SkillLifecycle)
- Contradictions actuelles (interroge fact_relations SUPERSEDES/CONTRADICTS)
- Coûts agrégés (interroge BudgetGuard.status())
- Initiatives proactives échouées ou ratées (interroge audit/store)
- Erreurs récurrentes (lit audit log Kernel + worker logs si dispo)

**RÈGLE NON NÉGOCIABLE CDC §10** : il PROPOSE, il n'APPLIQUE RIEN au-delà du
gate composite (§9). En PHASE 6 MVP : il n'applique RIEN du tout, point.

Garde-fou §11 PERSONNALITÉ : le Curator refuse explicitement tout patch qui
toucherait au noyau (`_PROTECTED_PATHS`) — même si un mode "auto-apply" était
activé un jour, le noyau resterait intouchable.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from loguru import logger

from jarvis.engine.budget import BudgetGuard
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.kernel.contracts import MemoryStore as MemoryKernel
from jarvis.kernel.contracts import SkillLifecycle
from jarvis.kernel.paths import MEMORY_DATA_DIR
from jarvis.kernel.schemas import DecayPolicy, Fact, FactStatus, SkillStatus

# ── Constantes ──────────────────────────────────────────────────────────────


# Seuil decay : un fact dont l'âge dépasse N demi-vies est "à archiver".
# 3 demi-vies → la saillance est descendue à 12.5% du nominal, peu utile.
_DECAY_HALFLIVES_THRESHOLD = 3

# Skills ACTIVE non utilisées depuis X jours → suggérées STALE.
_SKILL_STALE_DAYS = 30
# Skills STALE depuis Y jours supplémentaires → suggérées ARCHIVED.
_SKILL_ARCHIVE_DAYS = 60
# Candidates SANDBOXED_PASS en attente depuis Z jours → expirables (reject implicite).
_CANDIDATE_EXPIRY_DAYS = 14

# Mapping DecayPolicy → demi-vie en jours (synchro avec memory/retrieval.py)
_HALFLIFE_DAYS: dict[DecayPolicy, float] = {
    DecayPolicy.NONE: float("inf"),
    DecayPolicy.VERY_SLOW: 365.0 * 2,
    DecayPolicy.SLOW: 365.0,
    DecayPolicy.MEDIUM: 90.0,
    DecayPolicy.FAST: 14.0,
}

# §11 PERSONNALITÉ — fichiers/chemins JAMAIS modifiables par le Curator,
# même si un mode auto-apply était activé. Le noyau de valeurs ne s'écrit pas
# automatiquement (cf. CDC §11 "Garde-fou anti-complaisance").
_PROTECTED_PATHS: list[str] = [
    "prompts/system_static.md",  # noyau prompts système
    "prompts/consolidation.md",  # prompts background critiques
    "config/settings.py",  # règles de sécurité, plafonds, flags
    "config/approvals.py",
    "config/backends.py",
    "src/jarvis/engine/vocab.py",  # vocabulaires fermés PHASE 0
    "src/jarvis/engine/audit.py",  # audit log gate
    "src/jarvis/engine/mission/governance.py",  # gate composite
    "src/jarvis/engine/mission/schemas.py",  # contrat de données
    "src/jarvis/providers/memory/schemas.py",
    "src/jarvis/kernel/schemas.py",  # foyer canonique (Phase A)
    "src/jarvis/app.py",  # ex-main.py (Phase B)
    "main.py",  # shim racine encore protégé
    "CDC_jarvis_evolution.md",  # cahier des charges
]


def is_protected_path(path: str) -> bool:
    """True si le chemin est dans le noyau immuable (§11). Pattern minimal :
    exact match OR endswith (gère les chemins relatifs et absolus)."""
    return any(path == p or path.endswith("/" + p) for p in _PROTECTED_PATHS)


# ── Patches proposés ────────────────────────────────────────────────────────


class PatchKind(StrEnum):
    """Catégories de patches proposés par le Curator."""

    ARCHIVE_FACT = "archive_fact"  # fact dépassé sur sa demi-vie
    MARK_SKILL_STALE = "mark_skill_stale"  # skill non utilisée
    ARCHIVE_SKILL = "archive_skill"  # skill STALE depuis trop longtemps
    REJECT_STALE_CANDIDATE = "reject_stale_candidate"  # candidate en attente trop longue
    REVIEW_CONTRADICTION = "review_contradiction"  # paires fact_relations à revoir
    REVIEW_INITIATIVE = "review_initiative"  # initiative qui pourrait être obsolète


@dataclass
class CuratorPatch:
    """Patch proposé par le Curator. EN MVP, AUCUN n'est auto-appliqué.

    `auto_appliable` est UN SIGNAL pour PHASE 6.x — il indique si l'action
    serait sûre selon le gate (typiquement decay = oui, modify_core = non).
    En PHASE 6 MVP `applied` reste TOUJOURS False côté Curator.
    """

    kind: PatchKind
    target: str  # fact_id, skill_name, initiative_id, etc.
    description: str  # description humaine du patch
    auto_appliable: bool  # signal seulement — n'autorise PAS l'application MVP
    applied: bool = False  # toujours False en PHASE 6 MVP
    reason: str = ""


# ── Rapport global ──────────────────────────────────────────────────────────


@dataclass
class CuratorReport:
    """Rapport produit par une passe Curator nocturne (ou manuelle)."""

    generated_at: str
    duration_seconds: float
    # Inventaire
    facts_active: int = 0
    facts_superseded: int = 0
    facts_archive_proposed: int = 0
    skills_active: int = 0
    skills_stale_proposed: int = 0
    skills_archive_proposed: int = 0
    candidates_pending: int = 0
    candidates_to_reject: int = 0
    contradictions: int = 0
    # Coûts (depuis BudgetGuard)
    budget_global_spent_usd: float = 0.0
    budget_global_limit_usd: float = 0.0
    budget_status: str = "unknown"
    # Initiatives audit (lecture InitiativeStore)
    initiatives_pending: int = 0
    initiatives_validated_recent: int = 0
    initiatives_rejected_recent: int = 0
    # Patches proposés (jamais appliqués MVP)
    patches: list[CuratorPatch] = field(default_factory=list)
    # Notes humaines libres
    notes: list[str] = field(default_factory=list)
    # Sécurité — refus de patches protégés
    refused_protected_patches: list[str] = field(default_factory=list)


# ── Curator ─────────────────────────────────────────────────────────────────


class Curator:
    """Job de maintenance nocturne : RAPPORTE + PROPOSE, n'applique rien MVP."""

    def __init__(
        self,
        kernel: MemoryKernel,
        skill_lifecycle: SkillLifecycle,
        initiative_store: InitiativeStore,
        budget_guard: BudgetGuard | None,
        reports_dir: Path | None = None,
    ) -> None:
        self._kernel = kernel
        self._skills = skill_lifecycle
        self._initiatives = initiative_store
        self._budget = budget_guard
        self._reports_dir = (
            Path(reports_dir) if reports_dir else MEMORY_DATA_DIR / "curator_reports"
        )
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Scan principal ────────────────────────────────────────────────────────

    async def scan(self) -> CuratorReport:
        """Lance une passe complète. Produit un rapport, ne modifie RIEN."""
        started = datetime.now()
        report = CuratorReport(generated_at=started.isoformat(), duration_seconds=0.0)

        self._scan_facts(report)
        self._scan_skills(report)
        self._scan_contradictions(report)
        self._scan_budget(report)
        self._scan_initiatives(report)

        # MVP : on filtre toute proposition qui toucherait au noyau §11
        report.patches, refused = self._filter_protected_patches(report.patches)
        report.refused_protected_patches.extend(refused)

        report.duration_seconds = (datetime.now() - started).total_seconds()
        self._persist_report(report)
        logger.info(
            "Curator scan terminé",
            patches=len(report.patches),
            refused=len(report.refused_protected_patches),
            duration_s=int(report.duration_seconds),
        )
        return report

    # ── Étape 1 — facts à archiver par decay ──────────────────────────────────

    def _scan_facts(self, report: CuratorReport) -> None:
        """Pour chaque fact ACTIVE, calcule si son âge dépasse N demi-vies."""

        active: list[Fact] = self._kernel.list_facts_by_status(FactStatus.ACTIVE)
        superseded = self._kernel.count_facts(FactStatus.SUPERSEDED)
        report.facts_active = len(active)
        report.facts_superseded = superseded
        now = datetime.now()
        for fact in active:
            halflife = _HALFLIFE_DAYS.get(fact.decay_policy, 90.0)
            if halflife == float("inf"):
                continue  # identity/decision/memory_correction : pas de decay
            age_days = (now - fact.last_seen_at).total_seconds() / 86400.0
            if age_days >= halflife * _DECAY_HALFLIVES_THRESHOLD:
                report.facts_archive_proposed += 1
                report.patches.append(
                    CuratorPatch(
                        kind=PatchKind.ARCHIVE_FACT,
                        target=fact.id,
                        description=(
                            f"Fact '{fact.subject} {fact.predicate} {fact.object[:60]}' "
                            f"(cat {fact.category}) dépasse {_DECAY_HALFLIVES_THRESHOLD} "
                            f"demi-vies — saillance < 12.5%. Suggestion : archiver."
                        ),
                        auto_appliable=True,  # decay → archive est réversible et confiné
                        reason=f"age={age_days:.0f}j, halflife={halflife:.0f}j",
                    )
                )

    # ── Étape 2 — skills stale et archive ─────────────────────────────────────

    def _scan_skills(self, report: CuratorReport) -> None:
        actives = self._skills.list_by_status(SkillStatus.ACTIVE)
        stale = self._skills.list_by_status(SkillStatus.STALE)
        pending = self._skills.list_by_status(SkillStatus.SANDBOXED_PASS)
        report.skills_active = len(actives)
        report.candidates_pending = len(pending)
        now = datetime.now()

        # ACTIVE → STALE
        for rec in actives:
            ref = rec.last_used_at or rec.promoted_at or rec.created_at
            days = (now - ref).total_seconds() / 86400.0
            if days >= _SKILL_STALE_DAYS:
                report.skills_stale_proposed += 1
                report.patches.append(
                    CuratorPatch(
                        kind=PatchKind.MARK_SKILL_STALE,
                        target=rec.name,
                        description=(
                            f"Skill '{rec.name}' non utilisée depuis "
                            f"{days:.0f}j (seuil {_SKILL_STALE_DAYS}j). "
                            "Suggestion : passer en STALE."
                        ),
                        auto_appliable=True,
                        reason=f"days_since_use={days:.0f}",
                    )
                )

        # STALE → ARCHIVED
        for rec in stale:
            ref = rec.last_used_at or rec.promoted_at or rec.created_at
            days = (now - ref).total_seconds() / 86400.0
            if days >= _SKILL_STALE_DAYS + _SKILL_ARCHIVE_DAYS:
                report.skills_archive_proposed += 1
                report.patches.append(
                    CuratorPatch(
                        kind=PatchKind.ARCHIVE_SKILL,
                        target=rec.name,
                        description=(
                            f"Skill '{rec.name}' STALE depuis "
                            f"{days:.0f}j. Suggestion : archiver (réversible)."
                        ),
                        auto_appliable=True,
                        reason=f"days_since_use={days:.0f}",
                    )
                )

        # Candidates SANDBOXED_PASS en attente depuis trop longtemps
        for rec in pending:
            days = (now - rec.created_at).total_seconds() / 86400.0
            if days >= _CANDIDATE_EXPIRY_DAYS:
                report.candidates_to_reject += 1
                report.patches.append(
                    CuratorPatch(
                        kind=PatchKind.REJECT_STALE_CANDIDATE,
                        target=rec.name,
                        description=(
                            f"Candidate '{rec.name}' en attente de validation "
                            f"depuis {days:.0f}j (seuil {_CANDIDATE_EXPIRY_DAYS}j). "
                            "Suggestion : reject (la candidate reste sur disque "
                            "pour audit)."
                        ),
                        # Reject est sensible — exige humain explicite, jamais auto
                        auto_appliable=False,
                        reason=f"pending_for={days:.0f}j",
                    )
                )

    # ── Étape 3 — contradictions ──────────────────────────────────────────────

    def _scan_contradictions(self, report: CuratorReport) -> None:
        """Compte les paires SUPERSEDES dans fact_relations.

        Une SUPERSEDES est une "contradiction" résolue (l'ancien fact archivé).
        Le Curator propose une review humaine si beaucoup de supersessions
        récentes — signal qu'un sujet change vite et mérite attention.
        """
        with sqlite3.connect(self._kernel.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM fact_relations WHERE relation_type='supersedes'"
            ).fetchone()
        n = int(row[0]) if row else 0
        report.contradictions = n

        # Si > 10 supersessions sur la base, on propose une review
        if n > 10:
            report.patches.append(
                CuratorPatch(
                    kind=PatchKind.REVIEW_CONTRADICTION,
                    target="kernel_global",
                    description=(
                        f"{n} supersessions tracées dans fact_relations. "
                        "Suggestion : revue humaine pour identifier les sujets "
                        "qui changent souvent (peut indiquer une instabilité "
                        "de l'extracteur ou des objectifs réels)."
                    ),
                    auto_appliable=False,
                    reason=f"supersedes_count={n}",
                )
            )

    # ── Étape 4 — budget ──────────────────────────────────────────────────────

    def _scan_budget(self, report: CuratorReport) -> None:
        if self._budget is None:
            report.budget_status = "disabled"
            return
        try:
            status = self._budget.status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator: budget.status() échec", error=str(exc))
            report.budget_status = "error"
            return
        global_block = status.get("global", {})
        report.budget_global_spent_usd = global_block.get("spent_usd", 0.0)
        report.budget_global_limit_usd = global_block.get("limit_usd", 0.0)
        report.budget_status = global_block.get("status", "unknown")
        if report.budget_status == "hard_stop":
            report.notes.append(
                f"⚠️ Budget global HARD_STOP : "
                f"{report.budget_global_spent_usd:.2f}$ "
                f"/ {report.budget_global_limit_usd:.2f}$. "
                "Toutes les missions sont en pause budgétaire."
            )
        elif report.budget_status == "warning":
            report.notes.append(
                f"Budget global en alerte : {global_block.get('utilization_pct', 0):.0f}% utilisé."
            )

    # ── Étape 5 — initiatives proactives ──────────────────────────────────────

    def _scan_initiatives(self, report: CuratorReport) -> None:
        try:
            recent = self._initiatives.list_recent(days=7)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator: initiatives load échec", error=str(exc))
            return
        report.initiatives_pending = sum(1 for i in recent if i.status == "pending")
        report.initiatives_validated_recent = sum(1 for i in recent if i.status == "approved")
        report.initiatives_rejected_recent = sum(1 for i in recent if i.status == "rejected")

        # Propose review pour initiatives pending > 3 jours (probablement obsolètes)
        now = datetime.now()
        for i in recent:
            if i.status != "pending":
                continue
            age_days = (now - i.created_at).total_seconds() / 86400.0
            if age_days > 3:
                report.patches.append(
                    CuratorPatch(
                        kind=PatchKind.REVIEW_INITIATIVE,
                        target=i.id,
                        description=(
                            f"Initiative '{i.title}' en attente depuis "
                            f"{age_days:.0f}j. Suggestion : reviewer ou rejeter."
                        ),
                        auto_appliable=False,
                        reason=f"pending_for={age_days:.0f}j",
                    )
                )

    # ── Garde-fou §11 — refus patches protégés ────────────────────────────────

    def _filter_protected_patches(
        self, patches: list[CuratorPatch]
    ) -> tuple[list[CuratorPatch], list[str]]:
        """Retire toute proposition qui toucherait au noyau §11.

        En MVP les patches actuels (decay fact / mark skill stale / archive
        skill / reject candidate / review) ne touchent jamais le noyau (ils
        manipulent SQL/lifecycle, pas des fichiers). Mais on appliquera ce
        filtre DÈS MAINTENANT pour que si un futur patch type 'modify_prompt'
        ou 'edit_config' est ajouté, le filtre soit déjà en place.
        """
        kept: list[CuratorPatch] = []
        refused: list[str] = []
        for p in patches:
            if is_protected_path(p.target):
                refused.append(f"Patch {p.kind.value} sur '{p.target}' refusé : noyau protégé §11.")
                logger.warning(
                    "Curator: patch sur fichier protégé refusé",
                    kind=p.kind.value,
                    target=p.target,
                )
                continue
            kept.append(p)
        return kept, refused

    # ── Persistance rapport ───────────────────────────────────────────────────

    def _persist_report(self, report: CuratorReport) -> None:
        """JSON pour API + miroir MD pour humain (inert, écrasé à chaque scan)."""
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        json_path = self._reports_dir / f"{ts}.json"
        json_path.write_text(
            json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        latest_md = self._reports_dir / "latest.md"
        latest_md.write_text(_render_markdown(report), encoding="utf-8")
        logger.debug("Curator report persisted", json=str(json_path), md=str(latest_md))

    def latest_report(self) -> CuratorReport | None:
        """Renvoie le rapport le plus récent (lecture du dernier .json)."""
        reports = sorted(self._reports_dir.glob("*.json"), reverse=True)
        if not reports:
            return None
        try:
            data = json.loads(reports[0].read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator: latest_report parse échec", error=str(exc))
            return None
        return _report_from_dict(data)

    # ── Application contrôlée (PHASE 6 MVP : refuse tout) ────────────────────

    def apply_patch(self, patch_index: int, report: CuratorReport) -> tuple[bool, str]:
        """PHASE 6 MVP : REFUSE TOUJOURS — toute application exige humain.

        Cette méthode existe pour préparer PHASE 6.x où l'application
        sélective sera possible (via un endpoint validé). En MVP elle est
        un garde-fou vivant qui rappelle l'invariant : le Curator ne modifie
        RIEN automatiquement.

        Pour appliquer effectivement un patch, l'humain doit utiliser les
        endpoints des phases respectives (POST /api/skills/.../promote pour
        promouvoir, etc.).
        """
        if patch_index < 0 or patch_index >= len(report.patches):
            return False, f"patch_index {patch_index} hors borne"
        patch = report.patches[patch_index]
        if is_protected_path(patch.target):
            return False, "refusé : noyau protégé §11"
        # En MVP : aucun chemin d'application automatique.
        return False, (
            "Curator MVP refuse l'application automatique. "
            f"Patch {patch.kind.value} sur '{patch.target}' doit être appliqué "
            "manuellement par l'utilisateur via les endpoints dédiés "
            "(memory_correction, skill promote/reject, etc.)."
        )


# ── Sérialisation rapport ───────────────────────────────────────────────────


def _report_to_dict(report: CuratorReport) -> dict:
    d = asdict(report)
    # PatchKind StrEnum → str natif via dataclasses.asdict
    return d


def _report_from_dict(data: dict) -> CuratorReport:
    patches = [
        CuratorPatch(
            kind=PatchKind(p["kind"]),
            target=p["target"],
            description=p["description"],
            auto_appliable=p.get("auto_appliable", False),
            applied=p.get("applied", False),
            reason=p.get("reason", ""),
        )
        for p in data.get("patches", [])
    ]
    report = CuratorReport(
        generated_at=data["generated_at"],
        duration_seconds=data.get("duration_seconds", 0.0),
        facts_active=data.get("facts_active", 0),
        facts_superseded=data.get("facts_superseded", 0),
        facts_archive_proposed=data.get("facts_archive_proposed", 0),
        skills_active=data.get("skills_active", 0),
        skills_stale_proposed=data.get("skills_stale_proposed", 0),
        skills_archive_proposed=data.get("skills_archive_proposed", 0),
        candidates_pending=data.get("candidates_pending", 0),
        candidates_to_reject=data.get("candidates_to_reject", 0),
        contradictions=data.get("contradictions", 0),
        budget_global_spent_usd=data.get("budget_global_spent_usd", 0.0),
        budget_global_limit_usd=data.get("budget_global_limit_usd", 0.0),
        budget_status=data.get("budget_status", "unknown"),
        initiatives_pending=data.get("initiatives_pending", 0),
        initiatives_validated_recent=data.get("initiatives_validated_recent", 0),
        initiatives_rejected_recent=data.get("initiatives_rejected_recent", 0),
        patches=patches,
        notes=data.get("notes", []),
        refused_protected_patches=data.get("refused_protected_patches", []),
    )
    return report


def _render_markdown(report: CuratorReport) -> str:
    lines = [
        "# Curator Report (auto-généré, lecture seule)",
        "",
        f"_Généré : {report.generated_at} · durée {report.duration_seconds:.1f}s_",
        "",
        "## Inventaire",
        f"- Facts actifs : **{report.facts_active}**",
        f"- Facts supersedés : {report.facts_superseded}",
        f"- Facts proposés à archiver : **{report.facts_archive_proposed}**",
        f"- Skills actives : {report.skills_active}",
        f"- Skills proposées STALE : **{report.skills_stale_proposed}**",
        f"- Skills proposées ARCHIVED : {report.skills_archive_proposed}",
        f"- Candidates en attente review : {report.candidates_pending} "
        f"(dont **{report.candidates_to_reject}** à rejeter pour expiration)",
        f"- Contradictions tracées : {report.contradictions}",
        "",
        "## Budget",
        f"- Statut : **{report.budget_status}**",
        f"- Dépensé : {report.budget_global_spent_usd:.2f}$ "
        f"/ {report.budget_global_limit_usd:.2f}$",
        "",
        "## Initiatives proactives (7 derniers jours)",
        f"- Pending : {report.initiatives_pending}",
        f"- Validées : {report.initiatives_validated_recent}",
        f"- Rejetées : {report.initiatives_rejected_recent}",
        "",
    ]
    if report.patches:
        lines.append(f"## {len(report.patches)} patches PROPOSÉS (jamais auto-appliqués MVP)")
        for i, p in enumerate(report.patches):
            badge = "🟢 auto-éligible" if p.auto_appliable else "🔴 humain requis"
            lines.append(f"### Patch #{i} — {p.kind.value} {badge}")
            lines.append(f"- cible : `{p.target}`")
            lines.append(f"- raison : {p.reason}")
            lines.append(f"- description : {p.description}")
            lines.append("")
    if report.refused_protected_patches:
        lines.append("## ⚠️ Patches REFUSÉS (noyau §11 protégé)")
        for r in report.refused_protected_patches:
            lines.append(f"- {r}")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        for n in report.notes:
            lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


__all__ = [
    "Curator",
    "CuratorPatch",
    "CuratorReport",
    "PatchKind",
    "is_protected_path",
]
