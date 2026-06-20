"""Tests unitaires de providers.audio.chunker (decoupage de phrases streaming)."""

from __future__ import annotations

from jarvis.providers.audio.chunker import (
    MAX_TOKENS_WITHOUT_FLUSH,
    StreamChunker,
    split_sentences,
)


def test_split_sentences_basic() -> None:
    assert split_sentences("Bonjour. Comment vas-tu ?") == ["Bonjour.", "Comment vas-tu ?"]


def test_split_sentences_strips_and_drops_empty() -> None:
    assert split_sentences("   ") == []


def test_split_sentences_single_no_punctuation() -> None:
    assert split_sentences("salut le monde") == ["salut le monde"]


def test_split_sentences_multiple_terminators() -> None:
    assert split_sentences("Ah ! Vraiment ? Oui.") == ["Ah !", "Vraiment ?", "Oui."]


def test_chunker_yields_complete_sentence() -> None:
    c = StreamChunker()
    assert c.feed("Bonjour") == []
    out = c.feed(". ")
    assert out == ["Bonjour."]


def test_chunker_accumulates_then_flushes_remainder() -> None:
    c = StreamChunker()
    c.feed("Une phrase sans fin")
    assert c.flush() == "Une phrase sans fin"
    assert c.flush() is None


def test_chunker_flush_resets_buffer() -> None:
    c = StreamChunker()
    c.feed("Reste")
    assert c.flush() == "Reste"
    assert c.feed("Nouveau.") == ["Nouveau."]


def test_chunker_force_flush_after_max_tokens() -> None:
    c = StreamChunker()
    out: list[str] = []
    for _ in range(MAX_TOKENS_WITHOUT_FLUSH):
        out += c.feed("mot ")
    assert out
    assert "mot" in out[-1]


def test_chunker_multiple_sentences_in_one_feed() -> None:
    c = StreamChunker()
    out = c.feed("Un. Deux. ")
    assert out == ["Un.", "Deux."]


def test_chunker_empty_after_full_consume() -> None:
    c = StreamChunker()
    c.feed("Fini. ")
    assert c.flush() is None
