"""Retrieval : facts actifs + score importance × récence × pertinence × confidence (§6.9).

Récupère les facts pertinents pour une query, plus les contradictions connues
(facts supersedés liés). Pas seulement des chunks vectoriels — des facts.

Pertinence : FTS5 BM25 (sqlite-vec reporté en PHASE 3.x — cf. décision Q2=c).
Decay : applique une atténuation à la `récence` selon `decay_policy`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.schemas import DecayPolicy, Fact, FactStatus, RelationType

# ── Constantes du score ──────────────────────────────────────────────────────

# Demi-vie (jours) pour le facteur de récence par DecayPolicy (§6.6).
# Une demi-vie de 7 jours signifie : la récence vaut 0.5 au bout de 7 jours.
_HALFLIFE_DAYS: dict[DecayPolicy, float] = {
    DecayPolicy.NONE: float("inf"),
    DecayPolicy.VERY_SLOW: 365.0 * 2,  # 2 ans
    DecayPolicy.SLOW: 365.0,  # 1 an
    DecayPolicy.MEDIUM: 90.0,  # 3 mois
    DecayPolicy.FAST: 14.0,  # 2 semaines
}

# Plafond pour la normalisation BM25 → [0, 1]. bm25 plus bas = plus pertinent ;
# au-delà de ce seuil, on plafonne (peu pertinent).
_BM25_CAP = 20.0


@dataclass
class ScoredFact:
    fact: Fact
    score: float
    relevance: float
    recency: float
    contradictions: list[Fact] = field(default_factory=list)


class MemoryRetrieval:
    """Récupère les facts saillants pour une query."""

    def __init__(self, kernel: MemoryKernel) -> None:
        self._kernel = kernel

    def retrieve(
        self,
        query: str,
        k: int = 5,
        now: datetime | None = None,
    ) -> list[ScoredFact]:
        """Renvoie les k facts les plus saillants pour la query.

        - Pertinence : FTS5 BM25 sur (subject + predicate + object + category).
        - Récence : decay par DecayPolicy + age (jours).
        - Score = importance × récence × pertinence × confidence.
        """
        ref = now or datetime.now()
        # On élargit la fenêtre de candidats (k*4) puis on re-score localement
        # pour intégrer les axes non-FTS (importance, récence, confidence).
        candidates = self._kernel.search_facts_fts(query, k=k * 4)
        if not candidates:
            # Pas de matching textuel : on fait un fallback léger sur les facts
            # actifs les plus récents pour ne pas renvoyer vide en cold start.
            cold = self._kernel.list_facts_by_status(FactStatus.ACTIVE, limit=k)
            candidates = [(f, 0.0) for f in cold]

        scored: list[ScoredFact] = []
        for fact, bm25 in candidates:
            if fact.status != FactStatus.ACTIVE:
                continue
            relevance = _bm25_to_relevance(bm25)
            recency = _recency_factor(fact, ref)
            total = fact.importance * recency * relevance * fact.confidence
            scored.append(
                ScoredFact(
                    fact=fact,
                    score=total,
                    relevance=relevance,
                    recency=recency,
                )
            )

        scored.sort(key=lambda s: -s.score)
        top = scored[:k]

        # Joindre les contradictions connues (facts supersedés liés)
        for sf in top:
            sf.contradictions = self._known_contradictions(sf.fact.id)
        return top

    def _known_contradictions(self, fact_id: str) -> list[Fact]:
        """Liste les facts supersedés par le fact donné (cf. §6.9 contradictions)."""
        relations = self._kernel.list_relations(fact_id)
        contradictions: list[Fact] = []
        for rel in relations:
            if rel.relation_type != RelationType.SUPERSEDES:
                continue
            if rel.from_fact_id == fact_id:
                # Ce fait supersede un autre → l'ancien est une contradiction connue
                target = self._kernel.get_fact(rel.to_fact_id)
                if target is not None:
                    contradictions.append(target)
        return contradictions


def _bm25_to_relevance(bm25: float) -> float:
    """BM25 (plus bas = mieux) → [0, 1] (plus haut = plus pertinent).

    bm25=0 (pas de match) → 0.0 (cold start handled au caller).
    bm25 négatif (typique FTS5) → ~1.0 (très pertinent).
    bm25 > _BM25_CAP → 0.0.
    """
    if bm25 == 0.0:
        return 0.0
    # FTS5 BM25 est négatif quand pertinent. On veut une fonction décroissante.
    # Score = exp(- abs(bm25) / cap) borné.
    rel = math.exp(-min(abs(bm25), _BM25_CAP) / _BM25_CAP)
    return max(0.0, min(1.0, rel))


def _recency_factor(fact: Fact, now: datetime) -> float:
    """Atténuation par âge selon DecayPolicy. NONE → toujours 1.0."""
    halflife = _HALFLIFE_DAYS.get(fact.decay_policy, 90.0)
    if halflife == float("inf"):
        return 1.0
    delta_days = max(0.0, (now - fact.last_seen_at).total_seconds() / 86400.0)
    return 0.5 ** (delta_days / halflife)
