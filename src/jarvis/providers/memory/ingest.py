"""Pipeline d'ingestion : event → facts via LLM + réconciliation (CDC §6.4–§6.6).

**Le cœur dur de la PHASE 3.** La plomberie (kernel SQL) est facile ; la décision
"ce fait en confirme un autre / en contredit un autre / coexiste" est 90 % de la
difficulté.

Trois cas de réconciliation (§6.4 étape 5) :
- **Identique/quasi-identique** → FactObservation `confirm`, +confidence, +support_count.
- **Contradictoire** (même subject+predicate+category, object différent) → ancien
  passe `superseded`, nouveau créé, relation `supersedes`.
- **Nouveau compatible** → nouveau fact.

Hors vocabulaire (§6.4 étape 2) → `status=NEEDS_REVIEW`, jamais en base principale.

Confidence (§6.5) : 0.55 (inférence faible), 0.75 (énoncé explicite),
0.9 (correction directe). Monte à chaque ré-observation compatible (+0.05 cap 0.99).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from jarvis.kernel.events import EventBus, MemoryIngested
from jarvis.kernel.vocab import CATEGORIES, PREDICATES
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.kernel import MemoryKernel, _new_id, normalize
from jarvis.providers.memory.schemas import (
    DecayPolicy,
    Event,
    Fact,
    FactStatus,
    ObservationType,
    RelationType,
)

# ── Constantes (§6.5, §6.6) ───────────────────────────────────────────────────

# Confidence initiales par origine
CONFIDENCE_INFERENCE = 0.55
CONFIDENCE_EXPLICIT = 0.75
CONFIDENCE_CORRECTION = 0.9

# Delta de renforcement à chaque ré-observation compatible
CONFIRM_DELTA = 0.05
CONFIDENCE_CAP = 0.99

# Decay par catégorie (§6.6)
_DECAY_BY_CATEGORY: dict[str, DecayPolicy] = {
    "identity": DecayPolicy.NONE,
    "values": DecayPolicy.VERY_SLOW,
    "decision": DecayPolicy.NONE,  # superseable mais ne décroît pas
    "preference": DecayPolicy.MEDIUM,
    "project": DecayPolicy.MEDIUM,
    "habit": DecayPolicy.MEDIUM,
    "goal": DecayPolicy.FAST,
    "constraint": DecayPolicy.SLOW,
    "belief": DecayPolicy.SLOW,
    "relationship": DecayPolicy.SLOW,
    "tool": DecayPolicy.MEDIUM,
    "persona": DecayPolicy.SLOW,
    "memory_correction": DecayPolicy.NONE,
    "health_fitness": DecayPolicy.MEDIUM,
    "work_style": DecayPolicy.SLOW,
}

# Catégories "stables" : une contradiction sur ces catégories déclenche supersession.
# Sur les autres, on tolère la coexistence (plusieurs préférences peuvent cohabiter).
_STABLE_CATEGORIES: frozenset[str] = frozenset(
    {"identity", "goal", "values", "decision", "constraint", "persona"}
)


# ── Prompt LLM ────────────────────────────────────────────────────────────────


_EXTRACT_SYSTEM = (
    "Tu es un agent d'extraction de mémoire à long terme. Tu extrais des faits "
    "ATOMIQUES (une idée par fait) à partir d'un échange. Tu utilises uniquement "
    "un vocabulaire fermé. Tu réponds en JSON strict, sans markdown, sans préambule."
)


def _build_prompt(content: str, source: str) -> str:
    pred_list = ", ".join(sorted(PREDICATES))
    cat_list = ", ".join(sorted(CATEGORIES))
    return (
        "## Contexte\n"
        f"Source : {source}\n"
        f"Échange à analyser :\n{content}\n\n"
        "## Périmètre d'extraction (CDC §6.8 — étroit)\n"
        "Extraire UNIQUEMENT : préférences, projets actifs, objectifs, contraintes, "
        "décisions, habitudes stables, persona, corrections explicites. Tout le reste "
        "doit être ignoré (pas de salutations, météo, contexte éphémère, etc.).\n\n"
        "## Vocabulaire fermé\n"
        f"predicate (obligatoire, choisir EXACTEMENT un dans la liste) : {pred_list}\n"
        f"category (obligatoire, choisir EXACTEMENT un dans la liste) : {cat_list}\n\n"
        "## Règles d'extraction\n"
        "- 0 à 5 faits maximum. Si rien d'intéressant, renvoie une liste vide.\n"
        "- Chaque fait est atomique (une seule idée). 'Barth court depuis un an et "
        "vise sub-3h' = DEUX faits.\n"
        "- subject est l'entité concernée (souvent 'Barth' ou 'jarvis').\n"
        "- object est la valeur/cible du fait, court et concret.\n"
        "- 'confidence_source' = 'inference' (déduit), 'explicit' (énoncé direct), "
        "ou 'correction' (l'utilisateur corrige).\n"
        "- 'importance' ∈ [0, 1] : à quel point ce fait éclaire la compréhension "
        "long terme de Barth. 0.3 = anecdotique, 0.7 = significatif, 0.9 = pivot.\n"
        "- Si tu utilises un prédicat ou une catégorie HORS de la liste, le fait sera "
        "rejeté en `needs_review`. Préfère renvoyer moins.\n\n"
        "## Forme canonique (CRITIQUE — évite les doublons sémantiques en aval)\n"
        "Le matching de réconciliation s'appuie sur (subject, predicate, category) + "
        "comparaison d'object. Si tu paraphrases, tu crées des doublons ou "
        "des supersessions abusives. Donc :\n"
        "- UN seul prédicat par sens. N'alterne PAS 'works_on' et 'has' pour la "
        "même idée. Tableau de mapping prédicat→catégorie privilégiés :\n"
        "  · habit          → utiliser `has` (jamais `works_on`)\n"
        "  · goal           → utiliser `targets`\n"
        "  · preference     → utiliser `prefers`\n"
        "  · tool           → utiliser `uses`\n"
        "  · identity       → utiliser `is`\n"
        "  · constraint     → utiliser `struggles_with` ou `needs`\n"
        "  · decision       → utiliser `decided`\n"
        "  · project        → utiliser `works_on`\n"
        "  · belief         → utiliser `believes`\n"
        "  · persona        → utiliser `communicates_as`\n"
        "  · values         → utiliser `values`\n"
        "- object COURT et CANONIQUE. Pour 'sub-3h marathon' / 'marathon en sub-3h' / "
        "'sub-3h au marathon', choisis UNE forme et tiens-t'y : préfère "
        "'<valeur> <discipline>' (ex. 'sub-3h marathon', pas 'marathon sub-3h').\n"
        "- Pas d'articles inutiles ('le', 'la', 'au', 'du'). Pas de mots de remplissage "
        "('comme habitude de vie', 'pour cette année', 'aujourd\\'hui').\n"
        "- En cas de doute entre deux formulations, choisis la PLUS COURTE et la plus "
        "factuelle. Ex. 'course à pied' plutôt que 'la course à pied régulière'.\n\n"
        "## Format de sortie\n"
        '{\n  "facts": [\n'
        '    {\n      "subject": "Barth",\n      "predicate": "prefers",\n'
        '      "object": "café noir",\n      "category": "preference",\n'
        '      "confidence_source": "explicit",\n      "importance": 0.4\n    }\n'
        "  ]\n}\n"
    )


# ── Prompt arbitre (étape 2 — match partiel) ──────────────────────────────────


_ARBITER_SYSTEM = (
    "Tu es un arbitre de réconciliation mémoire. Tu juges si un fait candidat "
    "EXPRIME LA MÊME IDÉE qu'un fait existant (paraphrase), s'il en CONTREDIT "
    "l'essence, ou s'il est une idée DISTINCTE. Tu réponds en JSON strict."
)


def _build_arbiter_prompt(cand: _Candidate, possibles: list[Fact]) -> str:
    lines = [
        "## Fait candidat (à classer)",
        f"  subject:   {cand.subject}",
        f"  predicate: {cand.predicate}",
        f"  object:    {cand.object}",
        f"  category:  {cand.category}",
        "",
        "## Faits existants ACTIFS du même sujet, même catégorie",
    ]
    for f in possibles:
        lines.append(
            f"  [{f.id}]  {f.subject} {f.predicate} {f.object}  "
            f"(conf {f.confidence:.2f}, vu {f.support_count}×)"
        )
    lines.extend(
        [
            "",
            "## Question",
            "Le CANDIDAT est-il :",
            "  - 'same_as' : EXACTEMENT la même idée qu'un fait existant (paraphrase, "
            "reformulation textuelle, même intention) ? Renvoie son fact_id.",
            "  - 'contradicts' : CONTREDIT-il un fait existant sur sa valeur essentielle "
            "(ex. objectif chiffré différent, identité différente) ? Renvoie son fact_id.",
            "  - 'new' : Idée DISTINCTE, ni paraphrase ni contradiction ? target=null.",
            "",
            "RÈGLE STRICTE : 'same_as' UNIQUEMENT si le candidat et le fait existant ",
            "désignent la même chose en pratique. Une simple réorganisation de mots ('marathon",
            " en 3h10' vs '3h10 marathon') ou un mot de liaison déplacé ('au marathon' vs ",
            "'marathon') = same_as. Une valeur cible différente (sub-3h vs 3h10) = contradicts.",
            "",
            "## Réponse JSON",
            '{"verdict": "same_as|contradicts|new", "target_fact_id": "fact_xxx" ou null, '
            '"notes": "raisonnement bref"}',
        ]
    )
    return "\n".join(lines)


# ── Résultats ─────────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    """Trace d'une ingestion."""

    event: Event
    confirmed: list[Fact]  # facts dont le support_count a augmenté
    superseded_pairs: list[tuple[Fact, Fact]]  # (ancien, nouveau)
    new_facts: list[Fact]  # facts compatibles créés
    needs_review: list[Fact]  # facts hors vocabulaire
    raw_extracted_count: int  # nb de candidats avant réconciliation


# ── Pipeline ──────────────────────────────────────────────────────────────────


class MemoryIngest:
    """Pipeline d'ingestion. Une instance partage le kernel et le LLM extracteur.

    `arbiter_calls` : nombre d'appels au LLM arbitre depuis la création de l'instance.
    Exposé pour télémétrie/coût (cf. cas "match partiel" §6.4 étape 5 — v2).
    """

    def __init__(
        self,
        kernel: MemoryKernel,
        llm: LLMProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._kernel = kernel
        self._llm = llm
        self._bus = bus
        # Compteur d'appels au LLM arbitre (étape 2 du matcher v2).
        self.arbiter_calls = 0

    async def ingest(
        self,
        content: str,
        source: str = "conversation",
        event_type: str = "exchange",
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult:
        """Pipeline complet : log event → extraire facts → réconcilier."""
        evt = self._kernel.log_event(event_type, source, content, metadata)
        candidates = await self._extract_facts(content, source)

        confirmed: list[Fact] = []
        superseded_pairs: list[tuple[Fact, Fact]] = []
        new_facts: list[Fact] = []
        needs_review: list[Fact] = []

        for cand in candidates:
            outcome = await self._reconcile(cand, evt)
            if outcome.kind == "confirmed":
                confirmed.append(outcome.fact)
            elif outcome.kind == "superseded":
                assert outcome.old_fact is not None
                superseded_pairs.append((outcome.old_fact, outcome.fact))
                new_facts.append(outcome.fact)
            elif outcome.kind == "new":
                new_facts.append(outcome.fact)
            elif outcome.kind == "needs_review":
                needs_review.append(outcome.fact)

        result = IngestResult(
            event=evt,
            confirmed=confirmed,
            superseded_pairs=superseded_pairs,
            new_facts=new_facts,
            needs_review=needs_review,
            raw_extracted_count=len(candidates),
        )

        if self._bus is not None:
            await self._bus.publish(
                MemoryIngested(
                    event_id=evt.id,
                    fact_count=len(confirmed) + len(new_facts),
                    source=source,
                )
            )

        return result

    # ── Étape 2 : extraction LLM ──────────────────────────────────────────────

    async def _extract_facts(self, content: str, source: str) -> list[_Candidate]:
        prompt = _build_prompt(content, source)
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_EXTRACT_SYSTEM,
                stream=False,
                context="memory",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ingest LLM extract error", error=str(exc))
            return []

        if not isinstance(raw, str):
            return []
        parsed = _parse_extract_response(raw)
        return parsed

    # ── Étape 5 : réconciliation v2 (deux étages) ─────────────────────────────

    async def _reconcile(self, cand: _Candidate, evt: Event) -> _Outcome:
        """Réconciliation v2 — déterministe en priorité, arbitre LLM sur match partiel.

        Étage 1 (déterministe, gratuit, zéro LLM) : match exact (subj, pred, cat).
        Étage 2 (arbitre LLM, payant) : appelé UNIQUEMENT sur "match partiel" :
          - même triplet mais object différent sur catégorie stable
            (la supersession était abusive en v1 quand l'object n'était qu'une
            reformulation textuelle de la même valeur).
          - pas de match exact MAIS recouvrement FTS5 avec un sibling
            (un fait existant que le LLM extracteur a paraphrasé avec un autre
            prédicat — faux négatif du matcher syntaxique en v1).
        """
        # Vocab fermé : §6.4 étape 2 — hors vocab → needs_review.
        if cand.predicate not in PREDICATES or cand.category not in CATEGORIES:
            fact = self._make_fact(cand, evt, status=FactStatus.NEEDS_REVIEW)
            self._kernel.insert_fact(fact)
            return _Outcome("needs_review", fact)

        # ── Étage 1 — déterministe ────────────────────────────────────────
        match = self._kernel.find_active_match(
            subject=cand.subject,
            predicate=cand.predicate,
            category=cand.category,
        )

        if match is not None:
            # Object identique normalisé → CONFIRM franc, pas d'arbitre.
            if normalize(cand.object) == normalize(match.object):
                return self._confirm(match, cand, evt)

            # Object différent sur catégorie stable → MATCH PARTIEL.
            # En v1 : SUPERSEDE direct. En v2 : on arbitre via LLM
            # car la "contradiction" peut n'être qu'une reformulation textuelle.
            if cand.category in _STABLE_CATEGORIES:
                verdict = await self._arbitrate(cand, [match])
                if verdict.kind == "same_as":
                    return self._confirm(match, cand, evt)
                if verdict.kind == "contradicts":
                    return self._supersede(match, cand, evt)
                # arbitre : "new" → coexistence (rare sur stable mais possible)
                fact = self._make_fact(cand, evt, status=FactStatus.ACTIVE)
                self._kernel.insert_fact(fact)
                return _Outcome("new", fact)

            # Catégorie non stable, object différent → coexistence (sans arbitrage).
            fact = self._make_fact(cand, evt, status=FactStatus.ACTIVE)
            self._kernel.insert_fact(fact)
            return _Outcome("new", fact)

        # ── Étage 2 — pas de match exact : chercher des siblings via FTS5 ──
        siblings = self._find_overlap_siblings(cand)
        if siblings:
            verdict = await self._arbitrate(cand, siblings)
            if verdict.kind == "same_as" and verdict.target_fact_id:
                target = next((s for s in siblings if s.id == verdict.target_fact_id), None)
                if target is not None:
                    return self._confirm(target, cand, evt)
            elif verdict.kind == "contradicts" and verdict.target_fact_id:
                target = next((s for s in siblings if s.id == verdict.target_fact_id), None)
                if target is not None and target.category in _STABLE_CATEGORIES:
                    return self._supersede(target, cand, evt)
            # "new" ou cible introuvable → on tombe au fallback ci-dessous

        # Fallback : nouveau fait.
        fact = self._make_fact(cand, evt, status=FactStatus.ACTIVE)
        self._kernel.insert_fact(fact)
        return _Outcome("new", fact)

    # ── Étape 2bis — recherche de siblings via FTS5 (cap dur sur les appels) ──

    def _find_overlap_siblings(self, cand: _Candidate) -> list[Fact]:
        """Cherche des facts ACTIFS du même subject + catégorie via FTS5 sur l'object.

        Filtré côté Python pour limiter les coûts arbitre :
        - même subject normalisé
        - même catégorie (paraphrase impossible inter-catégorie sans changement de sens)
        - status ACTIVE uniquement
        - top 3 max
        """
        matches = self._kernel.search_facts_fts(cand.object, k=10)
        out: list[Fact] = []
        subj = normalize(cand.subject)
        cat = normalize(cand.category)
        for fact, _score in matches:
            if fact.status != FactStatus.ACTIVE:
                continue
            if normalize(fact.subject) != subj:
                continue
            if normalize(fact.category) != cat:
                continue
            out.append(fact)
            if len(out) >= 3:
                break
        return out

    # ── Arbitre LLM ──────────────────────────────────────────────────────────

    async def _arbitrate(self, cand: _Candidate, possibles: list[Fact]) -> _ArbiterVerdict:
        """Appelle le LLM arbitre. Comptabilise l'appel. Doute → "new"."""
        self.arbiter_calls += 1
        prompt = _build_arbiter_prompt(cand, possibles)
        try:
            raw = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_ARBITER_SYSTEM,
                stream=False,
                context="memory",
            )
        except Exception as exc:  # noqa: BLE001 — erreur LLM = doute = new
            logger.warning("Arbiter LLM error → fallback 'new'", error=str(exc))
            return _ArbiterVerdict(kind="new", target_fact_id=None, notes=str(exc))

        if not isinstance(raw, str):
            return _ArbiterVerdict(kind="new", target_fact_id=None, notes="non-text")
        return _parse_arbiter_verdict(raw)

    def _confirm(self, existing: Fact, cand: _Candidate, evt: Event) -> _Outcome:
        existing.support_count += 1
        existing.confidence = min(CONFIDENCE_CAP, existing.confidence + CONFIRM_DELTA)
        existing.last_seen_at = datetime.now()
        existing.importance = max(existing.importance, cand.importance)
        self._kernel.update_fact(existing)
        self._kernel.record_observation(
            fact_id=existing.id,
            event_id=evt.id,
            observation_type=ObservationType.CONFIRM,
            confidence_delta=CONFIRM_DELTA,
        )
        return _Outcome("confirmed", existing)

    def _supersede(self, old: Fact, cand: _Candidate, evt: Event) -> _Outcome:
        # L'ancien fait passe en superseded — on garde la source, jamais on supprime.
        old.status = FactStatus.SUPERSEDED
        old.updated_at = datetime.now()
        self._kernel.update_fact(old)
        # Le nouveau est créé en ACTIVE avec confidence cand
        new = self._make_fact(cand, evt, status=FactStatus.ACTIVE)
        self._kernel.insert_fact(new)
        # Relation supersedes : new → old
        self._kernel.link_facts(
            from_fact_id=new.id,
            to_fact_id=old.id,
            relation_type=RelationType.SUPERSEDES,
        )
        # Trace l'observation comme correction sur l'ancien
        self._kernel.record_observation(
            fact_id=old.id,
            event_id=evt.id,
            observation_type=ObservationType.CORRECT,
            confidence_delta=-old.confidence + CONFIDENCE_INFERENCE,
        )
        return _Outcome("superseded", new, old_fact=old)

    def _make_fact(self, cand: _Candidate, evt: Event, status: FactStatus) -> Fact:
        confidence = _initial_confidence(cand.confidence_source)
        decay = _DECAY_BY_CATEGORY.get(cand.category, DecayPolicy.MEDIUM)
        now = datetime.now()
        return Fact(
            id=_new_id("fact"),
            subject=normalize(cand.subject),
            predicate=normalize(cand.predicate),
            object=normalize(cand.object),
            category=normalize(cand.category),
            status=status,
            confidence=confidence,
            support_count=1,
            decay_policy=decay,
            importance=max(0.0, min(1.0, cand.importance)),
            source_event_id=evt.id,
            created_at=now,
            last_seen_at=now,
            updated_at=now,
        )


# ── Helpers ────────────────────────────────────────────────────────────────────


@dataclass
class _Candidate:
    """Fact candidat avant réconciliation."""

    subject: str
    predicate: str
    object: str  # noqa: A003
    category: str
    confidence_source: str  # inference | explicit | correction
    importance: float


@dataclass
class _Outcome:
    """Résultat d'une réconciliation pour un candidat."""

    kind: str  # confirmed | superseded | new | needs_review
    fact: Fact
    old_fact: Fact | None = None


@dataclass
class _ArbiterVerdict:
    """Verdict du LLM arbitre sur un match partiel."""

    kind: str  # "same_as" | "contradicts" | "new"
    target_fact_id: str | None
    notes: str = ""


def _initial_confidence(source: str) -> float:
    if source == "explicit":
        return CONFIDENCE_EXPLICIT
    if source == "correction":
        return CONFIDENCE_CORRECTION
    return CONFIDENCE_INFERENCE


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
_VALID_VERDICTS = {"same_as", "contradicts", "new"}


def _parse_arbiter_verdict(raw: str) -> _ArbiterVerdict:
    """Parse JSON arbitre. Tout doute → "new" (refus prudent du faux positif)."""
    candidate = raw.strip()
    fence = _CODE_FENCE_RE.search(candidate)
    if fence:
        candidate = fence.group(1)
    match = _JSON_OBJ_RE.search(candidate)
    if not match:
        return _ArbiterVerdict(kind="new", target_fact_id=None, notes="no JSON in arbiter output")
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return _ArbiterVerdict(kind="new", target_fact_id=None, notes=f"parse error: {exc}")
    if not isinstance(data, dict):
        return _ArbiterVerdict(kind="new", target_fact_id=None, notes="not a dict")
    verdict = data.get("verdict", "new")
    if verdict not in _VALID_VERDICTS:
        return _ArbiterVerdict(kind="new", target_fact_id=None, notes="invalid verdict value")
    target = data.get("target_fact_id")
    if target is not None and not isinstance(target, str):
        target = None
    return _ArbiterVerdict(
        kind=verdict,
        target_fact_id=target,
        notes=str(data.get("notes", ""))[:200],
    )


def _parse_extract_response(raw: str) -> list[_Candidate]:
    """Tolère ```json ... ``` autour et extrait la liste `facts`."""
    candidate = raw.strip()
    fence = _CODE_FENCE_RE.search(candidate)
    if fence:
        candidate = fence.group(1)
    match = _JSON_OBJ_RE.search(candidate)
    if not match:
        logger.debug("Ingest: extraction LLM sans JSON", preview=raw[:120])
        return []
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        logger.debug("Ingest: JSON parse error", error=str(exc), preview=raw[:120])
        return []
    if not isinstance(data, dict):
        return []
    raw_facts = data.get("facts", [])
    if not isinstance(raw_facts, list):
        return []
    out: list[_Candidate] = []
    for item in raw_facts[:5]:
        if not isinstance(item, dict):
            continue
        subj = item.get("subject")
        pred = item.get("predicate")
        obj = item.get("object")
        cat = item.get("category")
        if not all(isinstance(x, str) and x.strip() for x in (subj, pred, obj, cat)):
            continue
        imp_raw = item.get("importance", 0.5)
        try:
            imp = float(imp_raw)
        except (TypeError, ValueError):
            imp = 0.5
        out.append(
            _Candidate(
                subject=subj,
                predicate=pred,
                object=obj,
                category=cat,
                confidence_source=str(item.get("confidence_source", "inference")),
                importance=imp,
            )
        )
    return out
