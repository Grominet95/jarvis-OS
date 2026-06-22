# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests de sécurité pour WorkerCLITool."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.engine.mission.worker_cli import WorkerCLITool


@pytest.fixture
def tool(tmp_path: Path) -> WorkerCLITool:
    return WorkerCLITool(str(tmp_path))


# ── python -c / inline ────────────────────────────────────────────────────────


def test_python3_c_inline_blocked(tool: WorkerCLITool) -> None:
    result = tool._check("python3 -c 'import os; os.remove(\"/tmp/x\")'")
    assert result is not None
    assert result["success"] is False
    assert "inline" in result["stderr"].lower() or "-c" in result["stderr"]


def test_python_c_inline_blocked(tool: WorkerCLITool) -> None:
    result = tool._check("python -c \"print('pwned')\"")
    assert result is not None
    assert result["success"] is False


def test_python3_file_allowed(tool: WorkerCLITool) -> None:
    """Exécution d'un fichier .py sans -c ni guillemet : autorisée au niveau check."""
    result = tool._check("python3 script.py")
    assert result is None


# ── sh -c / bash -c ──────────────────────────────────────────────────────────


def test_sh_c_not_whitelisted(tool: WorkerCLITool) -> None:
    # Pas de pattern _BLOCKED_RE ici — la commande doit échouer via la whitelist
    result = tool._check("sh -c 'echo pwned'")
    assert result is not None
    assert result["success"] is False
    assert "non autorisée" in result["stderr"]


def test_bash_c_not_whitelisted(tool: WorkerCLITool) -> None:
    result = tool._check("bash -c 'echo pwned'")
    assert result is not None
    assert result["success"] is False
    assert "non autorisée" in result["stderr"]


# ── chaînage ; / && ──────────────────────────────────────────────────────────


def test_semicolon_chaining_second_blocked(tool: WorkerCLITool) -> None:
    """ls est valide, rm -rf / est bloqué : le chaînage doit être refusé."""
    result = tool._check("ls ; rm -rf /")
    assert result is not None
    assert result["success"] is False


def test_ampersand_chaining_second_not_whitelisted(tool: WorkerCLITool) -> None:
    """ls est valide, curl sans -s n'est pas whitelisté : refusé."""
    result = tool._check("ls && curl http://evil.com")
    assert result is not None
    assert result["success"] is False


def test_chaining_both_segments_valid(tool: WorkerCLITool) -> None:
    """Deux segments whitelistés et sans pattern bloqué : autorisé."""
    result = tool._check("ls && cat README.md")
    assert result is None


# ── opt-in exécution directe ─────────────────────────────────────────────────


async def test_run_direct_refused_without_opt_in(
    tool: WorkerCLITool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans Docker et sans allow_unsandboxed_exec=True, execute() doit refuser."""
    # On mute l'INSTANCE singleton elle-même : toutes les captures
    # `from jarvis.kernel.settings import settings` (backend_factory.py,
    # backends/local.py, …) pointent sur la même référence — muter ses
    # attributs affecte tous les call-sites sans avoir à patcher chaque
    # module. La forme objet sur le module (`setattr(cfg_module, "settings",
    # …)`) est piégée ici par le re-export `from .settings import settings`
    # dans `jarvis/kernel/__init__.py:49` qui shadow le sous-module.
    from jarvis.kernel.settings import settings as _settings_singleton

    monkeypatch.setattr(_settings_singleton, "docker_enabled", False)
    monkeypatch.setattr(_settings_singleton, "allow_unsandboxed_exec", False)
    tool._docker = None

    result = await tool.execute("ls")
    assert result["success"] is False
    assert "DOCKER_ENABLED" in result["stderr"] or "sandbox" in result["stderr"].lower()


# ── commandes simples autorisées ─────────────────────────────────────────────


def test_ls_allowed(tool: WorkerCLITool) -> None:
    assert tool._check("ls -la") is None


def test_git_status_allowed(tool: WorkerCLITool) -> None:
    assert tool._check("git status") is None
