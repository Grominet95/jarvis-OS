"""Tests unitaires de kernel.setup_layout (lecture .env + detection setup)."""

from __future__ import annotations

from pathlib import Path

from jarvis.kernel.setup_layout import is_setup_complete, read_env_file


def _write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding)


def test_read_env_file_missing_returns_empty(tmp_path: Path) -> None:
    assert read_env_file(tmp_path / "absent.env") == {}


def test_read_env_file_parses_key_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "FOO=bar\nBAZ=qux\n")
    result = read_env_file(env)
    assert result == {"FOO": "bar", "BAZ": "qux"}


def test_read_env_file_skips_comments_and_blanks(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "# comment\n\nFOO=bar\n   \n# another\nBAZ=qux\n")
    assert read_env_file(env) == {"FOO": "bar", "BAZ": "qux"}


def test_read_env_file_ignores_lines_without_equals(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "FOO=bar\nNOT_A_PAIR\nBAZ=qux\n")
    assert read_env_file(env) == {"FOO": "bar", "BAZ": "qux"}


def test_read_env_file_strips_whitespace(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "  FOO = bar  \n")
    assert read_env_file(env) == {"FOO": "bar"}


def test_read_env_file_handles_utf8_bom(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "FOO=bar\n", encoding="utf-8-sig")
    assert read_env_file(env) == {"FOO": "bar"}


def test_read_env_file_keeps_equals_in_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "TOKEN=a=b=c\n")
    assert read_env_file(env) == {"TOKEN": "a=b=c"}


def test_is_setup_complete_false_when_no_firstname(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "API_BACKEND=openai\nOPENAI_API_KEY=sk-test\n")
    assert is_setup_complete(env) is False


def test_is_setup_complete_openai_requires_openai_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "USER_FIRSTNAME=Max\nAPI_BACKEND=openai\nOPENAI_API_KEY=\n")
    assert is_setup_complete(env) is False


def test_is_setup_complete_openai_ok(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "USER_FIRSTNAME=Max\nAPI_BACKEND=openai\nOPENAI_API_KEY=sk-test\n")
    assert is_setup_complete(env) is True


def test_is_setup_complete_anthropic_requires_anthropic_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "USER_FIRSTNAME=Max\nAPI_BACKEND=anthropic\nANTHROPIC_API_KEY=\n")
    assert is_setup_complete(env) is False


def test_is_setup_complete_anthropic_ok(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "USER_FIRSTNAME=Max\nAPI_BACKEND=anthropic\nANTHROPIC_API_KEY=sk-ant\n")
    assert is_setup_complete(env) is True


def test_is_setup_complete_defaults_to_anthropic_backend(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    _write(env, "USER_FIRSTNAME=Max\nANTHROPIC_API_KEY=sk-ant\n")
    assert is_setup_complete(env) is True


def test_is_setup_complete_missing_file(tmp_path: Path) -> None:
    assert is_setup_complete(tmp_path / "absent.env") is False
