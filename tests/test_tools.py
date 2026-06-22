# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ── Fixture : active la permission fichiers pour ce module ────────────────────


@pytest.fixture(autouse=True)
def _enable_files_permission() -> Generator[None, None, None]:
    """Active files=True avant chaque test, restaure False après.

    Les outils filesystem refusent si files=False (défaut sécurité).
    Les tests qui vérifient un REFUS de PATH doivent passer avec files=True
    pour obtenir le bon message d'erreur (chemin hors racine, pas permissions).
    """
    from jarvis.kernel.permissions import permissions

    permissions.set("files", True)
    yield
    permissions.set("files", False)


# ── ToolResult / base ─────────────────────────────────────────


def test_tool_result_defaults() -> None:
    from jarvis.capabilities.tools.base import ToolResult

    r = ToolResult(content="ok")
    assert r.content == "ok"
    assert not r.is_error


def test_tool_to_claude_schema() -> None:
    from jarvis.capabilities.tools.base import Tool, ToolResult

    class _DummyTool(Tool):
        name = "dummy"
        description = "A dummy tool"
        input_schema = {"type": "object", "properties": {}, "required": []}

        async def execute(self, **_: object) -> ToolResult:
            return ToolResult(content="done")

    schema = _DummyTool().to_claude_schema()
    assert schema["name"] == "dummy"
    assert "input_schema" in schema


# ── ToolRegistry ──────────────────────────────────────────────


async def test_registry_dispatch() -> None:
    from jarvis.capabilities.tools.base import Tool, ToolResult
    from jarvis.capabilities.tools.registry import ToolRegistry

    class _EchoTool(Tool):
        name = "echo"
        description = "Echo"
        input_schema = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

        async def execute(self, text: str, **_: object) -> ToolResult:
            return ToolResult(content=text)

    registry = ToolRegistry()
    registry.register(_EchoTool())

    result = await registry.call("echo", {"text": "hello"})
    assert result.content == "hello"
    assert not result.is_error


async def test_registry_unknown_tool() -> None:
    from jarvis.capabilities.tools.registry import ToolRegistry

    registry = ToolRegistry()
    result = await registry.call("nonexistent", {})
    assert result.is_error
    assert "inconnu" in result.content


async def test_registry_call_str() -> None:
    from jarvis.capabilities.tools.base import Tool, ToolResult
    from jarvis.capabilities.tools.registry import ToolRegistry

    class _OkTool(Tool):
        name = "ok"
        description = "Ok"
        input_schema = {"type": "object", "properties": {}, "required": []}

        async def execute(self, **_: object) -> ToolResult:
            return ToolResult(content="résultat")

    registry = ToolRegistry()
    registry.register(_OkTool())
    text = await registry.call_str("ok", {})
    assert text == "résultat"


async def test_registry_call_str_error() -> None:
    from jarvis.capabilities.tools.registry import ToolRegistry

    registry = ToolRegistry()
    text = await registry.call_str("unknown", {})
    assert text.startswith("[ERREUR]")


# ── WeatherTool ───────────────────────────────────────────────


async def test_weather_tool_success() -> None:
    from jarvis.capabilities.tools.weather import WeatherTool

    tool = WeatherTool()
    mock_response = MagicMock()
    mock_response.text = "Paris: ⛅ +15°C"
    mock_response.raise_for_status = MagicMock()

    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    mock_instance.get = AsyncMock(return_value=mock_response)

    with patch("jarvis.capabilities.tools.weather.httpx.AsyncClient", return_value=mock_instance):
        result = await tool.execute(city="Paris")

    assert not result.is_error
    assert "Paris" in result.content


async def test_weather_tool_http_error() -> None:
    from jarvis.capabilities.tools.weather import WeatherTool

    tool = WeatherTool()
    mock_instance = AsyncMock()
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    mock_instance.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))

    with patch("jarvis.capabilities.tools.weather.httpx.AsyncClient", return_value=mock_instance):
        result = await tool.execute(city="NowhereLand")

    assert result.is_error
    assert "indisponible" in result.content


# ── ReadFileTool ──────────────────────────────────────────────


async def test_read_file_success(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import ReadFileTool

    tool = ReadFileTool(allowed_roots=[tmp_path])
    f = tmp_path / "hello.txt"
    f.write_text("Bonjour Barth")

    result = await tool.execute(path=str(f))
    assert not result.is_error
    assert result.content == "Bonjour Barth"


async def test_read_file_access_denied(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import ReadFileTool

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool = ReadFileTool(allowed_roots=[allowed])

    outside = tmp_path / "secret.txt"
    outside.write_text("classified")

    result = await tool.execute(path=str(outside))
    assert result.is_error
    assert "refusé" in result.content


async def test_read_file_not_found(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import ReadFileTool

    tool = ReadFileTool(allowed_roots=[tmp_path])
    result = await tool.execute(path=str(tmp_path / "ghost.txt"))
    assert result.is_error


async def test_read_file_too_large(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import _MAX_FILE_SIZE, ReadFileTool

    tool = ReadFileTool(allowed_roots=[tmp_path])
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (_MAX_FILE_SIZE + 1))

    result = await tool.execute(path=str(big))
    assert result.is_error
    assert "grand" in result.content


# ── FindFilesTool ─────────────────────────────────────────────


async def test_find_files_success(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import FindFilesTool

    tool = FindFilesTool(allowed_roots=[tmp_path])
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "b.py").write_text("# b")
    (tmp_path / "c.txt").write_text("text")

    result = await tool.execute(pattern="*.py", directory=str(tmp_path))
    assert not result.is_error
    assert "a.py" in result.content
    assert "b.py" in result.content
    assert "c.txt" not in result.content


async def test_find_files_no_results(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import FindFilesTool

    tool = FindFilesTool(allowed_roots=[tmp_path])
    result = await tool.execute(pattern="*.rs", directory=str(tmp_path))
    assert not result.is_error
    assert "Aucun" in result.content


async def test_find_files_access_denied(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.filesystem import FindFilesTool

    allowed = tmp_path / "zone"
    allowed.mkdir()
    tool = FindFilesTool(allowed_roots=[allowed])

    result = await tool.execute(pattern="*.py", directory=str(tmp_path))
    assert result.is_error


# ── CLIRunnerTool ─────────────────────────────────────────────


async def test_cli_runner_success(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.cli import CLIRunnerTool

    yaml_path = tmp_path / "tools.yaml"
    yaml_path.write_text('echo_test:\n  command: ["echo", "hello jarvis"]\n  description: "Test"\n')
    tool = CLIRunnerTool(whitelist_path=yaml_path)
    result = await tool.execute(alias="echo_test")

    assert not result.is_error
    assert "hello jarvis" in result.content


async def test_cli_runner_unknown_alias(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.cli import CLIRunnerTool

    yaml_path = tmp_path / "tools.yaml"
    yaml_path.write_text("{}")
    tool = CLIRunnerTool(whitelist_path=yaml_path)

    result = await tool.execute(alias="nonexistent")
    assert result.is_error
    assert "inconnu" in result.content


async def test_cli_runner_no_whitelist(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.cli import CLIRunnerTool

    tool = CLIRunnerTool(whitelist_path=tmp_path / "missing.yaml")
    result = await tool.execute(alias="anything")
    assert result.is_error


async def test_cli_runner_with_args(tmp_path: Path) -> None:
    from jarvis.capabilities.tools.cli import CLIRunnerTool

    yaml_path = tmp_path / "tools.yaml"
    yaml_path.write_text('greet:\n  command: ["echo"]\n  description: "Greet"\n')
    tool = CLIRunnerTool(whitelist_path=yaml_path)

    result = await tool.execute(alias="greet", args=["Barth"])
    assert not result.is_error
    assert "Barth" in result.content
