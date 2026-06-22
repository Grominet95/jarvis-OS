# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Test de non-régression sécurité (PHASE 4).

Garantit qu'aucun appel à SkillCreateTool ne peut installer une skill
directement dans skills/installed/ — c'est l'équivalent négatif du "skill
volontairement cassée doit être rejetée" : ici on prouve qu'aucun chemin
d'install ne contourne le gate du Lab.

Si ce test casse, c'est qu'une backdoor a été ré-introduite : un commit a
soit restauré propose_skill() legacy, soit ajouté un autre chemin d'install
direct. STOP — sécuriser avant de merger.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.capabilities.skills.lab import SkillLab
from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillStatus
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
from jarvis.capabilities.tools.skills import SkillCreateTool
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.kernel import MemoryKernel


class _FakeLLM(LLMProvider):
    """Renvoie un SKILL.md valide pour le test."""

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


_VALID_SKILL_MD = """\
---
name: test-pattern-skill
description: Skill de test pour vérifier que SkillCreateTool passe par le Lab.
license: MIT
metadata:
  author: test
  version: "1.0"
  tags: [test]
---

# Test Pattern Skill

Instructions de test.
"""


@pytest.mark.asyncio
async def test_skill_create_tool_ne_produit_jamais_dans_installed(
    tmp_path: Path,
) -> None:
    """CAS NÉGATIF — équivalent de la skill volontairement cassée, mais pour
    le chemin tool.

    On invoque SkillCreateTool comme le ferait un LLM via le voice agent.
    Quel que soit le résultat (sandbox pass ou fail), la skill DOIT être en
    zone tampon (candidates/{name}/) et JAMAIS dans installed/{name}/.
    Seule une action humaine explicite via lab.promote() peut l'y installer.
    """
    installed_dir = tmp_path / "installed"
    candidates_dir = tmp_path / "candidates"

    llm = _FakeLLM(skill_md=_VALID_SKILL_MD)
    synth = SkillSynthesizer(llm=llm)
    kernel = MemoryKernel(db_path=tmp_path / "memory.db")
    lifecycle = SkillLifecycle(db_path=tmp_path / "memory.db")
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=candidates_dir,
        installed_dir=installed_dir,
    )

    tool = SkillCreateTool(lab=lab)

    # Avant : installed/ n'existe pas
    assert not installed_dir.exists()

    result = await tool.execute(
        task_description="Pattern de test répétitif",
        result="Tâche accomplie",
    )

    # Le tool a réussi (sandbox vert avec ce SKILL.md valide)
    assert not result.is_error, f"Tool a échoué : {result.content}"
    assert "validation humaine" in result.content.lower()

    # La candidate EST en zone tampon
    cand_dir = candidates_dir / "test-pattern-skill"
    assert cand_dir.exists()
    assert (cand_dir / "skill.py").exists()
    assert (cand_dir / "skill.yaml").exists()

    # CRITIQUE : la skill n'est PAS dans installed/
    assert not installed_dir.exists() or not (installed_dir / "test-pattern-skill").exists()

    # Le lifecycle reflète bien SANDBOXED_PASS (en attente humaine)
    record = lifecycle.get("test-pattern-skill")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_PASS
    # source_event_id est None car le tool n'a pas d'event Kernel d'origine
    assert record.source_event_id is None


@pytest.mark.asyncio
async def test_skill_create_tool_meme_avec_skill_cassee_ne_pollue_pas_installed(
    tmp_path: Path,
) -> None:
    """Si le LLM génère une skill qui crash au sandbox, installed/ reste vide
    et le tool retourne is_error=True.

    Deuxième garde-fou : même un faux positif côté synthesizer (skill qui
    génère mais crash à l'import) ne peut PAS finir installée.
    """
    installed_dir = tmp_path / "installed"
    candidates_dir = tmp_path / "candidates"

    # SKILL.md valide pour passer le synthesizer
    llm = _FakeLLM(skill_md=_VALID_SKILL_MD)
    synth = SkillSynthesizer(llm=llm)
    # On corrompt le générateur skill.py pour produire un fichier qui crash
    synth._generate_skill_py = lambda name: (  # noqa: ARG005
        "raise RuntimeError('skill cassée — backdoor test')\n"
    )

    kernel = MemoryKernel(db_path=tmp_path / "memory.db")
    lifecycle = SkillLifecycle(db_path=tmp_path / "memory.db")
    lab = SkillLab(
        kernel=kernel,
        lifecycle=lifecycle,
        synthesizer=synth,
        candidates_dir=candidates_dir,
        installed_dir=installed_dir,
    )
    tool = SkillCreateTool(lab=lab)

    result = await tool.execute(
        task_description="Pattern qui crashera",
    )

    # Le tool retourne une erreur explicite
    assert result.is_error, f"Le tool aurait dû refuser, contenu : {result.content}"
    assert "rejetée" in result.content.lower() or "rejet" in result.content.lower()

    # installed/ reste vide
    assert not installed_dir.exists() or not any(installed_dir.iterdir())

    # Lifecycle reflète bien SANDBOXED_FAIL
    record = lifecycle.get("test-pattern-skill")
    assert record is not None
    assert record.status == SkillStatus.SANDBOXED_FAIL


def test_skill_create_tool_constructor_refuse_sans_lab() -> None:
    """SkillCreateTool DOIT exiger un lab en injection — aucune valeur par
    défaut, aucun fallback. Si quelqu'un instancie sans lab, ça crashe
    immédiatement (au lieu de silencieusement installer en direct)."""
    with pytest.raises(TypeError):
        SkillCreateTool()  # type: ignore[call-arg]
