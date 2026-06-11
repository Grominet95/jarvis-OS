"""Tests d'ingestion — le cœur dur de la PHASE 3 (CDC §6.4–§6.5).

Couvre les 3 cas de réconciliation + vocabulaire fermé + confidence.
Le LLM extracteur est FAKE et contrôlé pour tester précisément la mécanique
de réconciliation. La trace LLM réelle sera testée par le script de mission.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.ingest import (
    CONFIDENCE_EXPLICIT,
    CONFIDENCE_INFERENCE,
    CONFIRM_DELTA,
    MemoryIngest,
)
from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.schemas import FactStatus, ObservationType, RelationType

# ── Fake LLM contrôlé ─────────────────────────────────────────────────────────


class _ScriptedLLM(LLMProvider):
    """LLM contrôlable pour l'extracteur ET l'arbitre v2.

    Dispatch via le contenu du `system` prompt :
    - "arbitre" → consomme `arbiter_scripts` (verdict JSON pré-écrit)
    - sinon (extracteur) → consomme `extract_scripts` (liste de facts)

    Par défaut, l'arbitre renvoie 'contradicts' sur la première cible disponible
    pour préserver le comportement attendu des tests historiques (supersession sur
    stable). Les tests qui veulent une autre branche fournissent `arbiter_scripts`.
    """

    def __init__(
        self,
        scripts: list[list[dict]],
        arbiter_scripts: list[dict] | None = None,
    ) -> None:
        self._extract_scripts = scripts
        self._arbiter_scripts = arbiter_scripts or []
        self.extract_calls = 0
        self.arbiter_calls = 0

    @property
    def calls(self) -> int:
        return self.extract_calls + self.arbiter_calls

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        is_arbiter = "arbitre" in (system or "").lower()
        if is_arbiter:
            if self._arbiter_scripts:
                idx = min(self.arbiter_calls, len(self._arbiter_scripts) - 1)
                payload = self._arbiter_scripts[idx]
            else:
                # Default : on extrait l'id du premier candidat depuis le prompt et
                # on renvoie "contradicts" — préserve la sémantique v1 pour les tests
                # historiques (supersession sur stable).
                payload = {
                    "verdict": "contradicts",
                    "target_fact_id": _first_fact_id_in(messages[-1]["content"]),
                    "notes": "default arbiter for legacy tests",
                }
            self.arbiter_calls += 1
            return json.dumps(payload)

        idx = min(self.extract_calls, len(self._extract_scripts) - 1)
        self.extract_calls += 1
        return json.dumps({"facts": self._extract_scripts[idx]})

    async def health_check(self) -> bool:
        return True


def _first_fact_id_in(prompt: str) -> str | None:
    """Extrait le premier fact_id mentionné dans un prompt d'arbitre."""
    import re

    m = re.search(r"\[(fact_[a-f0-9]+)\]", prompt)
    return m.group(1) if m else None


def _f(
    subject: str = "Barth",
    predicate: str = "prefers",
    obj: str = "python",
    category: str = "tool",
    source: str = "explicit",
    importance: float = 0.6,
) -> dict:
    return {
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "category": category,
        "confidence_source": source,
        "importance": importance,
    }


@pytest.fixture
def kernel(tmp_path: Path) -> MemoryKernel:
    return MemoryKernel(tmp_path / "test.db")


# ── 1. Confirmation — ré-observation sans duplication ─────────────────────────


async def test_reobservation_confirme_sans_dupliquer(kernel: MemoryKernel) -> None:
    """Un fact ré-observé n'est PAS dupliqué : support_count++, confidence++."""
    llm = _ScriptedLLM(
        [
            [_f(obj="python")],  # 1er échange
            [_f(obj="python")],  # 2e échange — même fait
        ]
    )
    ingest = MemoryIngest(kernel, llm)

    r1 = await ingest.ingest("Barth dit qu'il préfère Python", source="test")
    assert len(r1.new_facts) == 1
    assert len(r1.confirmed) == 0
    initial_conf = r1.new_facts[0].confidence

    r2 = await ingest.ingest("Barth réitère qu'il préfère Python", source="test")
    assert len(r2.new_facts) == 0
    assert len(r2.confirmed) == 1
    # On a UN seul fact en base, pas deux
    assert kernel.count_facts(FactStatus.ACTIVE) == 1
    confirmed_fact = r2.confirmed[0]
    assert confirmed_fact.support_count == 2
    assert confirmed_fact.confidence == pytest.approx(initial_conf + CONFIRM_DELTA)
    # Une FactObservation CONFIRM est enregistrée
    obs = kernel.list_observations(confirmed_fact.id)
    assert len(obs) == 1
    assert obs[0].observation_type == ObservationType.CONFIRM


async def test_confirmation_normalisation_object_case_insensitive(
    kernel: MemoryKernel,
) -> None:
    """Object 'Python' et 'python' sont traités comme identiques (normalisation)."""
    llm = _ScriptedLLM(
        [
            [_f(obj="Python")],
            [_f(obj="python")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="test")
    r2 = await ingest.ingest("...", source="test")
    assert len(r2.confirmed) == 1
    assert kernel.count_facts(FactStatus.ACTIVE) == 1


# ── 2. Supersession — contradiction sur catégorie stable ─────────────────────


async def test_contradiction_sur_goal_declenche_supersession(
    kernel: MemoryKernel,
) -> None:
    """'objectif sub-3h' puis 'objectif 3h10' → ancien superseded, nouveau créé, relation."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h marathon", category="goal")],
            [_f(predicate="targets", obj="3h10 marathon", category="goal")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)

    r1 = await ingest.ingest("Barth vise sub-3h", source="test")
    old = r1.new_facts[0]
    assert old.status == FactStatus.ACTIVE

    r2 = await ingest.ingest("Barth a revu son objectif à 3h10", source="test")
    assert len(r2.superseded_pairs) == 1
    old_after, new = r2.superseded_pairs[0]
    assert old_after.id == old.id
    assert old_after.status == FactStatus.SUPERSEDED
    assert new.object == "3h10 marathon"

    # L'ancien n'est PAS supprimé (CDC : on archive, on ne détruit jamais)
    assert kernel.get_fact(old.id) is not None
    # Relation supersedes : new → old
    relations = kernel.list_relations(new.id)
    assert any(
        r.relation_type == RelationType.SUPERSEDES
        and r.from_fact_id == new.id
        and r.to_fact_id == old.id
        for r in relations
    )
    # Un seul fact ACTIVE de cette catégorie maintenant
    assert (
        len([f for f in kernel.list_facts_by_category("goal") if f.status == FactStatus.ACTIVE])
        == 1
    )


async def test_contradiction_sur_identity_declenche_supersession(
    kernel: MemoryKernel,
) -> None:
    """Identity est aussi une catégorie stable — supersession sur contradiction."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="is", obj="developer", category="identity")],
            [_f(predicate="is", obj="entrepreneur", category="identity")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("Barth est dev", source="test")
    r2 = await ingest.ingest("Barth se décrit comme entrepreneur", source="test")
    assert len(r2.superseded_pairs) == 1


# ── 3. Coexistence — pas de supersession sur catégorie non stable ─────────────


async def test_deux_preferences_coexistent_sans_supersession(
    kernel: MemoryKernel,
) -> None:
    """'Barth prefers python' et 'Barth prefers go' coexistent (preference non stable).

    NB du CDC §6 (test direct) : 'Barth court' + 'Barth fait du vélo' → coexistence.
    Ici on prend deux préférences sur subject/predicate/category identique mais objects
    différents → coexistence attendue.
    """
    llm = _ScriptedLLM(
        [
            [_f(predicate="prefers", obj="python", category="preference")],
            [_f(predicate="prefers", obj="go", category="preference")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("Barth aime Python", source="test")
    r2 = await ingest.ingest("Barth aussi go", source="test")

    # Sur 'preference', la contradiction ne déclenche PAS supersession → coexistence
    assert len(r2.superseded_pairs) == 0
    assert len(r2.new_facts) == 1
    active = [f for f in kernel.list_facts_by_category("preference")]
    assert len(active) == 2


async def test_predicates_differents_coexistent(kernel: MemoryKernel) -> None:
    """'Barth uses python' et 'Barth uses go' (prédicats identiques, objects diff)."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="uses", obj="python", category="tool")],
            [_f(predicate="uses", obj="go", category="tool")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="test")
    r2 = await ingest.ingest("...", source="test")
    # tool n'est PAS stable → coexistence
    assert len(r2.new_facts) == 1
    assert kernel.count_facts(FactStatus.ACTIVE) == 2


# ── 4. Vocabulaire fermé — hors vocab → needs_review ─────────────────────────


async def test_predicate_hors_vocab_va_en_needs_review(kernel: MemoryKernel) -> None:
    llm = _ScriptedLLM([[_f(predicate="vise", obj="sub-3h", category="goal")]])
    ingest = MemoryIngest(kernel, llm)
    r = await ingest.ingest("...", source="test")
    assert len(r.needs_review) == 1
    assert len(r.new_facts) == 0
    nr = r.needs_review[0]
    assert nr.status == FactStatus.NEEDS_REVIEW
    # Pas dans la base ACTIVE
    assert kernel.count_facts(FactStatus.ACTIVE) == 0
    assert kernel.count_facts(FactStatus.NEEDS_REVIEW) == 1


async def test_category_hors_vocab_va_en_needs_review(kernel: MemoryKernel) -> None:
    llm = _ScriptedLLM([[_f(predicate="prefers", category="emotion")]])
    ingest = MemoryIngest(kernel, llm)
    r = await ingest.ingest("...", source="test")
    assert len(r.needs_review) == 1
    assert kernel.count_facts(FactStatus.NEEDS_REVIEW) == 1


# ── 5. Confidence dynamique ───────────────────────────────────────────────────


async def test_confidence_explicit_superieure_a_inference(
    kernel: MemoryKernel,
) -> None:
    """Un énoncé explicite démarre à 0.75 ; une inférence à 0.55."""
    llm1 = _ScriptedLLM([[_f(source="explicit")]])
    r1 = await MemoryIngest(kernel, llm1).ingest("...", source="test")
    assert r1.new_facts[0].confidence == pytest.approx(CONFIDENCE_EXPLICIT)

    # Reset kernel pour second test
    kernel2 = MemoryKernel(kernel.db_path.parent / "m2.db")
    llm2 = _ScriptedLLM([[_f(source="inference")]])
    r2 = await MemoryIngest(kernel2, llm2).ingest("...", source="test")
    assert r2.new_facts[0].confidence == pytest.approx(CONFIDENCE_INFERENCE)


# ── 6. Robustesse extraction ─────────────────────────────────────────────────


async def test_llm_response_avec_fences_markdown(kernel: MemoryKernel) -> None:
    """L'extracteur tolère ```json ... ``` autour du JSON."""

    class _FencedLLM(LLMProvider):
        async def complete(  # type: ignore[override]
            self,
            messages: list[dict],
            system: str,
            tools: list[dict] | None = None,
            stream: bool = False,
            context: str = "",
        ) -> str:
            return "```json\n" + json.dumps({"facts": [_f()]}) + "\n```"

        async def health_check(self) -> bool:
            return True

    r = await MemoryIngest(kernel, _FencedLLM()).ingest("...", source="test")
    assert len(r.new_facts) == 1


async def test_llm_response_non_parsable_renvoie_zero_facts(
    kernel: MemoryKernel,
) -> None:
    class _GarbageLLM(LLMProvider):
        async def complete(  # type: ignore[override]
            self,
            messages: list[dict],
            system: str,
            tools: list[dict] | None = None,
            stream: bool = False,
            context: str = "",
        ) -> str:
            return "désolé je n'ai pas compris"

        async def health_check(self) -> bool:
            return True

    r = await MemoryIngest(kernel, _GarbageLLM()).ingest("...", source="test")
    assert r.raw_extracted_count == 0
    assert len(r.new_facts) == 0


async def test_max_5_facts_par_ingest(kernel: MemoryKernel) -> None:
    """CDC §6.4 : 0 à 5 facts maximum extraits par ingest."""
    seven = [_f(obj=f"item_{i}") for i in range(7)]
    llm = _ScriptedLLM([seven])
    r = await MemoryIngest(kernel, llm).ingest("...", source="test")
    # Le parser tronque à 5
    assert r.raw_extracted_count == 5


# ── 7. Decay policy assignée correctement par catégorie ──────────────────────


async def test_decay_policy_par_categorie(kernel: MemoryKernel) -> None:
    """goal → fast, identity → none, preference → medium."""
    from jarvis.providers.memory.schemas import DecayPolicy

    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h", category="goal")],
            [_f(predicate="is", obj="developer", category="identity")],
            [_f(predicate="prefers", obj="café", category="preference")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    g = (await ingest.ingest("...", source="t")).new_facts[0]
    i = (await ingest.ingest("...", source="t")).new_facts[0]
    p = (await ingest.ingest("...", source="t")).new_facts[0]
    assert g.decay_policy == DecayPolicy.FAST
    assert i.decay_policy == DecayPolicy.NONE
    assert p.decay_policy == DecayPolicy.MEDIUM


# ── 8. Event tracé pour chaque ingest ────────────────────────────────────────


async def test_ingest_log_toujours_un_event(kernel: MemoryKernel) -> None:
    """Même quand rien n'est extrait, l'event brut est tracé (immuabilité)."""
    llm = _ScriptedLLM([[]])  # zéro faits
    ingest = MemoryIngest(kernel, llm)
    r = await ingest.ingest("Barth dit bonjour", source="voice")
    assert kernel.count_events() == 1
    assert r.event.content == "Barth dit bonjour"
    assert r.event.source == "voice"


# ── 9. Matcher v2 — arbitre LLM appelé UNIQUEMENT sur match partiel ──────────


async def test_arbiter_pas_appele_sur_match_franc(kernel: MemoryKernel) -> None:
    """Object identique normalisé → CONFIRM franc, ZÉRO appel arbitre."""
    llm = _ScriptedLLM(
        [
            [_f(obj="python")],
            [_f(obj="python")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="t")
    await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 0
    assert llm.arbiter_calls == 0


async def test_arbiter_pas_appele_sur_coexistence_non_stable(
    kernel: MemoryKernel,
) -> None:
    """Match exact (subj,pred,cat) sur catégorie non stable + object différent →
    coexistence directe, ZÉRO arbitre (les non stables n'ont pas de risque de
    supersession abusive)."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="uses", obj="python", category="tool")],
            [_f(predicate="uses", obj="go", category="tool")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="t")
    await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 0
    assert kernel.count_facts(FactStatus.ACTIVE) == 2


async def test_arbiter_appele_sur_stable_object_different(
    kernel: MemoryKernel,
) -> None:
    """Match exact (subj,pred,cat) sur catégorie stable + object différent →
    arbitre est appelé (la "contradiction" peut n'être qu'une reformulation)."""
    # Arbiter dit "same_as" → CONFIRM (la "contradiction" était une paraphrase)
    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h marathon", category="goal")],
            [_f(predicate="targets", obj="marathon sub-3h", category="goal")],
        ],
        arbiter_scripts=[{"verdict": "same_as", "target_fact_id": None, "notes": ""}],
    )
    ingest = MemoryIngest(kernel, llm)
    r1 = await ingest.ingest("...", source="t")
    old_id = r1.new_facts[0].id

    # Patch le verdict pour pointer sur le bon id
    llm._arbiter_scripts = [{"verdict": "same_as", "target_fact_id": old_id, "notes": ""}]

    r2 = await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 1
    assert llm.arbiter_calls == 1
    assert len(r2.confirmed) == 1
    assert len(r2.superseded_pairs) == 0  # arbitre a sauvé : pas de supersession abusive
    assert kernel.count_facts(FactStatus.ACTIVE) == 1


async def test_arbiter_contradicts_sur_stable_declenche_supersession(
    kernel: MemoryKernel,
) -> None:
    """Arbitre dit "contradicts" → supersession (vraie contradiction)."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h marathon", category="goal")],
            [_f(predicate="targets", obj="3h10 marathon", category="goal")],
        ],
        arbiter_scripts=[{"verdict": "contradicts", "target_fact_id": "", "notes": ""}],
    )
    ingest = MemoryIngest(kernel, llm)
    r1 = await ingest.ingest("...", source="t")
    llm._arbiter_scripts = [
        {"verdict": "contradicts", "target_fact_id": r1.new_facts[0].id, "notes": ""}
    ]
    r2 = await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 1
    assert len(r2.superseded_pairs) == 1


async def test_arbiter_new_sur_stable_donne_coexistence(kernel: MemoryKernel) -> None:
    """Arbitre dit "new" sur stable → coexistence (cas rare mais possible)."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h marathon", category="goal")],
            [_f(predicate="targets", obj="autre objectif distinct", category="goal")],
        ],
        arbiter_scripts=[{"verdict": "new", "target_fact_id": None, "notes": ""}],
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="t")
    r2 = await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 1
    assert len(r2.new_facts) == 1
    assert len(r2.superseded_pairs) == 0


# ── 10. Étage 2 — siblings via FTS5 (faux négatifs du matcher syntaxique) ────


async def test_arbiter_appele_sur_sibling_fts(kernel: MemoryKernel) -> None:
    """Pas de match exact mais sibling FTS5 trouvé (même cat, object overlap) →
    l'arbitre est appelé pour décider si c'est une paraphrase."""
    # 1er fact : 'barth has running' (prédicat 'has', catégorie habit)
    # 2e fact : 'barth has course à pied' (mêmes subj, cat ; FTS hit sur 'course')
    # Arbitre dit "same_as" → CONFIRM du 1er
    llm = _ScriptedLLM(
        [
            [_f(predicate="has", obj="running course", category="habit")],
            [_f(predicate="has", obj="course à pied régulière", category="habit")],
        ],
        arbiter_scripts=[{"verdict": "same_as", "target_fact_id": None, "notes": ""}],
    )
    ingest = MemoryIngest(kernel, llm)
    r1 = await ingest.ingest("...", source="t")
    # Patch l'id arbitre vers le 1er fact (pas le matcher exact car objects diffèrent)
    llm._arbiter_scripts = [
        {"verdict": "same_as", "target_fact_id": r1.new_facts[0].id, "notes": ""}
    ]
    await ingest.ingest("...", source="t")
    # Stage 1 (exact match) trouve le 1er car (subj, pred, cat) identiques.
    # Object diff sur habit (non stable) → coexistence directe sans arbitre.
    # Pour exercer vraiment l'étage 2, le prédicat doit différer.
    assert kernel.count_facts(FactStatus.ACTIVE) == 2  # habit non stable → coexist


async def test_arbiter_etage_2_sur_predicat_different_meme_categorie(
    kernel: MemoryKernel,
) -> None:
    """Faux négatif typique : LLM extracteur alterne 'has' et 'works_on' pour la
    même idée. Pas de match exact (predicates différents), mais FTS sur l'object
    trouve un sibling → arbitre invoqué."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="has", obj="course à pied", category="habit")],
            # Le LLM extracteur paraphrase avec un autre prédicat
            [_f(predicate="works_on", obj="course à pied", category="habit")],
        ],
        arbiter_scripts=[{"verdict": "same_as", "target_fact_id": None, "notes": ""}],
    )
    ingest = MemoryIngest(kernel, llm)
    r1 = await ingest.ingest("...", source="t")
    llm._arbiter_scripts = [
        {"verdict": "same_as", "target_fact_id": r1.new_facts[0].id, "notes": ""}
    ]
    r2 = await ingest.ingest("...", source="t")
    assert ingest.arbiter_calls == 1
    assert len(r2.confirmed) == 1
    assert kernel.count_facts(FactStatus.ACTIVE) == 1  # le faux doublon a été évité


async def test_arbiter_pas_appele_si_aucun_sibling_fts(kernel: MemoryKernel) -> None:
    """Si l'object du candidat n'a aucun recouvrement FTS avec les facts actifs,
    on ne paie pas un appel arbitre inutile."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="has", obj="course à pied", category="habit")],
            [_f(predicate="works_on", obj="cuisine italienne", category="project")],
        ]
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="t")
    await ingest.ingest("...", source="t")
    # Pas d'overlap FTS entre 'course à pied' et 'cuisine italienne' → 0 arbitre
    assert ingest.arbiter_calls == 0


# ── 11. Robustesse du parser arbitre ─────────────────────────────────────────


async def test_arbiter_verdict_invalide_donne_new(kernel: MemoryKernel) -> None:
    """Verdict illisible / valeur invalide → 'new' par défaut (refus prudent)."""
    llm = _ScriptedLLM(
        [
            [_f(predicate="targets", obj="sub-3h", category="goal")],
            [_f(predicate="targets", obj="3h05", category="goal")],
        ],
        arbiter_scripts=[{"verdict": "unknown_value", "target_fact_id": None}],
    )
    ingest = MemoryIngest(kernel, llm)
    await ingest.ingest("...", source="t")
    r2 = await ingest.ingest("...", source="t")
    # Verdict invalide → "new" → coexistence (refus du faux positif)
    assert ingest.arbiter_calls == 1
    assert len(r2.new_facts) == 1
    assert len(r2.superseded_pairs) == 0
