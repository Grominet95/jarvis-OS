"""Tests unitaires de capabilities.skills._mapping (mapping outils OpenClaw)."""

from __future__ import annotations

import pytest

from jarvis.capabilities.skills._mapping import TOOL_MAP, UNSUPPORTED, resolve_tool


@pytest.mark.parametrize(
    ("openclaw", "expected"),
    [
        ("exec", "run_script"),
        ("cli", "run_script"),
        ("web_search", "browser"),
        ("browser", "browser"),
        ("read_file", "filesystem"),
        ("calendar", "calendar_list"),
        ("notion", "notion_tasks"),
        ("weather", "weather"),
    ],
)
def test_resolve_known_tools(openclaw: str, expected: str) -> None:
    assert resolve_tool(openclaw) == expected


@pytest.mark.parametrize("tool", sorted(UNSUPPORTED))
def test_resolve_unsupported_returns_none(tool: str) -> None:
    assert resolve_tool(tool) is None


def test_resolve_unknown_returns_none() -> None:
    assert resolve_tool("totally_unknown_tool") is None


def test_tool_map_values_are_strings() -> None:
    assert all(isinstance(v, str) and v for v in TOOL_MAP.values())


def test_unsupported_and_map_are_disjoint() -> None:
    assert UNSUPPORTED.isdisjoint(TOOL_MAP.keys())
