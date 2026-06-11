"""Tests de la boucle d'apprentissage de skills Jarvis.

Couvre :
  - propose_skill : génère un SKILL.md valide depuis un LLM mocké
  - Le skill synthétisé devient chargeable par le SkillRegistry
  - improve_skill : met à jour SKILL.md + skill.yaml + skill.py
  - AgentSkillsAdapter.export_to_standard : produit un SKILL.md valide
  - AgentSkillsAdapter.import_from_standard : round-trip import/export
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# ── Fixtures et helpers ───────────────────────────────────────────────────────

_SAMPLE_SKILL_MD = """\
---
name: web-research
description: Recherche web multi-sources avec synthèse. Utiliser pour toute requête
  nécessitant des informations récentes.
license: MIT
metadata:
  author: jarvis-synthesizer
  version: "1.0"
  tags:
    - research
    - web
    - search
---

## Skill actif : Recherche Web

### Quand utiliser ce skill
Recherche d'informations récentes, vérification de faits, collecte de données multi-sources.

### Instructions
1. Identifier les mots-clés pertinents
2. Lancer une recherche via `browser` ou `execute_cli`
3. Synthétiser les résultats en réponse structurée
"""

_SAMPLE_TRAJECTORY: dict = {
    "task_description": "Recherche des informations sur les LLMs open-source.",
    "messages": [
        {"role": "user", "content": "Quels sont les meilleurs LLMs open-source ?"},
        {"role": "assistant", "content": "Je recherche..."},
    ],
    "tool_calls": [
        {"name": "browser", "result": "Liste des LLMs : Llama 3, Mistral, Qwen..."},
    ],
    "result": "Synthèse des meilleurs LLMs open-source en 2025.",
}


def _make_mock_llm(response: str) -> MagicMock:
    """Crée un LLMProvider mocké qui retourne `response` à chaque appel."""
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


# ── Tests SkillSynthesizer ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_propose_skill_candidate_cree_les_fichiers(tmp_path: Path) -> None:
    """propose_skill_candidate génère SKILL.md, skill.yaml et skill.py valides."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    mock_llm = _make_mock_llm(_SAMPLE_SKILL_MD)
    synth = SkillSynthesizer(llm=mock_llm)

    skill_name = await synth.propose_skill_candidate(_SAMPLE_TRAJECTORY, target_dir=tmp_path)

    skill_dir = tmp_path / skill_name
    assert skill_dir.exists(), f"Dossier skill absent : {skill_dir}"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "skill.yaml").exists()
    assert (skill_dir / "skill.py").exists()


@pytest.mark.asyncio
async def test_propose_skill_candidate_skill_md_valide(tmp_path: Path) -> None:
    """Le SKILL.md généré a un frontmatter valide (name + description)."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    mock_llm = _make_mock_llm(_SAMPLE_SKILL_MD)
    synth = SkillSynthesizer(llm=mock_llm)

    skill_name = await synth.propose_skill_candidate(_SAMPLE_TRAJECTORY, target_dir=tmp_path)

    skill_md = (tmp_path / skill_name / "SKILL.md").read_text(encoding="utf-8")
    import re

    fm_match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
    assert fm_match, "Frontmatter YAML absent du SKILL.md"
    fm = yaml.safe_load(fm_match.group(1))
    assert fm.get("name"), "Champ 'name' absent du frontmatter"
    assert fm.get("description"), "Champ 'description' absent du frontmatter"


@pytest.mark.asyncio
async def test_propose_skill_candidate_skill_yaml_contient_system_prompt(
    tmp_path: Path,
) -> None:
    """Le skill.yaml contient un system_prompt non vide."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    mock_llm = _make_mock_llm(_SAMPLE_SKILL_MD)
    synth = SkillSynthesizer(llm=mock_llm)

    skill_name = await synth.propose_skill_candidate(_SAMPLE_TRAJECTORY, target_dir=tmp_path)

    with (tmp_path / skill_name / "skill.yaml").open(encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    assert meta.get("system_prompt"), "system_prompt absent ou vide dans skill.yaml"


@pytest.mark.asyncio
async def test_propose_skill_candidate_nom_invalide_leve_erreur(tmp_path: Path) -> None:
    """propose_skill_candidate lève ValueError si le LLM retourne un nom invalide."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    bad_md = "---\nname: INVALID_NAME_WITH_CAPS\ndescription: test\n---\nBody."
    mock_llm = _make_mock_llm(bad_md)
    synth = SkillSynthesizer(llm=mock_llm)

    with pytest.raises(ValueError, match="kebab-case"):
        await synth.propose_skill_candidate(_SAMPLE_TRAJECTORY, target_dir=tmp_path)


@pytest.mark.asyncio
async def test_improve_skill_met_a_jour_les_fichiers(tmp_path: Path) -> None:
    """improve_skill met à jour SKILL.md, skill.yaml et skill.py."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    skill_name = "web-research"
    skill_dir = tmp_path / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SAMPLE_SKILL_MD, encoding="utf-8")

    improved_md = _SAMPLE_SKILL_MD.replace('version: "1.0"', 'version: "1.1"')
    mock_llm = _make_mock_llm(improved_md)
    synth = SkillSynthesizer(llm=mock_llm)

    with patch("jarvis.capabilities.skills.synthesizer.SKILLS_INSTALLED_DIR", tmp_path):
        await synth.improve_skill(skill_name, "Leçon : toujours vérifier plusieurs sources.")

    updated = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "1.1" in updated, "Version non incrémentée dans le SKILL.md amélioré"

    with (skill_dir / "skill.yaml").open(encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    assert meta.get("version") in ("1.1", "1.1.0"), (
        f"Version inattendue dans skill.yaml : {meta.get('version')}"
    )


@pytest.mark.asyncio
async def test_improve_skill_fichier_absent_leve_erreur(tmp_path: Path) -> None:
    """improve_skill lève FileNotFoundError si le skill est absent."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    mock_llm = _make_mock_llm("")
    synth = SkillSynthesizer(llm=mock_llm)

    with patch("jarvis.capabilities.skills.synthesizer.SKILLS_INSTALLED_DIR", tmp_path):
        with pytest.raises(FileNotFoundError):
            await synth.improve_skill("skill-inexistant", "test")


# ── Tests chargement par le SkillRegistry ─────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_synthetise_chargeable_par_le_registry(tmp_path: Path) -> None:
    """Un skill synthétisé peut être chargé et activé par le SkillRegistry."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer

    mock_llm = _make_mock_llm(_SAMPLE_SKILL_MD)
    synth = SkillSynthesizer(llm=mock_llm)

    skill_name = await synth.propose_skill_candidate(_SAMPLE_TRAJECTORY, target_dir=tmp_path)

    # Charge le skill directement depuis le dossier temporaire
    from jarvis.capabilities.skills.registry import SkillRegistry

    registry = SkillRegistry.__new__(SkillRegistry)
    registry._skills = {}
    with patch("jarvis.capabilities.skills.registry.SKILLS_INSTALLED_DIR", tmp_path):
        registry.load_all()

    assert skill_name in registry._skills, (
        f"Skill '{skill_name}' non trouvé dans le registry après synthèse.\n"
        f"Skills chargés : {list(registry._skills.keys())}"
    )
    skill = registry._skills[skill_name]
    assert skill.is_active(), "Le skill synthétisé n'est pas actif (SYSTEM_PROMPT vide)"
    assert skill.name == skill_name


# ── Tests AgentSkillsAdapter ──────────────────────────────────────────────────


def test_export_to_standard_produit_skill_md_valide(tmp_path: Path) -> None:
    """export_to_standard produit un SKILL.md avec frontmatter valide."""
    skill_name = "data-analysis"
    skill_dir = tmp_path / skill_name
    skill_dir.mkdir()

    meta = {
        "name": skill_name,
        "version": "1.0.0",
        "author": "test",
        "description": "Analyse des données structurées.",
        "tags": ["data", "analysis"],
        "system_prompt": "## Skill Data Analysis\n\nInstructions de l'analyse.",
        "type": "conversational",
    }
    with (skill_dir / "skill.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True)

    from jarvis.capabilities.skills.standard import AgentSkillsAdapter

    with patch("jarvis.capabilities.skills.standard.SKILLS_INSTALLED_DIR", tmp_path):
        skill_md = AgentSkillsAdapter.export_to_standard(skill_name)

    assert "---" in skill_md, "Frontmatter YAML absent du SKILL.md exporté"
    assert "data-analysis" in skill_md
    assert "Analyse des données structurées." in skill_md


def test_import_from_standard_cree_les_fichiers(tmp_path: Path) -> None:
    """import_from_standard crée skill.yaml + skill.py depuis un SKILL.md."""
    from jarvis.capabilities.skills.standard import AgentSkillsAdapter

    with patch("jarvis.capabilities.skills.standard.SKILLS_INSTALLED_DIR", tmp_path):
        skill_name = AgentSkillsAdapter.import_from_standard(_SAMPLE_SKILL_MD)

    skill_dir = tmp_path / skill_name
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "skill.yaml").exists()
    assert (skill_dir / "skill.py").exists()

    with (skill_dir / "skill.yaml").open(encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    assert meta["name"] == skill_name
    assert meta.get("system_prompt"), "system_prompt absent dans skill.yaml importé"


def test_import_from_standard_nom_invalide_leve_erreur() -> None:
    """import_from_standard lève ValueError si le name est invalide."""
    from jarvis.capabilities.skills.standard import AgentSkillsAdapter

    bad_md = "---\nname: Invalid_Name\ndescription: test\n---\nBody."
    with pytest.raises(ValueError, match="invalide"):
        AgentSkillsAdapter.import_from_standard(bad_md)


def test_import_from_standard_description_absente_leve_erreur() -> None:
    """import_from_standard lève ValueError si description est absente."""
    from jarvis.capabilities.skills.standard import AgentSkillsAdapter

    bad_md = "---\nname: valid-name\n---\nBody."
    with pytest.raises(ValueError, match="description"):
        AgentSkillsAdapter.import_from_standard(bad_md)


def test_round_trip_export_import(tmp_path: Path) -> None:
    """Round-trip export → import conserve le nom et la description."""
    skill_name = "round-trip-test"
    skill_dir = tmp_path / skill_name
    skill_dir.mkdir()

    meta = {
        "name": skill_name,
        "version": "2.0.0",
        "author": "test-author",
        "description": "Test du round-trip import/export agentskills.io.",
        "tags": ["test"],
        "system_prompt": "Instructions de test du round-trip.",
        "type": "conversational",
    }
    with (skill_dir / "skill.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True)

    from jarvis.capabilities.skills.standard import AgentSkillsAdapter

    # Export Jarvis → SKILL.md
    with patch("jarvis.capabilities.skills.standard.SKILLS_INSTALLED_DIR", tmp_path):
        skill_md = AgentSkillsAdapter.export_to_standard(skill_name)

    # Import SKILL.md → Jarvis (dans un dossier séparé)
    import_dir = tmp_path / "imported"
    import_dir.mkdir()
    with patch("jarvis.capabilities.skills.standard.SKILLS_INSTALLED_DIR", import_dir):
        imported_name = AgentSkillsAdapter.import_from_standard(skill_md)

    assert imported_name == skill_name, f"Nom après round-trip : '{imported_name}' ≠ '{skill_name}'"
    with (import_dir / imported_name / "skill.yaml").open(encoding="utf-8") as f:
        imported_meta = yaml.safe_load(f)

    assert imported_meta["name"] == skill_name
    assert imported_meta["description"] == meta["description"]


def test_is_valid_name_kebab_case() -> None:
    """_is_valid_name valide correctement les noms agentskills.io."""
    from jarvis.capabilities.skills.standard import _is_valid_name

    assert _is_valid_name("web-research")
    assert _is_valid_name("data-analysis-v2")
    assert _is_valid_name("a")
    assert not _is_valid_name("UPPERCASE")
    assert not _is_valid_name("-leading-hyphen")
    assert not _is_valid_name("trailing-hyphen-")
    assert not _is_valid_name("double--hyphen")
    assert not _is_valid_name("a" * 65)


# ── Tests tools/skills.py ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_create_tool_succes(tmp_path: Path) -> None:
    """SkillCreateTool retourne un ToolResult non-erreur sur succès via le Lab."""
    from jarvis.capabilities.skills.lab import SkillLab
    from jarvis.capabilities.skills.lifecycle import SkillLifecycle
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
    from jarvis.capabilities.tools.skills import SkillCreateTool
    from jarvis.providers.memory.kernel import MemoryKernel

    mock_llm = _make_mock_llm(_SAMPLE_SKILL_MD)
    synth = SkillSynthesizer(llm=mock_llm)
    kernel = MemoryKernel(db_path=tmp_path / "memory.db")
    lifecycle = SkillLifecycle(db_path=tmp_path / "memory.db")
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=tmp_path / "candidates",
        installed_dir=tmp_path / "installed",
    )
    tool = SkillCreateTool(lab=lab)

    result = await tool.execute(
        task_description="Recherche web multi-sources.",
        result="Synthèse des résultats.",
    )

    assert not result.is_error, f"Erreur inattendue : {result.content}"
    assert "web-research" in result.content
    # CRITIQUE : passe par le Lab, donc en attente de validation humaine.
    assert "validation humaine" in result.content.lower()
    # Et JAMAIS dans installed/
    assert not (tmp_path / "installed" / "web-research").exists()


@pytest.mark.asyncio
async def test_skill_list_tool_vide() -> None:
    """SkillListTool retourne un message clair si aucun skill."""
    from jarvis.capabilities.tools.skills import SkillListTool

    mock_registry = MagicMock()
    mock_registry.list_installed.return_value = []

    tool = SkillListTool()
    with patch("jarvis.capabilities.tools.skills.skill_registry", mock_registry):
        result = await tool.execute()

    assert not result.is_error
    assert "Aucun skill" in result.content


@pytest.mark.asyncio
async def test_skill_list_tool_avec_skills() -> None:
    """SkillListTool liste les skills installés."""
    from jarvis.capabilities.tools.skills import SkillListTool

    mock_registry = MagicMock()
    mock_registry.list_installed.return_value = [
        {
            "name": "web-research",
            "version": "1.0.0",
            "description": "Recherche web.",
            "tags": ["research"],
            "type": "conversational",
        },
    ]

    tool = SkillListTool()
    with patch("jarvis.capabilities.tools.skills.skill_registry", mock_registry):
        result = await tool.execute()

    assert not result.is_error
    assert "web-research" in result.content


@pytest.mark.asyncio
async def test_skill_improve_tool_skill_absent() -> None:
    """SkillImproveTool retourne is_error=True si le skill est absent."""
    from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
    from jarvis.capabilities.tools.skills import SkillImproveTool

    mock_llm = _make_mock_llm("")
    synth = SkillSynthesizer(llm=mock_llm)
    tool = SkillImproveTool(synthesizer=synth)

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("jarvis.capabilities.skills.synthesizer.SKILLS_INSTALLED_DIR", Path(tmpdir)):
            result = await tool.execute(
                skill_name="inexistant",
                new_experience="test",
            )

    assert result.is_error
    assert "introuvable" in result.content.lower()
