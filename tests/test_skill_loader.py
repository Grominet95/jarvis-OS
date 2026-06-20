"""Tests unitaires de capabilities.skills._loader (parsing SKILL.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.capabilities.skills._loader import (
    _check_requirements,
    _parse_skill_md,
    load_skills,
)

_VALID = """---
name: demo
description: Une skill de demonstration
---
Voici les instructions.
Multi-lignes.
"""


def _make_skill(root: Path, folder: str, content: str) -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(content, encoding="utf-8")
    return md


def test_parse_valid_skill(tmp_path: Path) -> None:
    md = _make_skill(tmp_path, "demo", _VALID)
    parsed = _parse_skill_md(md)
    assert parsed is not None
    assert parsed["name"] == "demo"
    assert parsed["description"] == "Une skill de demonstration"
    assert "instructions" in parsed["instructions"].lower() or parsed["instructions"]
    assert parsed["instructions"].startswith("Voici les instructions.")


def test_parse_missing_file_returns_none(tmp_path: Path) -> None:
    assert _parse_skill_md(tmp_path / "nope" / "SKILL.md") is None


def test_parse_without_frontmatter_returns_none(tmp_path: Path) -> None:
    md = _make_skill(tmp_path, "raw", "Pas de frontmatter ici.")
    assert _parse_skill_md(md) is None


def test_parse_invalid_yaml_returns_none(tmp_path: Path) -> None:
    bad = "---\nname: [unclosed\n---\nbody\n"
    md = _make_skill(tmp_path, "bad", bad)
    assert _parse_skill_md(md) is None


def test_parse_name_defaults_to_folder(tmp_path: Path) -> None:
    content = "---\ndescription: sans nom\n---\nbody\n"
    md = _make_skill(tmp_path, "myfolder", content)
    parsed = _parse_skill_md(md)
    assert parsed is not None
    assert parsed["name"] == "myfolder"


def test_check_requirements_no_openclaw_block() -> None:
    ok, reason = _check_requirements({})
    assert ok is True
    assert reason == ""


def test_check_requirements_os_filter_rejects() -> None:
    meta = {"metadata": {"openclaw": {"os": ["nonexistent-os"]}}}
    ok, reason = _check_requirements(meta)
    assert ok is False
    assert "non support" in reason.lower()


def test_check_requirements_missing_binary() -> None:
    meta = {"metadata": {"openclaw": {"requires": {"bins": ["definitely-not-a-real-bin-xyz"]}}}}
    ok, reason = _check_requirements(meta)
    assert ok is False
    assert "manquant" in reason.lower()


def test_check_requirements_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_REQUIRED_KEY_XYZ", raising=False)
    meta = {"metadata": {"openclaw": {"requires": {"config": ["SOME_REQUIRED_KEY_XYZ"]}}}}
    ok, reason = _check_requirements(meta)
    assert ok is False
    assert "env" in reason.lower()


def test_load_skills_empty_dir(tmp_path: Path) -> None:
    assert load_skills(tmp_path / "absent") == []


def test_load_skills_collects_valid(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo", _VALID)
    skills = load_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0]["name"] == "demo"


def test_load_skills_ignores_underscore_folders(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo", _VALID)
    _make_skill(tmp_path, "_internal", _VALID)
    skills = load_skills(tmp_path)
    names = {s["name"] for s in skills}
    assert "demo" in names
    assert all(not s["dir"].name.startswith("_") for s in skills)
