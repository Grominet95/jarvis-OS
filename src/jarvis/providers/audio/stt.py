from __future__ import annotations

import asyncio

import numpy as np
from faster_whisper import WhisperModel
from loguru import logger
from numpy.typing import NDArray

from jarvis.kernel.settings import settings

_model: WhisperModel | None = None


def _load_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model", size=settings.whisper_model)
        _model = WhisperModel(settings.whisper_model, device="auto", compute_type="float16")
        logger.info("Whisper model ready")
    return _model


def _run_transcribe(model: WhisperModel, audio: NDArray[np.float32]) -> str:
    segments, info = model.transcribe(audio, language="fr", beam_size=5)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    logger.debug("STT done", lang=info.language, chars=len(text))
    return text


async def transcribe(pcm_bytes: bytes) -> str:
    """Transcrit un buffer PCM float32 (16 kHz mono) en texte français."""
    if not pcm_bytes:
        return ""
    model = await asyncio.to_thread(_load_model)
    audio: NDArray[np.float32] = np.frombuffer(pcm_bytes, dtype=np.float32).copy()
    return await asyncio.to_thread(_run_transcribe, model, audio)
