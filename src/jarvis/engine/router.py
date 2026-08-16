# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from enum import StrEnum

from loguru import logger

from jarvis.kernel.error_collector import collector  # jrv: autofix


class RouteEnum(StrEnum):
    INSTANT = "I"
    CONFIRM_FIRE = "CF"
    BACKGROUND = "BG"
    PROJECT = "BG:PROJECT"


# BG:PROJECT doit être testé AVANT BG pour éviter le match partiel.
_TAG_RE = re.compile(r"^\[(I|CF|BG:PROJECT|BG)\]\s?")

# Variante sans ancre — cherche le tag n'importe où dans la fenêtre de buffer.
_TAG_SEARCH_RE = re.compile(r"\[(I|CF|BG:PROJECT|BG)\]\s?")

# Filtre les tags routing inconnus courts (ex: [C], [A], [X]…)
# Ne pas matcher [MINDMAP], [/MINDMAP] ou tout tag > 3 lettres
_ANY_TAG_RE = re.compile(r"^\[[A-Z]{1,3}(?::[A-Z]+)?\]\s?")

# Mots-clés domotiques / actions → pré-route CONFIRM_FIRE.
_CF_PATTERNS = re.compile(
    r"\b(allume|éteins|lumière|lampe|thermostat|minuteur|timer|rappel|note|"
    r"souviens|mémorise|programme|règle|lance|démarre|arrête|ouvre|ferme)\b",
    re.IGNORECASE,
)


class SpeedRouter:
    """Heuristique de pré-routing + extraction du tag LLM depuis un stream.

    Phase C : aucun constructeur — toutes les méthodes sont `@staticmethod`,
    pas d'état, pas de dépendance externe. Aucune injection nécessaire.
    Le router est instancié indirectement via ses méthodes statiques
    (`SpeedRouter.extract_route(...)`) — pas via Container.
    """

    @staticmethod
    def heuristic(message: str) -> RouteEnum:
        """Pré-classe la requête avant l'appel LLM. INSTANT par défaut."""
        if _CF_PATTERNS.search(message):
            return RouteEnum.CONFIRM_FIRE
        return RouteEnum.INSTANT

    @staticmethod
    def strip_tag(text: str) -> str:
        """Retire le tag de routing d'une réponse complète (non-stream)."""
        return _TAG_RE.sub("", text)

    @staticmethod
    async def extract_route(
        stream: AsyncIterator[str],
        pre_route: RouteEnum = RouteEnum.INSTANT,
    ) -> tuple[RouteEnum, AsyncIterator[str]]:
        """Lit le tag du début du stream et retourne (route, stream nettoyé).

        Bufferise jusqu'à voir ']', la première fin de ligne, ou ~80 caractères.
        Cherche d'abord le tag en début de buffer (comportement nominal), puis
        dans l'ensemble de la fenêtre si un préambule précède le tag.

        Si aucun tag n'est trouvé et que pre_route vaut CONFIRM_FIRE, le route
        CF est conservé (avec warning) plutôt que de tomber silencieusement en
        INSTANT — ce qui désactiverait les actions domotiques.
        """
        buffer = ""
        async for chunk in stream:
            buffer += chunk
            if "]" in buffer or "\n" in buffer or len(buffer) >= 80:
                break

        # Essai 1 : tag strictement en début de buffer (cas nominal).
        match = _TAG_RE.match(buffer)
        if match:
            tag = match.group(1)
            try:
                route = RouteEnum(tag)
            except ValueError:
                collector.error("JRV-ENG-000", "JRV-ENG-000")
                route = RouteEnum.INSTANT
            prefix = ""
            stripped = _TAG_RE.sub("", buffer)
            tag_consumed_all = not stripped
        else:
            # Essai 2 : tag dans la fenêtre après un éventuel préambule.
            search = _TAG_SEARCH_RE.search(buffer)
            if search:
                tag = search.group(1)
                try:
                    route = RouteEnum(tag)
                except ValueError:
                    collector.error("JRV-ENG-000", "JRV-ENG-000")
                    route = RouteEnum.INSTANT
                prefix = buffer[: search.start()]
                stripped = buffer[search.end() :]
                tag_consumed_all = not stripped
            else:
                # Aucun tag — fallback sur pre_route si CF, sinon INSTANT.
                if pre_route is RouteEnum.CONFIRM_FIRE:
                    logger.warning("SpeedRouter: tag absent — fallback sur pre_route CF")
                    route = RouteEnum.CONFIRM_FIRE
                else:
                    route = RouteEnum.INSTANT
                prefix = ""
                stripped = _ANY_TAG_RE.sub("", buffer)
                tag_consumed_all = not stripped

        logger.debug("SpeedRouter", route=route.value)

        async def _tail() -> AsyncIterator[str]:
            if prefix:
                yield prefix
            lstrip_next = tag_consumed_all and not prefix
            if stripped:
                yield stripped
            async for chunk in stream:
                if lstrip_next:
                    chunk = chunk.lstrip(" ")
                    lstrip_next = not chunk
                if chunk:
                    yield chunk

        return route, _tail()
