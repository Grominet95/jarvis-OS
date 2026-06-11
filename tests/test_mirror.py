"""Tests du miroir Markdown unidirectionnel (CDC §6.7).

Couvre :
- Export par catégorie vers fichiers MD
- Bandeau d'avertissement présent
- Édition manuelle d'un .md → écrasée à la régénération (aucun effet sur la DB)
- needs_review séparé
- uncertain-beliefs : faible confidence
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.mirror import MemoryMirror
from jarvis.providers.memory.schemas import DecayPolicy, Fact, FactStatus


def _make_fact(
    fid: str,
    subject: str = "barth",
    predicate: str = "prefers",
    obj: str = "python",
    category: str = "tool",
    status: FactStatus = FactStatus.ACTIVE,
    confidence: float = 0.75,
    importance: float = 0.6,
) -> Fact:
    now = datetime.now()
    return Fact(
        id=fid,
        subject=subject,
        predicate=predicate,
        object=obj,
        category=category,
        status=status,
        confidence=confidence,
        support_count=1,
        decay_policy=DecayPolicy.MEDIUM,
        importance=importance,
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )


@pytest.fixture
def kernel(tmp_path: Path) -> MemoryKernel:
    return MemoryKernel(tmp_path / "test.db")


def test_export_cree_fichier_par_categorie(tmp_path: Path, kernel: MemoryKernel) -> None:
    kernel.insert_fact(_make_fact("f1", category="preference", obj="café noir"))
    kernel.insert_fact(_make_fact("f2", category="goal", predicate="targets", obj="sub-3h"))

    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    report = mirror.export()

    assert (tmp_path / "mirror/user/preferences.md").exists()
    assert (tmp_path / "mirror/user/goals.md").exists()
    assert "user/preferences.md" in report.files_written
    assert report.facts_exported == 2


def test_bandeau_warning_present(tmp_path: Path, kernel: MemoryKernel) -> None:
    kernel.insert_fact(_make_fact("f1", category="preference"))
    MemoryMirror(kernel, tmp_path / "mirror").export()

    content = (tmp_path / "mirror/user/preferences.md").read_text(encoding="utf-8")
    assert "AUTO-GÉNÉRÉ" in content
    assert "NE PAS ÉDITER" in content


def test_edition_manuelle_ecrasee_a_la_regeneration(tmp_path: Path, kernel: MemoryKernel) -> None:
    """Une modification manuelle du miroir disparaît à l'export suivant. DB inchangée."""
    kernel.insert_fact(_make_fact("f1", category="preference", obj="café"))
    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    mirror.export()

    prefs_md = tmp_path / "mirror/user/preferences.md"
    original = prefs_md.read_text(encoding="utf-8")

    # Édition manuelle malicieuse
    prefs_md.write_text("# Détourné par l'humain\n- fait inventé\n", encoding="utf-8")
    assert "Détourné" in prefs_md.read_text(encoding="utf-8")

    # Régénération
    mirror.export()
    regen = prefs_md.read_text(encoding="utf-8")
    assert "Détourné" not in regen
    assert regen == original

    # DB n'a JAMAIS bougé (count facts inchangé)
    assert kernel.count_facts(FactStatus.ACTIVE) == 1


def test_needs_review_fichier_separe(tmp_path: Path, kernel: MemoryKernel) -> None:
    kernel.insert_fact(_make_fact("f1", status=FactStatus.NEEDS_REVIEW))
    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    report = mirror.export()
    assert "jarvis/needs-review.md" in report.files_written
    content = (tmp_path / "mirror/jarvis/needs-review.md").read_text(encoding="utf-8")
    assert "à revoir" in content.lower()


def test_uncertain_beliefs_separes_par_confidence(tmp_path: Path, kernel: MemoryKernel) -> None:
    """Un fact persona/belief à faible confidence va dans uncertain-beliefs."""
    kernel.insert_fact(
        _make_fact("low", category="persona", confidence=0.3, predicate="communicates_as")
    )
    kernel.insert_fact(
        _make_fact("high", category="persona", confidence=0.85, predicate="communicates_as")
    )

    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    report = mirror.export()
    assert "jarvis/persona.md" in report.files_written
    assert "jarvis/uncertain-beliefs.md" in report.files_written

    persona_md = (tmp_path / "mirror/jarvis/persona.md").read_text(encoding="utf-8")
    uncertain_md = (tmp_path / "mirror/jarvis/uncertain-beliefs.md").read_text(encoding="utf-8")
    # Low conf → uncertain ; high conf → persona
    assert "0.30" in uncertain_md
    assert "0.85" in persona_md


def test_export_aucun_fact_genere_fichier_vide_lisible(
    tmp_path: Path, kernel: MemoryKernel
) -> None:
    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    report = mirror.export()
    assert report.facts_exported == 0
    assert report.files_written == []


def test_superseded_facts_non_exportes(tmp_path: Path, kernel: MemoryKernel) -> None:
    """Un fact en statut SUPERSEDED n'apparaît pas dans le miroir."""
    kernel.insert_fact(_make_fact("ar", category="goal", status=FactStatus.SUPERSEDED))
    kernel.insert_fact(_make_fact("ac", category="goal", obj="3h10"))
    mirror = MemoryMirror(kernel, tmp_path / "mirror")
    mirror.export()
    goals_md = (tmp_path / "mirror/user/goals.md").read_text(encoding="utf-8")
    assert "3h10" in goals_md
    assert "1 fait" in goals_md
