# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[.!?])$")
MAX_TOKENS_WITHOUT_FLUSH = 8


def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases non vides."""
    parts = SENTENCE_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


class StreamChunker:
    """Accumule les tokens LLM et yield des phrases complètes dès détection.

    Flush également si le buffer dépasse MAX_TOKENS_WITHOUT_FLUSH sans ponctuation,
    pour éviter d'attendre sur les réponses courtes sans point final.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._token_count = 0

    def feed(self, token: str) -> list[str]:
        """Reçoit un token, retourne les phrases complètes disponibles."""
        self._buffer += token
        self._token_count += 1
        sentences: list[str] = []

        while True:
            match = SENTENCE_END.search(self._buffer)
            if not match:
                break
            sentence = self._buffer[: match.start() + 1].strip()
            self._buffer = self._buffer[match.end() :]
            self._token_count = 0
            if sentence:
                sentences.append(sentence)

        # Flush si trop de tokens sans ponctuation (ex: "C'est parti mon reuf")
        if self._token_count >= MAX_TOKENS_WITHOUT_FLUSH and self._buffer.strip():
            sentences.append(self._buffer.strip())
            self._buffer = ""
            self._token_count = 0

        return sentences

    def flush(self) -> str | None:
        """Retourne le reste du buffer (fin sans ponctuation finale)."""
        remainder = self._buffer.strip()
        self._buffer = ""
        self._token_count = 0
        return remainder if remainder else None
