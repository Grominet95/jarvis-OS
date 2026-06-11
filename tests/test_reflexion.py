"""Tests du Reflexion post-mission (CDC §5).

Couvre :
- Statut non terminal (PAUSED/RUNNING) → None, pas de leçon.
- Mission DONE → leçon avec what_worked non vide.
- Mission FAILED → leçon avec cause et action corrective non vides.
- skill_candidate=true → second Event 'skill_candidate_proposal' tracé.
- skill_candidate=false → pas de signal.
- Intégration avec MemoryIngest : la leçon passe par le pipeline et devient un
  Fact category=decision (cas confirmé par mock extracteur).
- Erreur LLM réflexion → None silencieux.
- JSON non parsable → None silencieux.
- Sans Kernel ni Ingest → leçon produite mais NON persistée.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.engine.mission.reflexion import Reflexion
from jarvis.engine.mission.schemas import Project, ProjectStatus, Step, StepStatus
from jarvis.engine.vocab import AccessLevel
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.ingest import MemoryIngest
from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.schemas import FactStatus

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _DualLLM(LLMProvider):
    """LLM contrôlable qui dispatche entre :
    - le prompt de Reflexion (system contient 'analyste rétrospectif') → renvoie
      le `reflect_response` du test.
    - le prompt d'extraction d'ingest (system contient 'extraction de mémoire') →
      renvoie `extract_response` (liste de facts).
    - le prompt d'arbitre (system contient 'arbitre') → renvoie verdict 'new'
      pour ne jamais déclencher confirm/supersede par défaut.
    """

    def __init__(
        self,
        reflect_response: dict | str,
        extract_response: list[dict] | None = None,
        raise_on_reflect: Exception | None = None,
    ) -> None:
        self._reflect = reflect_response
        self._extract = extract_response or []
        self._raise = raise_on_reflect
        self.reflect_calls = 0
        self.extract_calls = 0
        self.arbiter_calls = 0

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        s = (system or "").lower()
        if "rétrospectif" in s:
            self.reflect_calls += 1
            if self._raise is not None:
                raise self._raise
            if isinstance(self._reflect, str):
                return self._reflect
            return json.dumps(self._reflect)
        if "arbitre" in s:
            self.arbiter_calls += 1
            return json.dumps({"verdict": "new", "target_fact_id": None})
        # Extraction d'ingest par défaut
        self.extract_calls += 1
        return json.dumps({"facts": self._extract})

    async def health_check(self) -> bool:
        return True


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_project(
    pid: str = "proj_test",
    status: ProjectStatus = ProjectStatus.DONE,
    steps: list[Step] | None = None,
) -> Project:
    return Project(
        id=pid,
        title="Test mission",
        mission="Mission de test",
        status=status,
        steps=steps
        or [
            Step(
                id="s1",
                title="Step OK",
                description="d",
                status=StepStatus.DONE,
                success_criterion="ok",
                access_level=AccessLevel.WRITE_LOCAL,
                verified=True,
                output="Tout OK.",
            )
        ],
    )


def _make_failed_project() -> Project:
    return _make_project(
        status=ProjectStatus.FAILED,
        steps=[
            Step(
                id="s1",
                title="Step OK",
                description="d",
                status=StepStatus.DONE,
                success_criterion="ok",
                access_level=AccessLevel.WRITE_LOCAL,
                verified=True,
                output="OK",
            ),
            Step(
                id="s2",
                title="Step KO",
                description="d",
                status=StepStatus.FAILED,
                success_criterion="3 articles HTML",
                access_level=AccessLevel.WRITE_LOCAL,
                error="Vérification non concluante après 2 essais",
                verification_notes="[semantic] critère non atteint",
            ),
        ],
    )


def _lesson_dict(
    what_worked: str = "Premier step propre.",
    what_failed: str = "Second step a échoué.",
    root_cause: str = "Le LLM n'a généré que 1 article au lieu de 3.",
    corrective_action: str = "préciser la quantité attendue dans le success_criterion",
    skill_candidate: bool = False,
    skill_description: str = "",
) -> dict:
    return {
        "what_worked": what_worked,
        "what_failed": what_failed,
        "root_cause": root_cause,
        "corrective_action": corrective_action,
        "skill_candidate": skill_candidate,
        "skill_description": skill_description,
    }


@pytest.fixture
def kernel(tmp_path: Path) -> MemoryKernel:
    return MemoryKernel(tmp_path / "test.db")


# ── 1. Statut non terminal → pas de leçon ────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [ProjectStatus.PLANNING, ProjectStatus.RUNNING, ProjectStatus.PAUSED],
)
async def test_pas_de_lecon_sur_statut_non_terminal(
    kernel: MemoryKernel, status: ProjectStatus
) -> None:
    llm = _DualLLM(reflect_response=_lesson_dict())
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project(status=status)

    lesson = await reflexion.reflect(project)
    assert lesson is None
    assert llm.reflect_calls == 0  # n'a même pas tenté d'analyser
    assert kernel.count_events() == 0


# ── 2. Mission DONE → leçon avec what_worked non vide ────────────────────────


async def test_lecon_sur_succes(kernel: MemoryKernel) -> None:
    llm = _DualLLM(
        reflect_response=_lesson_dict(
            what_worked="Pipeline complet sans accroc.",
            what_failed="",
            root_cause="",
            corrective_action="",
        )
    )
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project(status=ProjectStatus.DONE)

    lesson = await reflexion.reflect(project)
    assert lesson is not None
    assert lesson.project_status == ProjectStatus.DONE
    assert lesson.what_worked  # non vide
    assert lesson.lesson_event_id  # event tracé
    assert kernel.count_events() == 1


# ── 3. Mission FAILED → leçon avec cause et action correctives non vides ─────


async def test_lecon_sur_echec_avec_cause_et_action(
    kernel: MemoryKernel,
) -> None:
    llm = _DualLLM(
        reflect_response=_lesson_dict(
            what_worked="Premier step OK.",
            what_failed="Second step a échoué (3 articles attendus, 1 produit).",
            root_cause="LLM a sous-spécifié le contenu sans relance.",
            corrective_action="ajouter un verification_command explicite par fichier",
        )
    )
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_failed_project()

    lesson = await reflexion.reflect(project)
    assert lesson is not None
    assert lesson.project_status == ProjectStatus.FAILED
    assert lesson.what_failed
    assert lesson.root_cause
    assert lesson.corrective_action  # NON VIDE — l'exigence du test CDC


# ── 4. skill_candidate=true → second Event skill_candidate_proposal ──────────


async def test_skill_candidate_emet_signal_event(kernel: MemoryKernel) -> None:
    llm = _DualLLM(
        reflect_response=_lesson_dict(
            skill_candidate=True,
            skill_description="batch_write_articles : génère N fichiers HTML "
            "d'articles à partir d'un template + une liste de sujets.",
        )
    )
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project()

    lesson = await reflexion.reflect(project)
    assert lesson is not None
    assert lesson.skill_candidate is True
    # 2 events : mission_lesson + skill_candidate_proposal
    assert kernel.count_events() == 2

    # Vérifier que le second event existe et porte la description + le pointeur
    import sqlite3

    with sqlite3.connect(kernel.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM events WHERE type=? ORDER BY created_at",
            ("skill_candidate_proposal",),
        ).fetchall()
    assert len(rows) == 1
    assert "batch_write_articles" in rows[0]["content"]
    assert rows[0]["metadata_json"] is not None
    assert "from_lesson_evt" in rows[0]["metadata_json"]


async def test_skill_candidate_false_pas_de_signal(
    kernel: MemoryKernel,
) -> None:
    llm = _DualLLM(reflect_response=_lesson_dict(skill_candidate=False))
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project()

    await reflexion.reflect(project)
    # 1 seul event : mission_lesson, pas de skill_candidate_proposal
    assert kernel.count_events() == 1


# ── 5. Intégration MemoryIngest — leçon ingérée comme fact 'decision' ────────


async def test_lecon_ingere_comme_fact_decision(kernel: MemoryKernel) -> None:
    """Pipeline complet : Reflexion → ingest.ingest() → matcher v2 → Fact decision."""
    # L'extracteur d'ingest est configuré pour reconnaître la decision dans la leçon.
    llm = _DualLLM(
        reflect_response=_lesson_dict(
            corrective_action="adopter verification_command par fichier livrable",
        ),
        extract_response=[
            {
                "subject": "jarvis",
                "predicate": "decided",
                "object": "verification_command par fichier livrable",
                "category": "decision",
                "confidence_source": "explicit",
                "importance": 0.8,
            }
        ],
    )
    ingest = MemoryIngest(kernel=kernel, llm=llm)
    reflexion = Reflexion(llm=llm, kernel=kernel, memory_ingest=ingest)

    project = _make_failed_project()
    lesson = await reflexion.reflect(project)
    assert lesson is not None

    decisions = kernel.list_facts_by_category("decision", status=FactStatus.ACTIVE)
    assert len(decisions) == 1
    fact = decisions[0]
    assert fact.subject == "jarvis"
    assert fact.predicate == "decided"
    assert "verification_command" in fact.object
    assert fact.source_event_id == lesson.lesson_event_id


# ── 6. Erreurs LLM → leçon None silencieuse ──────────────────────────────────


async def test_llm_erreur_renvoie_none(kernel: MemoryKernel) -> None:
    llm = _DualLLM(
        reflect_response={},
        raise_on_reflect=RuntimeError("LLM down"),
    )
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project()

    lesson = await reflexion.reflect(project)
    assert lesson is None
    assert kernel.count_events() == 0  # rien tracé


async def test_llm_json_non_parsable_renvoie_none(kernel: MemoryKernel) -> None:
    llm = _DualLLM(reflect_response="Désolé je ne peux pas analyser cette mission.")
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project()

    lesson = await reflexion.reflect(project)
    assert lesson is None
    assert kernel.count_events() == 0


# ── 7. Sans Kernel ni Ingest — leçon produite mais non persistée ─────────────


async def test_sans_kernel_lecon_produite_mais_non_persistee() -> None:
    llm = _DualLLM(reflect_response=_lesson_dict())
    reflexion = Reflexion(llm=llm)  # ni kernel ni ingest
    project = _make_project()

    lesson = await reflexion.reflect(project)
    assert lesson is not None  # leçon produite
    assert lesson.lesson_event_id is None  # mais pas tracée


# ── 8. Format text de la leçon contient 'jarvis decided' pour faciliter ──────
#     l'extraction d'un fact decision par l'extracteur PHASE 3.


async def test_format_text_inclut_jarvis_decided(kernel: MemoryKernel) -> None:
    llm = _DualLLM(reflect_response=_lesson_dict(corrective_action="prendre du recul avant d'agir"))
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_project()
    await reflexion.reflect(project)

    evt = kernel.list_facts_by_status(FactStatus.ACTIVE)  # pas de fact ici
    assert evt == []  # on n'a pas d'ingest, donc pas de facts
    # On lit l'event directement
    import sqlite3

    with sqlite3.connect(kernel.db_path) as conn:
        row = conn.execute("SELECT content FROM events").fetchone()
    assert row is not None
    assert "jarvis decided" in row[0]
    assert "prendre du recul avant d'agir" in row[0]


# ── 9. Métadonnées de la leçon préservées dans l'Event ────────────────────────


async def test_metadata_evt_contient_champs_lecon(kernel: MemoryKernel) -> None:
    llm = _DualLLM(
        reflect_response=_lesson_dict(
            what_worked="x",
            what_failed="y",
            skill_candidate=True,
            skill_description="my_skill",
        )
    )
    reflexion = Reflexion(llm=llm, kernel=kernel)
    project = _make_failed_project()
    await reflexion.reflect(project)

    import sqlite3

    with sqlite3.connect(kernel.db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM events WHERE type='mission_lesson'"
        ).fetchone()
    assert row is not None
    meta = json.loads(row[0])
    assert meta["project_id"] == project.id
    assert meta["project_status"] == "failed"
    assert meta["skill_candidate"] is True
    assert meta["skill_description"] == "my_skill"
    assert meta["n_steps_total"] == 2
    assert meta["n_steps_failed"] == 1
    assert meta["n_steps_done"] == 1
