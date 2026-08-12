# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Garde-fou : le retry Anthropic ne doit jamais rejouer un flux déjà émis.

Le retry sur erreur transitoire (429/5xx/réseau) est correct tant que rien n'a
été envoyé à l'appelant. Dès qu'un token est parti, il est irrécupérable : le
rejeu réémettrait le début de la réponse par-dessus et l'utilisateur lirait le
texte en double. Ces tests exercent les deux côtés de cette frontière.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import anthropic
import pytest

from jarvis.providers.llm.api import AnthropicProvider


def _status_error(status_code: int) -> anthropic.APIStatusError:
    """Erreur transitoire : 529 fait partie de _ANTHROPIC_RETRY_STATUS."""
    return anthropic.APIStatusError(
        "overloaded",
        response=SimpleNamespace(  # type: ignore[arg-type]
            request=SimpleNamespace(), status_code=status_code, headers={}
        ),
        body=None,
    )


class _FakeStream:
    """Imite `client.messages.stream(...)` : context manager async + text_stream."""

    def __init__(self, chunks: list[str], raise_after: int | None) -> None:
        self._chunks = chunks
        self._raise_after = raise_after

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            for i, c in enumerate(self._chunks):
                if self._raise_after is not None and i == self._raise_after:
                    raise _status_error(529)
                yield c
            if self._raise_after is not None and self._raise_after >= len(self._chunks):
                raise _status_error(529)

        return _gen()


class _FakeMessages:
    def __init__(self, attempts: list[_FakeStream]) -> None:
        self._attempts = attempts
        self.call_count = 0

    def stream(self, **_kwargs: object) -> _FakeStream:
        attempt = self._attempts[min(self.call_count, len(self._attempts) - 1)]
        self.call_count += 1
        return attempt


def _provider(attempts: list[_FakeStream]) -> tuple[AnthropicProvider, _FakeMessages]:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    messages = _FakeMessages(attempts)
    provider._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    provider._model = "claude-test"
    provider._max_tokens = 128
    provider._tracker = None
    return provider, messages


async def test_pas_de_retry_une_fois_un_chunk_emis() -> None:
    """Échec APRÈS le premier token : l'erreur remonte, aucun texte dupliqué."""
    attempts = [
        # 1re tentative : émet "Bonjour" puis casse.
        _FakeStream(["Bonjour", " Barth"], raise_after=1),
        # Ne doit jamais être consommée.
        _FakeStream(["Bonjour", " Barth"], raise_after=None),
    ]
    provider, messages = _provider(attempts)

    received: list[str] = []
    with pytest.raises(anthropic.APIStatusError):
        async for chunk in provider._stream({}):
            received.append(chunk)

    assert received == ["Bonjour"], "le flux ne doit pas être rejoué"
    assert messages.call_count == 1, "aucune seconde requête après un token émis"


async def test_retry_si_echec_avant_tout_chunk() -> None:
    """Échec AVANT le premier token : le retry reste légitime et transparent."""
    attempts = [
        _FakeStream([], raise_after=0),
        _FakeStream(["Bonjour", " Barth"], raise_after=None),
    ]
    provider, messages = _provider(attempts)

    received = [chunk async for chunk in provider._stream({})]

    assert received == ["Bonjour", " Barth"]
    assert messages.call_count == 2, "la seconde tentative doit avoir eu lieu"
