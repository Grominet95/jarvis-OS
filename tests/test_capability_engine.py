"""Tests du CapabilityEngine (CDC §8) — détection + délégation + sécurité.

Les cas négatifs (jamais d'auto-install, INSTALL_PACKAGE bloqué) sont
prioritaires : c'est eux qui prouvent que la phase la plus dangereuse du
projet (auto-extension) ne contourne pas les garde-fous.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.capabilities.skills.lab import SkillLab
from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillStatus
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
from jarvis.engine.mission.capability_engine import (
    CapabilityEngine,
    ResolutionKind,
    Whitelist,
    WhitelistDomain,
    _jaccard,
    _looks_dangerous,
    _tokenize,
)
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.kernel import MemoryKernel

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeLLM(LLMProvider):
    """Renvoie un SKILL.md valide pour les tests du Lab."""

    def __init__(self, skill_md: str) -> None:
        self._md = skill_md

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        return self._md

    async def health_check(self) -> bool:
        return True


class _FakeSkillRegistry:
    """Faux registry — list_installed renvoie une liste configurable."""

    def __init__(self, installed: list[dict] | None = None) -> None:
        self._installed = installed or []

    def list_installed(self) -> list[dict]:
        return self._installed


class _FakeToolRegistry:
    """Faux tool registry — schemas() renvoie une liste configurable."""

    def __init__(self, schemas: list[dict] | None = None) -> None:
        self._schemas = schemas or []

    def schemas(self) -> list[dict]:
        return self._schemas


_VALID_SKILL_MD = """\
---
name: test-capability-skill
description: Skill de test pour le capability engine.
license: MIT
metadata:
  author: jarvis-synthesizer
  version: "1.0"
  tags: [test, capability]
---

# Test Capability

Instructions de test pour vérifier le pipeline.
"""


def _make_engine(
    tmp_path: Path,
    installed_skills: list[dict] | None = None,
    available_tools: list[dict] | None = None,
    whitelist: Whitelist | None = None,
    auto_install: bool = False,
    skill_md: str = _VALID_SKILL_MD,
) -> tuple[CapabilityEngine, MemoryKernel, SkillLifecycle, Path]:
    """Construit un engine + fakes.

    Renvoie (engine, kernel, lifecycle, installed_dir).
    """
    db_path = tmp_path / "memory.db"
    cand_dir = tmp_path / "candidates"
    installed_dir = tmp_path / "installed"
    llm = _FakeLLM(skill_md=skill_md)
    synth = SkillSynthesizer(llm=llm)
    kernel = MemoryKernel(db_path)
    lifecycle = SkillLifecycle(db_path=db_path)
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=cand_dir,
        installed_dir=installed_dir,
    )
    engine = CapabilityEngine(
        kernel=kernel,
        lab=lab,
        skill_registry=_FakeSkillRegistry(installed_skills),
        tool_registry=_FakeToolRegistry(available_tools),
        whitelist=whitelist,
        auto_install_enabled=auto_install,
    )
    return engine, kernel, lifecycle, installed_dir


# ── 1. Helpers (tokenize, jaccard, dangerous) ────────────────────────────────


def test_tokenize_ignore_stop_words() -> None:
    tokens = _tokenize("Je veux transcrire un fichier audio en texte")
    # "je", "un", "en" sont stop-words → exclus
    assert "transcrire" in tokens
    assert "fichier" in tokens
    assert "audio" in tokens
    assert "texte" in tokens
    assert "je" not in tokens
    assert "un" not in tokens


def test_jaccard_score() -> None:
    assert _jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0
    assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert _jaccard({"a", "b", "c"}, {"a", "b", "d"}) == pytest.approx(0.5)


def test_looks_dangerous_install_package() -> None:
    """Pré-filtre dangereux : variants courants détectés."""
    assert _looks_dangerous("pip install requests")
    assert _looks_dangerous("npm install left-pad")
    assert _looks_dangerous("Installer un paquet pour faire X")
    assert _looks_dangerous("install a new library")
    assert _looks_dangerous("modifier le core de Jarvis")
    assert _looks_dangerous("sudo apt update")

    # Non-dangereux
    assert not _looks_dangerous("transcrire un fichier audio")
    assert not _looks_dangerous("envoyer un email")


# ── 2. Matching d'une skill existante ────────────────────────────────────────


async def test_match_existing_skill_evite_le_lab(tmp_path: Path) -> None:
    """Si une skill installée matche, on N'APPELLE PAS le Lab."""
    installed = [
        {
            "name": "weather",
            "label": "Météo",
            "description": "Affichage et prévision météo immersive",
            "tags": ["météo", "climat", "prévisions"],
        }
    ]
    engine, kernel, lifecycle, _ = _make_engine(tmp_path, installed_skills=installed)

    resolution = await engine.detect_and_propose(
        description="Je veux afficher la météo et les prévisions pour demain"
    )

    assert resolution.kind == ResolutionKind.EXISTING_SKILL
    assert resolution.target_name == "weather"
    # CRITIQUE : aucune candidate créée dans le lifecycle
    assert len(lifecycle.list_all()) == 0
    # L'event est tracé
    assert kernel.count_events() == 1


async def test_match_existing_tool_evite_le_lab(tmp_path: Path) -> None:
    """Si un tool natif matche, on N'APPELLE PAS le Lab."""
    available_tools = [
        {
            "name": "weather_tool",
            "description": "Récupère les données météo via Open-Meteo",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    engine, _, lifecycle, _ = _make_engine(tmp_path, available_tools=available_tools)

    resolution = await engine.detect_and_propose(
        description="Je veux récupérer les données météo actuelles"
    )

    assert resolution.kind == ResolutionKind.EXISTING_TOOL
    assert resolution.target_name == "weather_tool"
    assert len(lifecycle.list_all()) == 0


# ── 3. Délégation au Lab — nouvelle candidate ────────────────────────────────


async def test_nouvelle_candidate_delegue_au_lab(tmp_path: Path) -> None:
    """Aucun existant → délègue au Lab → SANDBOXED_PASS (PHASE 5 MVP)."""
    engine, kernel, lifecycle, installed_dir = _make_engine(tmp_path)

    resolution = await engine.detect_and_propose(
        description="Calculer la position des planètes pour une date donnée",
        example_input="2026-06-08T12:00:00",
    )

    assert resolution.kind == ResolutionKind.NEW_CANDIDATE
    assert resolution.target_name == "test-capability-skill"
    assert resolution.candidate_record is not None
    assert resolution.candidate_record.status == SkillStatus.SANDBOXED_PASS

    # CRITIQUE : la candidate est en zone tampon, PAS dans installed/
    assert not installed_dir.exists() or not (installed_dir / "test-capability-skill").exists()
    # Lifecycle reflète SANDBOXED_PASS
    record = lifecycle.get("test-capability-skill")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_PASS


# ── 4. CRITIQUE : JAMAIS d'auto-installation en MVP ──────────────────────────


async def test_jamais_auto_install_meme_avec_whitelist_match(tmp_path: Path) -> None:
    """Même si une whitelist matche ET sandbox vert ET flag ON, AUCUNE
    auto-installation en PHASE 5 MVP. La candidate reste en SANDBOXED_PASS,
    attendant promote() humain."""
    whitelist = Whitelist(
        domains=[
            WhitelistDomain(
                name="astro",
                max_access_level="WRITE_LOCAL",
                allowed_categories=["agent_mission"],
                description_must_contain=["planètes", "astre", "astro"],
            )
        ]
    )
    engine, _, lifecycle, installed_dir = _make_engine(
        tmp_path,
        whitelist=whitelist,
        # Même avec le flag ON — censé être inerte en MVP
        auto_install=True,
    )

    resolution = await engine.detect_and_propose(
        description="Calculer la position des planètes pour une date donnée"
    )

    # Le sandbox passe vert
    assert resolution.kind == ResolutionKind.NEW_CANDIDATE
    assert resolution.candidate_record.status == SkillStatus.SANDBOXED_PASS

    # CRITIQUE CDC §8 : ZÉRO installation, même avec flag ON + whitelist match
    assert not installed_dir.exists() or not any(installed_dir.iterdir())
    record = lifecycle.get("test-capability-skill")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_PASS  # PAS ACTIVE
    assert record.promoted_at is None  # JAMAIS promu auto


async def test_meme_avec_flag_off_aucune_auto_install(tmp_path: Path) -> None:
    """Flag OFF (défaut) : strictement aucune auto-install. Comportement par défaut."""
    engine, _, lifecycle, installed_dir = _make_engine(tmp_path, auto_install=False)

    resolution = await engine.detect_and_propose(
        description="Convertir un fichier CSV en JSON structuré"
    )

    assert resolution.kind == ResolutionKind.NEW_CANDIDATE
    record = lifecycle.get("test-capability-skill")
    assert record.status == SkillStatus.SANDBOXED_PASS  # attente humain
    assert not installed_dir.exists() or not any(installed_dir.iterdir())


# ── 5. CRITIQUE SÉCURITÉ : INSTALL_PACKAGE / MODIFY_CORE refusés ────────────


@pytest.mark.parametrize(
    "dangerous_request",
    [
        "Installer le paquet requests pour faire des appels HTTP",
        "pip install pandas pour manipuler des données",
        "installer une nouvelle library Python",
        "Modifier le runtime de Jarvis pour ajouter un hook",
        "sudo apt install ffmpeg",
        "Je voudrais install a new package called numpy",
        "Modifier le core pour exposer un nouvel endpoint",
    ],
)
async def test_install_package_modify_core_refuse_avant_generation(
    tmp_path: Path, dangerous_request: str
) -> None:
    """CRITIQUE CDC §8 : ne JAMAIS générer une skill qui demande INSTALL_PACKAGE
    ou MODIFY_CORE. Refus avant même d'appeler le Lab (économie LLM + signal)."""
    engine, kernel, lifecycle, installed_dir = _make_engine(tmp_path)

    resolution = await engine.detect_and_propose(description=dangerous_request)

    assert resolution.kind == ResolutionKind.BLOCKED_DANGEROUS
    # CRITIQUE : zéro candidate générée, zéro install
    assert len(lifecycle.list_all()) == 0
    assert not installed_dir.exists() or not any(installed_dir.iterdir())
    # Event tracé pour audit
    assert kernel.count_events() == 1
    with sqlite3.connect(kernel.db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM events WHERE type='capability_gap_recorded'"
        ).fetchone()
    assert row is not None
    import json

    meta = json.loads(row[0])
    assert meta["resolution_kind"] == "blocked_dangerous"


# ── 6. Lab échoue (LLM down) ─────────────────────────────────────────────────


async def test_lab_echec_renvoie_lab_failed(tmp_path: Path) -> None:
    """Si le Lab retourne None (synthèse foireuse), on signale LAB_FAILED."""
    # SKILL.md sans 'name' valide → synthesizer.propose_skill_candidate lève ValueError
    bad_md = "---\ndescription: pas de name kebab-case\n---\n"
    engine, _, lifecycle, _ = _make_engine(tmp_path, skill_md=bad_md)

    resolution = await engine.detect_and_propose(
        description="Faire une chose normale qui ne déclenche pas le filtre dangereux"
    )

    assert resolution.kind == ResolutionKind.LAB_FAILED
    assert len(lifecycle.list_all()) == 0  # rien dans le lifecycle


# ── 7. Sandbox rejette la candidate ──────────────────────────────────────────


async def test_sandbox_rejette_renvoie_sandbox_rejected(tmp_path: Path) -> None:
    """Si la candidate générée échoue le sandbox, on renvoie SANDBOX_REJECTED."""
    engine, _, lifecycle, installed_dir = _make_engine(tmp_path)
    # Corromp le générateur pour produire un skill.py qui crash à l'import
    engine._lab._synthesizer._generate_skill_py = lambda name: (  # noqa: ARG005
        "raise RuntimeError('skill volontairement cassée — test PHASE 5')\n"
    )

    resolution = await engine.detect_and_propose(description="Convertir un format XML obscur")

    assert resolution.kind == ResolutionKind.SANDBOX_REJECTED
    record = lifecycle.get("test-capability-skill")
    assert record.status == SkillStatus.SANDBOXED_FAIL
    # CRITIQUE : zéro install même en cas d'erreur (pas de fallback "tant pis")
    assert not installed_dir.exists() or not any(installed_dir.iterdir())


# ── 8. Event capability_gap_recorded tracé dans le Kernel ────────────────────


async def test_event_capability_gap_recorded_dans_kernel(tmp_path: Path) -> None:
    """Toute résolution trace un Event dans le Kernel pour audit + pipeline ingest."""
    engine, kernel, _, _ = _make_engine(tmp_path)

    resolution = await engine.detect_and_propose(description="Tester l'enregistrement event")

    assert resolution.event_id is not None
    evt = kernel.get_event(resolution.event_id)
    assert evt is not None
    assert evt.type == "capability_gap_recorded"
    assert evt.source == "capability_engine"
    import json

    meta = json.loads(evt.metadata_json)
    assert "description" in meta
    assert "resolution_kind" in meta


# ── 9. Whitelist load ────────────────────────────────────────────────────────


def test_whitelist_load_fichier_inexistant() -> None:
    """Whitelist.load tolère l'absence du fichier."""
    wl = Whitelist.load(Path("/nonexistent/permissions.yaml"))
    assert wl.domains == []


def test_whitelist_load_fichier_vide(tmp_path: Path) -> None:
    """Fichier avec domains: [] (PHASE 5 MVP) → liste vide."""
    p = tmp_path / "permissions.yaml"
    p.write_text("domains: []\n", encoding="utf-8")
    wl = Whitelist.load(p)
    assert wl.domains == []
    # Et personne ne matche
    assert wl.matches("transcrire un fichier audio") is None


def test_whitelist_matches_si_keyword(tmp_path: Path) -> None:
    """Si un domaine est défini avec keywords, matches() renvoie le domain."""
    p = tmp_path / "permissions.yaml"
    p.write_text(
        "domains:\n"
        "  - name: audio\n"
        "    max_access_level: WRITE_LOCAL\n"
        "    description_must_contain:\n"
        "      - .ogg\n"
        "      - transcrire\n",
        encoding="utf-8",
    )
    wl = Whitelist.load(p)
    assert wl.matches("transcrire un fichier audio") is not None
    assert wl.matches("envoyer un email") is None


# ── 10. Le LLM extracteur (Lab) n'est JAMAIS appelé sur cas dangereux ─────────


async def test_install_package_court_circuit_avant_llm(tmp_path: Path) -> None:
    """CRITIQUE coût + sécurité : si la demande est dangereuse, le Lab n'est
    PAS appelé, donc le LLM n'est pas consommé pour générer du code potentiellement
    malveillant."""
    # On instrument le synthesizer pour compter les appels
    engine, _, lifecycle, _ = _make_engine(tmp_path)
    call_count = [0]
    original_complete = engine._lab._synthesizer._llm.complete

    async def counting_complete(*args: object, **kwargs: object) -> object:  # noqa: ANN401
        call_count[0] += 1
        return await original_complete(*args, **kwargs)

    engine._lab._synthesizer._llm.complete = counting_complete

    await engine.detect_and_propose(description="pip install requests please")

    assert call_count[0] == 0  # ZÉRO appel LLM sur cas dangereux
    assert len(lifecycle.list_all()) == 0
