# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import pytest

from jarvis.engine.router import RouteEnum, SpeedRouter

# ── strip_tag (sync) ──────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[I] Il est 14h23.", "Il est 14h23."),
        ("[CF] Mode Batman, chef.", "Mode Batman, chef."),
        ("[BG] Ok, je lance ça.", "Ok, je lance ça."),
        ("Pas de tag.", "Pas de tag."),
        ("[I]Sans espace.", "Sans espace."),
        ("[I]  Double espace.", " Double espace."),
    ],
)
def test_strip_tag_sync(raw: str, expected: str) -> None:
    assert SpeedRouter.strip_tag(raw) == expected


# ── extract_route (async stream) ─────────────────────────────


async def _collect_route(chunks: list[str]) -> tuple[RouteEnum, str]:
    async def _gen() -> RouteEnum:  # type: ignore[valid-type]
        for c in chunks:
            yield c

    route, stream = await SpeedRouter.extract_route(_gen())
    return route, "".join([c async for c in stream])


async def test_strip_tag_stream_single_chunk() -> None:
    route, result = await _collect_route(["[I] Bonjour chef."])
    assert route == RouteEnum.INSTANT
    assert result == "Bonjour chef."


async def test_strip_tag_stream_tag_split_across_chunks() -> None:
    route, result = await _collect_route(["[I", "] Bonjour chef."])
    assert route == RouteEnum.INSTANT
    assert result == "Bonjour chef."


async def test_strip_tag_stream_tag_and_space_split() -> None:
    route, result = await _collect_route(["[CF]", " Mode Batman, chef."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert result == "Mode Batman, chef."


async def test_strip_tag_stream_no_tag() -> None:
    route, result = await _collect_route(["Bonne", " question."])
    assert route == RouteEnum.INSTANT
    assert result == "Bonne question."


async def test_strip_tag_stream_bg() -> None:
    route, result = await _collect_route(["[BG] Ok, ", "je lance ça."])
    assert route == RouteEnum.BACKGROUND
    assert result == "Ok, je lance ça."
