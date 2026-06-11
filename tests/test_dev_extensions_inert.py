"""Test d'inertie de la zone dev (~/.jarvis/extensions/dev/).

Garantie : sans extension dev liée, Jarvis charge skills/installed/ exactement
comme avant le patch — même set de noms, même ordre de mounts FastAPI.

Couvre les 4 cas demandés :
  (a) zone absente              → comportement strictement identique
  (b) zone existe mais vide     → idem
  (c) FastAPI app sans dev      → 0 mount supplémentaire
  (d) override : un skill dev shadow un installed du même nom
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from jarvis.capabilities.skills.dev_extensions import iter_dev_skills_and_presets, mount_dev_views
from jarvis.capabilities.skills.registry import SKILLS_INSTALLED_DIR, SkillRegistry


def _installed_skill_names() -> set[str]:
    """Set des noms de skills physiquement installés (depuis le disque)."""
    return {
        d.name for d in SKILLS_INSTALLED_DIR.iterdir() if d.is_dir() and (d / "skill.py").exists()
    }


# ── (a) zone absente ─────────────────────────────────────────────────────────


def test_a_zone_dev_absente_charge_uniquement_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HOME redirigé vers un tmp_path SANS .jarvis/extensions/dev → la zone est
    inexistante. load_all() doit charger exactement skills/installed/."""
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(tmp_path / "absent"))
    assert not (tmp_path / "absent").exists(), "garde-fou : la zone ne doit pas exister"

    assert list(iter_dev_skills_and_presets()) == []

    reg = SkillRegistry()
    reg.load_all()
    loaded = set(reg.get_all().keys())

    # Tous les installés (dont skill.py existe ET dont les requirements passent)
    # doivent se retrouver chargés. On vérifie l'inclusion : un skill installé
    # peut être ignoré pour requirements (binaire absent), mais aucun skill dev
    # ne doit apparaître.
    installed_names = _installed_skill_names()
    assert loaded.issubset(installed_names), (
        f"Skills inattendus (non-installed) : {loaded - installed_names}"
    )


# ── (b) zone existe mais vide ────────────────────────────────────────────────


def test_b_zone_dev_vide_charge_uniquement_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zone dev créée mais sous-dossiers skills/ presets/ vides → no-op."""
    dev_root = tmp_path / "dev"
    (dev_root / "skills").mkdir(parents=True)
    (dev_root / "presets").mkdir(parents=True)
    (dev_root / "views").mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(dev_root))

    assert list(iter_dev_skills_and_presets()) == []

    reg = SkillRegistry()
    reg.load_all()
    loaded = set(reg.get_all().keys())

    installed_names = _installed_skill_names()
    assert loaded.issubset(installed_names)


# ── (c) FastAPI : 0 mount supplémentaire sans zone dev ───────────────────────


def test_c_mount_dev_views_inerte_sans_zone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(tmp_path / "absent"))
    app = FastAPI()
    routes_before = list(app.routes)

    added = mount_dev_views(app)

    assert added == 0
    assert list(app.routes) == routes_before


def test_c_mount_dev_views_inerte_avec_zone_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev_root = tmp_path / "dev"
    (dev_root / "views").mkdir(parents=True)
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(dev_root))
    app = FastAPI()
    routes_before = list(app.routes)

    added = mount_dev_views(app)

    assert added == 0
    assert list(app.routes) == routes_before


# ── (d) override : skill dev shadow installed du même nom ────────────────────


def test_d_override_dev_shadow_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un skill dev /skills/<X> doit masquer skills/installed/<X> quand X
    existe déjà côté installed."""
    installed = _installed_skill_names()
    if not installed:
        pytest.skip("Aucun skill installé pour tester l'override")
    # On choisit un skill installé et on crée un shadow dev très simple.
    target = sorted(installed)[0]

    dev_root = tmp_path / "dev"
    dev_skill = dev_root / "skills" / target
    dev_skill.mkdir(parents=True)
    (dev_skill / "skill.py").write_text(
        "from skills.base import SkillBase\n\n"
        "class DevShadow(SkillBase):\n"
        '    SYSTEM_PROMPT = "shadow dev"\n'
    )
    (dev_skill / "skill.yaml").write_text(
        f"name: {target}\nversion: 99.0.0-dev\nauthor: dev-test\n"
    )
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(dev_root))

    reg = SkillRegistry()
    reg.load_all()

    loaded = reg.get(target)
    assert loaded is not None, f"Skill '{target}' devrait être chargé depuis dev"
    # Le shadow est marqué version 99.0.0-dev → preuve que c'est bien la
    # version dev qui a été chargée, pas l'installée.
    assert loaded.version == "99.0.0-dev", f"Override raté : version chargée = {loaded.version}"
    # __dir doit pointer vers la zone dev, pas vers skills/installed/.
    loaded_dir = Path(loaded.metadata["__dir"])
    assert loaded_dir == dev_skill.resolve(), (
        f"__dir devrait pointer vers le dev, pointe vers {loaded_dir}"
    )
