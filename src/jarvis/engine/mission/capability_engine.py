"""Capability Engine (CDC §8) — détection de gap + délégation au SkillLab.

C'est la phase la plus DANGEREUSE du projet (cf. CDC §8 anti-patterns).
Un agent qui détecte un manque et fabrique son propre outil peut, sans
garde-fous, exfiltrer des tokens, installer un paquet compromis, se casser.
La capacité et le garde-fou sont le MÊME sujet.

Invariants non négociables MVP :
- AUCUN second chemin de génération/installation : on délègue STRICTEMENT au
  SkillLab (PHASE 4). Pas de reimplémentation maison.
- AUCUNE auto-installation : même si le sandbox passe vert, on s'arrête à la
  validation humaine. Le flag settings.auto_install_whitelisted_enabled est
  False par défaut et NON consulté en MVP.
- AUCUNE skill INSTALL_PACKAGE ni MODIFY_CORE en auto, jamais : le gate
  composite (§9) reste la porte, le CapabilityEngine ne le contourne pas.

Boucle CDC §8 :
  1. Cherche une skill existante qui matche → si oui, retourne le pointer
  2. Cherche un tool existant qui matche → si oui, retourne le pointer
  3. Sinon → délègue au Lab via lab.propose_from_trajectory()
  4. Log Event 'capability_gap_recorded' avec la résolution
  5. Renvoie le résultat structuré au caller (jamais d'install même si vert)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml
from loguru import logger

from jarvis.kernel.contracts import (
    MemoryStore as MemoryKernel,
)
from jarvis.kernel.contracts import (
    SkillLab,
    SkillRegistry,
    ToolRegistry,
)
from jarvis.kernel.schemas import SkillRecord, SkillStatus

# Seuil heuristique de matching textuel (sur jaccard normalisé).
# Bas pour MVP : on préfère détecter des matchs faibles plutôt que de
# proposer une candidate à tort. Le tokenizer ne fait pas de stemming, donc
# "afficher" vs "affichage" sont distincts — d'où le seuil bas.
# Le matcher sémantique (embeddings) reviendra en PHASE 5.x si besoin.
_MATCH_THRESHOLD = 0.2
_STOP_WORDS = frozenset(
    {
        "de",
        "du",
        "la",
        "le",
        "les",
        "un",
        "une",
        "des",
        "à",
        "au",
        "aux",
        "et",
        "ou",
        "en",
        "pour",
        "par",
        "sur",
        "dans",
        "avec",
        "sans",
        "the",
        "a",
        "an",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "without",
        "je",
        "tu",
        "il",
        "elle",
        "vous",
        "nous",
        "ils",
        "ce",
        "cette",
        "ces",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "qui",
        "que",
        "quoi",
        "comment",
        "pourquoi",
    }
)


class ResolutionKind(StrEnum):
    """Comment le gap a été résolu (ou pas)."""

    EXISTING_SKILL = "existing_skill"  # une skill installée correspond
    EXISTING_TOOL = "existing_tool"  # un tool natif correspond
    NEW_CANDIDATE = "new_candidate"  # candidate générée par le Lab (attend humain)
    LAB_FAILED = "lab_failed"  # le Lab n'a pas produit (LLM down, JSON KO)
    SANDBOX_REJECTED = "sandbox_rejected"  # candidate générée mais SANDBOXED_FAIL
    BLOCKED_DANGEROUS = "blocked_dangerous"  # description évoque INSTALL_PACKAGE ou MODIFY_CORE


@dataclass
class CapabilityGapResolution:
    """Résultat du processing d'un gap par CapabilityEngine."""

    description: str
    kind: ResolutionKind
    target_name: str | None = None  # nom de la skill/tool/candidate
    candidate_record: SkillRecord | None = None  # SkillRecord du Lab si new_candidate
    notes: str = ""
    event_id: str | None = None  # event capability_gap_recorded tracé


# ── Whitelist (PHASE 5 MVP : inerte) ──────────────────────────────────────────


@dataclass
class WhitelistDomain:
    name: str
    max_access_level: str = "WRITE_LOCAL"
    allowed_categories: list[str] = field(default_factory=list)
    description_must_contain: list[str] = field(default_factory=list)


@dataclass
class Whitelist:
    """config/permissions.yaml parsé. INERTE en MVP."""

    domains: list[WhitelistDomain] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Whitelist:
        if not path.exists():
            return cls(domains=[])
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.warning("Whitelist YAML invalide", error=str(exc))
            return cls(domains=[])
        domains = []
        for d in data.get("domains", []) or []:
            if not isinstance(d, dict):
                continue
            domains.append(
                WhitelistDomain(
                    name=str(d.get("name", "")),
                    max_access_level=str(d.get("max_access_level", "WRITE_LOCAL")),
                    allowed_categories=list(d.get("allowed_categories", []) or []),
                    description_must_contain=list(d.get("description_must_contain", []) or []),
                )
            )
        return cls(domains=domains)

    def matches(self, description: str) -> WhitelistDomain | None:
        """Trouve un domaine whitelisté qui matche la description (cf. PHASE 5.x)."""
        low = description.lower()
        for dom in self.domains:
            keywords = [k.lower() for k in dom.description_must_contain]
            if keywords and any(k in low for k in keywords):
                return dom
        return None


# ── Heuristique de matching textuel ──────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Tokens lowercase, sans stop-words, sans ponctuation."""
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9_-]+", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS and len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Patterns dangereux — court-circuit explicite avant tout LLM call ─────────

# Mots-clés qui signalent une demande dangereuse (INSTALL_PACKAGE/MODIFY_CORE).
# Le CapabilityEngine refuse de générer pour ces cas — même la GÉNÉRATION
# n'est pas autorisée car l'agent pourrait être manipulé pour fabriquer un
# outil malveillant. Le gate composite refuserait à l'exécution, mais on
# évite même la production en zone tampon (économie LLM + signal au caller).
_DANGEROUS_PATTERNS = [
    re.compile(r"\b(pip|npm|apt|brew|cargo)\s+install\b", re.IGNORECASE),
    # Variantes FR : "installer un/une/le/la/des/quelques (nouveau/nouvelle) paquet/package/..."
    re.compile(
        r"\binstall(?:er|ation)?(?:\s+(?:un|une|le|la|des|du|quelques?))?"
        r"(?:\s+(?:nouveaux?|nouvelles?|petit|petits))?\s+"
        r"(?:paquet|package|library|librairie|module|d[ée]pendance|requirement)",
        re.IGNORECASE,
    ),
    # Variantes EN : "install a/the/some (new) package/library/..."
    re.compile(
        r"\b(?:install|installation)(?:\s+(?:a|the|some|any))?"
        r"(?:\s+(?:new|fresh|small))?\s+"
        r"(?:package|library|module|dependency|requirement)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmodif(?:ier|y)(?:\s+(?:le|la|the))?\s+(?:core|noyau|runtime)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bsystem\s+(?:level|niveau)\b", re.IGNORECASE),
]


def _looks_dangerous(description: str) -> bool:
    """Pré-filtre : la description évoque-t-elle INSTALL_PACKAGE / MODIFY_CORE ?"""
    return any(p.search(description) for p in _DANGEROUS_PATTERNS)


# ── Capability Engine ────────────────────────────────────────────────────────


class CapabilityEngine:
    """Détecte un gap, cherche existant, sinon délègue au Lab. JAMAIS auto-install MVP."""

    def __init__(
        self,
        kernel: MemoryKernel,
        lab: SkillLab,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        whitelist: Whitelist | None = None,
        *,
        auto_install_enabled: bool = False,
    ) -> None:
        self._kernel = kernel
        self._lab = lab
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._whitelist = whitelist or Whitelist(domains=[])
        # PHASE 5 MVP : flag INERTE — toute candidate exige promote() humain.
        # Le flag est stocké mais le code MVP ne consulte JAMAIS la whitelist
        # pour décider d'auto-installer. Sa présence prépare PHASE 5.x.
        self._auto_install_enabled = auto_install_enabled

    # ── API publique ─────────────────────────────────────────────────────────

    async def detect_and_propose(
        self,
        description: str,
        example_input: str | None = None,
    ) -> CapabilityGapResolution:
        """Pipeline §8. Renvoie une résolution structurée, JAMAIS d'install auto.

        Args:
            description : verbalisation du besoin par le LLM ou par un caller
                          ("transcrire un fichier .ogg", "parser un format X").
            example_input : optionnel, échantillon de l'input qui a échoué (pour
                            informer le LLM du Lab sur la nature du gap).
        """
        # Étape 0 — court-circuit dangereux. On refuse même la génération.
        if _looks_dangerous(description):
            logger.warning(
                "CapabilityEngine: demande dangereuse refusée AVANT génération",
                description=description[:120],
            )
            event_id = self._record_event(
                description=description,
                kind=ResolutionKind.BLOCKED_DANGEROUS,
                target_name=None,
                notes=(
                    "Description évoque INSTALL_PACKAGE / MODIFY_CORE — "
                    "génération refusée par CapabilityEngine, le gate "
                    "composite (§9) refuserait également à l'exécution."
                ),
            )
            return CapabilityGapResolution(
                description=description,
                kind=ResolutionKind.BLOCKED_DANGEROUS,
                notes="Demande évoque install package / modify core — refusé.",
                event_id=event_id,
            )

        # Étape 1 — skill existante ?
        existing_skill = self._match_existing_skill(description)
        if existing_skill is not None:
            event_id = self._record_event(
                description, ResolutionKind.EXISTING_SKILL, existing_skill
            )
            return CapabilityGapResolution(
                description=description,
                kind=ResolutionKind.EXISTING_SKILL,
                target_name=existing_skill,
                notes=f"Skill installée '{existing_skill}' couvre déjà ce besoin.",
                event_id=event_id,
            )

        # Étape 2 — tool existant ?
        existing_tool = self._match_existing_tool(description)
        if existing_tool is not None:
            event_id = self._record_event(description, ResolutionKind.EXISTING_TOOL, existing_tool)
            return CapabilityGapResolution(
                description=description,
                kind=ResolutionKind.EXISTING_TOOL,
                target_name=existing_tool,
                notes=f"Tool natif '{existing_tool}' couvre déjà ce besoin.",
                event_id=event_id,
            )

        # Étape 3 — déléguer au Lab (génération + sandbox).
        trajectory = self._build_trajectory(description, example_input)
        record = await self._lab.propose_from_trajectory(trajectory, source_event_id=None)
        if record is None:
            event_id = self._record_event(
                description,
                ResolutionKind.LAB_FAILED,
                target_name=None,
                notes="Lab.propose_from_trajectory a retourné None (LLM down / JSON KO).",
            )
            return CapabilityGapResolution(
                description=description,
                kind=ResolutionKind.LAB_FAILED,
                notes="Lab n'a pas pu générer la candidate.",
                event_id=event_id,
            )

        # Étape 4 — décide la résolution selon le verdict sandbox.
        # CRITIQUE PHASE 5 MVP : peu importe le résultat, on NE PROMOTE PAS auto.
        # Même si self._auto_install_enabled est True et que la whitelist matche,
        # on s'arrête à la décision humaine. Le flag est stocké mais inerte.
        if record.status == SkillStatus.SANDBOXED_PASS:
            kind = ResolutionKind.NEW_CANDIDATE
            notes = (
                f"Candidate '{record.name}' générée et sandbox vert. "
                "EN ATTENTE de validation humaine — aucune auto-installation "
                "en PHASE 5 MVP."
            )
        else:
            kind = ResolutionKind.SANDBOX_REJECTED
            notes = (
                f"Candidate '{record.name}' rejetée par le sandbox : "
                f"{record.sandbox_notes or '(détail manquant)'}"
            )

        event_id = self._record_event(
            description=description,
            kind=kind,
            target_name=record.name,
            notes=notes,
        )

        return CapabilityGapResolution(
            description=description,
            kind=kind,
            target_name=record.name,
            candidate_record=record,
            notes=notes,
            event_id=event_id,
        )

    # ── Matching heuristique ────────────────────────────────────────────────

    def _match_existing_skill(self, description: str) -> str | None:
        """Cherche une skill installée dont (name|description|tags) chevauche
        suffisamment la description du besoin (jaccard ≥ _MATCH_THRESHOLD)."""
        try:
            installed = self._skill_registry.list_installed()
        except Exception as exc:  # noqa: BLE001 — registry peut planter
            logger.warning("CapabilityEngine: skill_registry.list_installed échec", error=str(exc))
            return None

        desc_tokens = _tokenize(description)
        best: tuple[str, float] | None = None
        for s in installed:
            text = " ".join(
                [
                    str(s.get("name", "")),
                    str(s.get("label", "")),
                    str(s.get("description", "")),
                    " ".join(s.get("tags", []) or []),
                ]
            )
            score = _jaccard(desc_tokens, _tokenize(text))
            if best is None or score > best[1]:
                best = (str(s.get("name", "")), score)
        if best is not None and best[1] >= _MATCH_THRESHOLD:
            return best[0]
        return None

    def _match_existing_tool(self, description: str) -> str | None:
        """Cherche un tool natif dont name|description chevauche."""
        try:
            schemas = self._tool_registry.schemas()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CapabilityEngine: tool_registry.schemas échec", error=str(exc))
            return None

        desc_tokens = _tokenize(description)
        best: tuple[str, float] | None = None
        for sch in schemas:
            text = " ".join(
                [
                    str(sch.get("name", "")),
                    str(sch.get("description", "")),
                ]
            )
            score = _jaccard(desc_tokens, _tokenize(text))
            if best is None or score > best[1]:
                best = (str(sch.get("name", "")), score)
        if best is not None and best[1] >= _MATCH_THRESHOLD:
            return best[0]
        return None

    @staticmethod
    def _build_trajectory(description: str, example_input: str | None) -> dict:
        """Construit la trajectoire pour le SkillLab depuis le besoin verbalisé."""
        return {
            "task_description": description[:600],
            "messages": [],
            "tool_calls": [],
            "result": example_input[:400] if example_input else "",
        }

    # ── Event Kernel — mémorisation §8 étape 6 ──────────────────────────────

    def _record_event(
        self,
        description: str,
        kind: ResolutionKind,
        target_name: str | None,
        notes: str = "",
    ) -> str:
        """Trace dans le Kernel pour audit + pipeline ingest PHASE 3 éventuel."""
        evt = self._kernel.log_event(
            type="capability_gap_recorded",
            source="capability_engine",
            content=(
                f"Gap signalé : {description[:300]}\n"
                f"Résolution : {kind.value}"
                + (f" → {target_name}" if target_name else "")
                + (f"\nNotes : {notes[:300]}" if notes else "")
            ),
            metadata={
                "description": description[:600],
                "resolution_kind": kind.value,
                "target_name": target_name,
                "notes": notes[:600],
            },
        )
        return evt.id


__all__ = [
    "CapabilityEngine",
    "CapabilityGapResolution",
    "ResolutionKind",
    "Whitelist",
    "WhitelistDomain",
]
