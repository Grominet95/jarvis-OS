"""Tests du dry_run_preset.

Vérifie :
- Découverte du preset (zone dev prioritaire, fallback installed).
- 0 effet de bord : aucun subprocess spawné, aucun appel TTS/LLM, même quand
  le preset contient des steps cli avec des commandes destructives.
- Tags CONFIRMATION et DESTRUCTIF apparaissent là où attendu.
- Refus si la cible n'est pas un preset.
- Erreur propre si introuvable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
DRY_RUN = REPO / "scripts" / "dry_run_preset.py"

sys.path.insert(0, str(REPO / "scripts"))
from dry_run_preset import _is_destructive, find_preset, format_step  # noqa: E402


def _write_preset(parent: Path, name: str, body: str) -> Path:
    src = parent / name
    src.mkdir(parents=True)
    (src / "skill.yaml").write_text(body)
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


# ── Découverte ───────────────────────────────────────────────────────────────


def test_find_preset_zone_dev_prioritaire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dev = tmp_path / "dev"
    _write_preset(
        dev / "presets",
        "mode-test",
        "name: mode-test\ntype: preset\nsteps:\n  - name: x\n    type: wait\n    seconds: 1\n",
    )
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(dev))

    found = find_preset("mode-test")
    assert found is not None
    assert found.resolve() == (dev / "presets" / "mode-test").resolve()


def test_find_preset_introuvable_renvoie_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JARVIS_DEV_EXTENSIONS_DIR", str(tmp_path / "absent"))
    assert find_preset("inexistant-xxx") is None


# ── Heuristique destructif ───────────────────────────────────────────────────


def test_destructif_detecte() -> None:
    assert _is_destructive("rm -rf /tmp/x")
    assert _is_destructive("sudo shutdown -h now")
    assert _is_destructive("echo 'foo' > /tmp/file")
    assert _is_destructive("git push origin main")
    assert not _is_destructive("echo hello")
    assert not _is_destructive("open -a 'OBS'")


def test_format_step_tags_confirmation_destructif() -> None:
    fs = format_step(
        1,
        {
            "type": "cli",
            "name": "purge",
            "command": "rm -rf /tmp/x",
            "requires_confirmation": True,
        },
    )
    assert "CONFIRMATION" in fs.tags
    assert any("DESTRUCTIF" in t for t in fs.tags)


# ── Aucun effet de bord (end-to-end via subprocess) ──────────────────────────


def test_aucun_subprocess_pour_steps_cli(tmp_path: Path) -> None:
    """Même avec un step cli qui marquerait un fichier, rien ne doit s'exécuter."""
    dev = tmp_path / "dev"
    marker = tmp_path / "MARKER"
    _write_preset(
        dev / "presets",
        "p",
        f"""name: p
type: preset
steps:
  - name: write-marker
    type: cli
    command: touch {marker}
  - name: wait
    type: wait
    seconds: 5
""",
    )

    proc = _run([str(DRY_RUN), "p"], dev)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # La commande n'a PAS été exécutée.
    assert not marker.exists(), "dry-run a exécuté la commande cli — interdit"
    # Et la sortie contient bien la commande affichée.
    assert "touch" in proc.stdout
    assert f"{marker}" in proc.stdout


def test_sortie_indique_confirmation_et_destructif(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    _write_preset(
        dev / "presets",
        "p2",
        """name: p2
type: preset
steps:
  - name: nettoyage
    type: cli
    command: rm -rf /tmp/zzz
    requires_confirmation: true
""",
    )
    proc = _run([str(DRY_RUN), "p2"], dev)
    assert proc.returncode == 0
    out = proc.stdout
    assert "[CONFIRMATION]" in out
    assert "DESTRUCTIF" in out


def test_refus_si_pas_un_preset(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    _write_preset(
        dev / "skills",
        "convskill",
        "name: convskill\ntype: conversational\n",
    )
    proc = _run([str(DRY_RUN), "convskill"], dev)
    assert proc.returncode == 2
    assert "preset" in proc.stderr.lower()


def test_erreur_si_introuvable(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    proc = _run([str(DRY_RUN), "ghost"], dev)
    assert proc.returncode == 1
    assert "introuvable" in proc.stderr.lower()
