# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import pytest

from jarvis.engine.router import RouteEnum, SpeedRouter

# ── heuristic ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Quelle heure est-il ?", RouteEnum.INSTANT),
        ("Qu'est-ce que tu penses de ça ?", RouteEnum.INSTANT),
        ("Allume la lumière du salon.", RouteEnum.CONFIRM_FIRE),
        ("Éteins le thermostat.", RouteEnum.CONFIRM_FIRE),
        ("Lance un minuteur de 10 minutes.", RouteEnum.CONFIRM_FIRE),
        ("Mémorise que j'ai rendez-vous demain.", RouteEnum.CONFIRM_FIRE),
        ("Ouvre le volet de la chambre.", RouteEnum.CONFIRM_FIRE),
    ],
)
def test_heuristic(message: str, expected: RouteEnum) -> None:
    assert SpeedRouter.heuristic(message) == expected


# ── strip_tag ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[I] Réponse directe.", "Réponse directe."),
        ("[CF] Je confirme.", "Je confirme."),
        ("[BG] Ok je lance.", "Ok je lance."),
        ("Pas de tag.", "Pas de tag."),
    ],
)
def test_strip_tag(raw: str, expected: str) -> None:
    assert SpeedRouter.strip_tag(raw) == expected


# ── extract_route ─────────────────────────────────────────────


async def _extract(
    chunks: list[str],
    pre_route: RouteEnum = RouteEnum.INSTANT,
) -> tuple[RouteEnum, str]:
    async def _gen() -> RouteEnum:  # type: ignore[valid-type]
        for c in chunks:
            yield c

    route, stream = await SpeedRouter.extract_route(_gen(), pre_route=pre_route)
    return route, "".join([c async for c in stream])


# ── cas nominaux (existants) ──────────────────────────────────


async def test_extract_route_instant_single() -> None:
    route, text = await _extract(["[I] Il est 14h23."])
    assert route == RouteEnum.INSTANT
    assert text == "Il est 14h23."


async def test_extract_route_cf_single() -> None:
    route, text = await _extract(["[CF] Lumière allumée."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert text == "Lumière allumée."


async def test_extract_route_bg_single() -> None:
    route, text = await _extract(["[BG] Je lance la recherche."])
    assert route == RouteEnum.BACKGROUND
    assert text == "Je lance la recherche."


async def test_extract_route_tag_split() -> None:
    route, text = await _extract(["[CF", "] Mode nuit activé."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert text == "Mode nuit activé."


async def test_extract_route_tag_and_space_split() -> None:
    route, text = await _extract(["[BG]", " Tâche soumise."])
    assert route == RouteEnum.BACKGROUND
    assert text == "Tâche soumise."


async def test_extract_route_no_tag() -> None:
    route, text = await _extract(["Bonjour", " chef."])
    assert route == RouteEnum.INSTANT
    assert text == "Bonjour chef."


async def test_extract_route_multi_chunks() -> None:
    route, text = await _extract(["[I] ", "Il est ", "14h."])
    assert route == RouteEnum.INSTANT
    assert text == "Il est 14h."


# ── nouveaux cas : préambule avant le tag ─────────────────────


async def test_extract_route_tag_after_short_preamble() -> None:
    """Tag précédé d'un court préambule dans le même chunk."""
    route, text = await _extract(["Voici : [CF] Lumière allumée."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert "Lumière allumée." in text


async def test_extract_route_tag_after_long_preamble_same_chunk() -> None:
    """Préambule ~40 caractères avant le tag — fenêtre de 80 chars."""
    preamble = "Bien sûr, je m'en occupe tout de suite. "
    assert len(preamble) < 80
    route, text = await _extract([preamble + "[CF] Lumière allumée."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert "Lumière allumée." in text


async def test_extract_route_tag_in_second_chunk_after_preamble() -> None:
    """Préambule dans le premier chunk, tag en début du second."""
    route, text = await _extract(["Bien sûr, voici : ", "[CF] Lumière allumée."])
    assert route == RouteEnum.CONFIRM_FIRE
    assert "Lumière allumée." in text


async def test_extract_route_bg_project_after_preamble() -> None:
    """Tag BG:PROJECT détecté après préambule (priorité sur BG simple)."""
    route, text = await _extract(["Lancement : [BG:PROJECT] Projet démarré."])
    assert route == RouteEnum.PROJECT
    assert "Projet démarré." in text


# ── nouveaux cas : fallback pre_route CF ─────────────────────


async def test_extract_route_no_tag_cf_fallback() -> None:
    """Absence de tag + pre_route=CF → route CF conservée, texte intact."""
    route, text = await _extract(
        ["Lumière allumée maintenant."],
        pre_route=RouteEnum.CONFIRM_FIRE,
    )
    assert route == RouteEnum.CONFIRM_FIRE
    assert text == "Lumière allumée maintenant."


async def test_extract_route_no_tag_instant_default() -> None:
    """Absence de tag + pre_route=INSTANT (défaut) → route INSTANT."""
    route, text = await _extract(["Bonjour, comment puis-je vous aider ?"])
    assert route == RouteEnum.INSTANT
    assert "Bonjour" in text


async def test_extract_route_explicit_tag_overrides_pre_route() -> None:
    """Tag explicite [I] prévaut même si pre_route=CF."""
    route, text = await _extract(
        ["[I] Simple réponse."],
        pre_route=RouteEnum.CONFIRM_FIRE,
    )
    assert route == RouteEnum.INSTANT
    assert text == "Simple réponse."


async def test_extract_route_no_tag_bg_pre_route_falls_to_instant() -> None:
    """pre_route=BG sans tag → INSTANT (le fallback ne s'active que pour CF)."""
    route, _ = await _extract(
        ["Réponse sans tag."],
        pre_route=RouteEnum.BACKGROUND,
    )
    assert route == RouteEnum.INSTANT
