"""Tests du TTS Gemini : wrap PCM->WAV + routing TTS_PROVIDER."""

from __future__ import annotations

import io
import wave
from types import SimpleNamespace

from jarvis.providers.audio import tts as mod


def test_pcm_to_wav_wraps_raw_pcm() -> None:
    pcm = b"\x01\x02" * 12000  # 24000 octets = 12000 samples 16-bit
    out = mod._pcm_to_wav(pcm, sample_rate=24000)
    assert out[:4] == b"RIFF"
    w = wave.open(io.BytesIO(out))
    assert w.getnchannels() == 1
    assert w.getsampwidth() == 2
    assert w.getframerate() == 24000
    assert w.getnframes() == 12000


def test_extract_gemini_pcm_concatenates_audio_parts() -> None:
    resp = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
        SimpleNamespace(inline_data=SimpleNamespace(data=b"ab", mime_type="audio/pcm")),
        SimpleNamespace(inline_data=SimpleNamespace(data=b"cd", mime_type="text/plain")),
        SimpleNamespace(inline_data=SimpleNamespace(data=b"ef", mime_type="audio/L16")),
    ]))])
    assert mod._extract_gemini_pcm(resp) == b"abef"


def test_extract_gemini_pcm_empty_when_no_audio() -> None:
    assert mod._extract_gemini_pcm(SimpleNamespace(candidates=[])) == b""
