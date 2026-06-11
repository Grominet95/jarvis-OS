"""Tests des scripts install_local_extension / uninstall_local_extension.

Couvre :
- Détection du type via le champ `type` du manifest (priorité), heuristique
  en fallback.
- Refus quand `validate_catalog.py` n'existe pas (chantier amont non livré).
- Refus quand `validate_catalog.py` renvoie rc ≠ 0.
- Création du symlink sur les 3 types avec un validateur factice.
- Uninstall retire uniquement le lien (refuse de toucher un vrai dossier).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
INSTALL = REPO / "scripts" / "install_local_extension.py"
UNINSTALL = REPO / "scripts" / "uninstall_local_extension.py"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_jarvis_skills(tmp_path: Path, *, validator_rc: int | None) -> Path:
    """Crée un faux repo `jarvis-skills/` minimal.

    validator_rc :
      - None  → pas de validate_catalog.py (chantier amont non livré)
      - 0     → validateur OK
      - 1     → validateur refuse
    """
    repo = tmp_path / "jarvis-skills"
    (repo / "skills").mkdir(parents=True)
    (repo / "presets").mkdir(parents=True)
    (repo / "views").mkdir(parents=True)
    if validator_rc is not None:
        scripts = repo / "scripts"
        scripts.mkdir()
        (scripts / "validate_catalog.py").write_text(f"import sys\nsys.exit({validator_rc})\n")
    return repo


def _write_skill(parent: Path, name: str, kind: str) -> Path:
    """kind : 'skill' | 'preset' | 'view'."""
    src = parent / name
    src.mkdir()
    if kind == "skill":
        (src / "skill.py").write_text(
            "from skills.base import SkillBase\nclass S(SkillBase):\n    SYSTEM_PROMPT = 'x'\n"
        )
        (src / "skill.yaml").write_text(f"name: {name}\ntype: conversational\n")
    elif kind == "preset":
        (src / "skill.py").write_text("from skills.base import PresetSkill\n")
        (src / "skill.yaml").write_text(
            f"name: {name}\ntype: preset\nsteps:\n  - name: hello\n    type: wait\n    seconds: 1\n"
        )
    elif kind == "view":
        (src / "view.js").write_text("/* view */")
        (src / "VIEW.md").write_text(f"---\nid: {name}\nname: {name}\ncommands: []\n---\n")
    return src


def _run(args: list[str], dev_root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "JARVIS_DEV_EXTENSIONS_DIR": str(dev_root)}
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
    )


# ── Détection du type ────────────────────────────────────────────────────────


def test_detect_type_manifest_priorite_sur_heuristique(tmp_path: Path) -> None:
    """Manifest `type: skill` doit l'emporter même si `steps:` est présent."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from install_local_extension import detect_type
    finally:
        sys.path.pop(0)

    src = tmp_path / "weird"
    src.mkdir()
    # Pièges : steps présents (heuristique dirait "preset") MAIS type explicite
    (src / "skill.yaml").write_text(
        "name: weird\ntype: conversational\nsteps:\n  - name: x\n    type: wait\n"
    )
    assert detect_type(src) == "skill"


def test_detect_type_heuristique_steps(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from install_local_extension import detect_type
    finally:
        sys.path.pop(0)

    src = tmp_path / "p"
    src.mkdir()
    (src / "skill.yaml").write_text("name: p\nsteps:\n  - name: x\n    type: wait\n")
    assert detect_type(src) == "preset"


def test_detect_type_view_via_view_md(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from install_local_extension import detect_type
    finally:
        sys.path.pop(0)

    src = tmp_path / "v"
    src.mkdir()
    (src / "VIEW.md").write_text("---\nid: v\nname: v\n---\n")
    (src / "view.js").write_text("/* */")
    assert detect_type(src) == "view"


# ── Refus de validation ──────────────────────────────────────────────────────


def test_refus_si_validate_catalog_absent(tmp_path: Path) -> None:
    repo = _fake_jarvis_skills(tmp_path, validator_rc=None)
    src = _write_skill(repo / "skills", "x", "skill")
    dev = tmp_path / "dev"

    proc = _run([str(INSTALL), str(src)], dev)

    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "validate_catalog" in (proc.stdout + proc.stderr).lower()
    # Aucun lien créé.
    assert not (dev / "skills" / "x").exists()


def test_refus_si_validate_catalog_rc_non_zero(tmp_path: Path) -> None:
    repo = _fake_jarvis_skills(tmp_path, validator_rc=1)
    src = _write_skill(repo / "skills", "x", "skill")
    dev = tmp_path / "dev"

    proc = _run([str(INSTALL), str(src)], dev)

    assert proc.returncode != 0
    assert not (dev / "skills" / "x").exists()


# ── Création du symlink sur les 3 types ──────────────────────────────────────


@pytest.mark.parametrize(
    "kind,dest_subdir",
    [("skill", "skills"), ("preset", "presets"), ("view", "views")],
)
def test_install_cree_symlink(tmp_path: Path, kind: str, dest_subdir: str) -> None:
    repo = _fake_jarvis_skills(tmp_path, validator_rc=0)
    parent = repo / dest_subdir
    src = _write_skill(parent, "mon-ext", kind)
    dev = tmp_path / "dev"

    proc = _run([str(INSTALL), str(src)], dev)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    link = dev / dest_subdir / "mon-ext"
    assert link.is_symlink()
    assert link.resolve() == src.resolve()


# ── Uninstall ────────────────────────────────────────────────────────────────


def test_uninstall_retire_le_lien(tmp_path: Path) -> None:
    repo = _fake_jarvis_skills(tmp_path, validator_rc=0)
    src = _write_skill(repo / "skills", "todelete", "skill")
    dev = tmp_path / "dev"
    _run([str(INSTALL), str(src)], dev)
    assert (dev / "skills" / "todelete").is_symlink()

    proc = _run([str(UNINSTALL), "todelete"], dev)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (dev / "skills" / "todelete").exists()
    # La source d'origine ne doit pas avoir été touchée.
    assert src.exists()


def test_uninstall_refuse_sur_dossier_non_symlink(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    (dev / "skills" / "vrai-dossier").mkdir(parents=True)
    (dev / "skills" / "vrai-dossier" / "skill.py").write_text("x")

    proc = _run([str(UNINSTALL), "vrai-dossier"], dev)

    # rc ≠ 0 et le dossier toujours là.
    assert proc.returncode != 0
    assert (dev / "skills" / "vrai-dossier").is_dir()


def test_uninstall_signale_si_rien_a_faire(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    proc = _run([str(UNINSTALL), "nimporte"], dev)
    assert proc.returncode == 1
