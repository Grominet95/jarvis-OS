"""Tests unitaires de kernel.bundle (resolution runtime / manifest offline)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from jarvis.kernel import bundle


@pytest.fixture
def fake_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reconfigure le module bundle pour pointer vers un faux bundle temporaire."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    monkeypatch.setattr(bundle, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(bundle, "BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(bundle, "MANIFEST_PATH", bundle_dir / "manifest.json")
    return bundle_dir


def _venv_python(bundle_dir: Path) -> Path:
    if sys.platform == "win32":
        p = bundle_dir / ".venv" / "Scripts" / "python.exe"
    else:
        p = bundle_dir / ".venv" / "bin" / "python"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    return p


def test_load_manifest_missing_returns_empty(fake_bundle: Path) -> None:
    assert bundle.load_manifest() == {}


def test_load_manifest_reads_json(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text(
        json.dumps({"version": "1", "platform": "windows"}), encoding="utf-8"
    )
    assert bundle.load_manifest() == {"version": "1", "platform": "windows"}


def test_load_manifest_tolerates_utf8_bom(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text(
        json.dumps({"version": "2"}), encoding="utf-8-sig"
    )
    assert bundle.load_manifest() == {"version": "2"}


def test_bundle_available_false_without_manifest(fake_bundle: Path) -> None:
    _venv_python(fake_bundle)
    assert bundle.bundle_available() is False


def test_bundle_available_false_without_python(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text("{}", encoding="utf-8")
    assert bundle.bundle_available() is False


def test_bundle_available_true_when_complete(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text("{}", encoding="utf-8")
    _venv_python(fake_bundle)
    assert bundle.bundle_available() is True


def test_resolve_python_prefers_bundle(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text("{}", encoding="utf-8")
    expected = _venv_python(fake_bundle)
    assert bundle.resolve_python() == expected


def test_resolve_python_raises_when_nothing(fake_bundle: Path) -> None:
    with pytest.raises(FileNotFoundError):
        bundle.resolve_python()


def test_resolve_uv_falls_back_to_path(fake_bundle: Path) -> None:
    assert bundle.resolve_uv() == "uv"


def test_resolve_uv_uses_bundled_binary(fake_bundle: Path) -> None:
    bin_dir = fake_bundle / "bin"
    bin_dir.mkdir()
    name = "uv.exe" if sys.platform == "win32" else "uv"
    bundled = bin_dir / name
    bundled.write_text("", encoding="utf-8")
    assert bundle.resolve_uv() == str(bundled)


def test_resolve_livekit_binary_none_when_absent(fake_bundle: Path) -> None:
    assert bundle.resolve_livekit_binary() is None


def test_resolve_livekit_binary_from_manifest(fake_bundle: Path) -> None:
    rel = "bin/livekit-server.exe" if sys.platform == "win32" else "bin/livekit-server"
    target = fake_bundle / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    (fake_bundle / "manifest.json").write_text(
        json.dumps({"bin": {"livekit": rel}}), encoding="utf-8"
    )
    assert bundle.resolve_livekit_binary() == target


def test_prerequisites_status_shape(fake_bundle: Path) -> None:
    (fake_bundle / "manifest.json").write_text(
        json.dumps({"version": "9"}), encoding="utf-8"
    )
    _venv_python(fake_bundle)
    status = bundle.prerequisites_status()
    assert status["bundle"] is True
    assert status["bundle_version"] == "9"
    assert status["python"] is True
    assert status["yolo_model"] is False
    assert status["piper_model"] is False
    assert status["offline_ready"] is False
    for key in ("platform", "python_path", "livekit_binary", "livekit_path"):
        assert key in status


def test_stage_models_noop_without_bundle(fake_bundle: Path) -> None:
    assert bundle.stage_models_from_bundle() == []
