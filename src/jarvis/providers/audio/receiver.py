from __future__ import annotations

import asyncio
import threading

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from jarvis.kernel.settings import settings

# Modèles faster-whisper valides — nova-2 (Deepgram) et autres cloud STT ne sont pas valides ici
_VALID_WHISPER = frozenset(
    {
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-large-v2",
        "distil-medium.en",
        "distil-small.en",
        "distil-large-v3",
        "large-v3-turbo",
        "turbo",
    }
)


class VoiceReceiver:
    """Transcription temps réel via RealtimeSTT (VAD Silero/WebRTC + Whisper).

    Reçoit du PCM float32 depuis le navigateur, convertit en int16,
    et laisse RealtimeSTT gérer intégralement le VAD et la transcription.
    Le résultat est poussé dans une asyncio.Queue dès qu'une phrase est complète.
    """

    def __init__(self) -> None:
        self._recorder: object = None
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._vad_queue: asyncio.Queue[None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reader: threading.Thread | None = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialise RealtimeSTT et démarre le thread lecteur."""
        from RealtimeSTT import AudioToTextRecorder  # type: ignore[import-untyped]

        self._loop = loop
        self._running = True
        self._transcript_queue = asyncio.Queue()

        whisper_model = settings.whisper_model
        if whisper_model not in _VALID_WHISPER:
            logger.warning(
                "Modèle Whisper invalide '{}' — fallback sur 'tiny'. "
                "Vérifier WHISPER_MODEL dans .env "
                "(valeurs valides: tiny, small, medium, large-v3-turbo…)",
                whisper_model,
            )
            whisper_model = "tiny"

        logger.info(
            "Initialisation Whisper '{}' — premier lancement = téléchargement du modèle"
            " (~74 MB pour tiny, ~244 MB pour small). Patience…",
            whisper_model,
        )

        self._recorder = AudioToTextRecorder(
            language="fr",
            model=whisper_model,
            compute_type="int8",
            use_microphone=False,
            silero_sensitivity=0.6,  # plus sensible (0 = muet, 1 = maximal)
            webrtc_sensitivity=1,  # moins agressif (1-3, 3 = plus strict)
            post_speech_silence_duration=0.6,  # réponse plus rapide (était 1.2s)
            min_length_of_recording=0.3,  # accepte les courtes phrases (était 0.8s)
            spinner=False,
            on_recording_start=self._on_recording_start_cb,
        )

        def _reader_loop() -> None:
            logger.debug("RealtimeSTT reader loop started")
            while self._running:
                try:
                    text: str = self._recorder.text()  # type: ignore[union-attr]
                    logger.debug("RealtimeSTT raw transcript", text=repr(text))
                    if text and text.strip() and self._loop and not self._loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            self._transcript_queue.put(text.strip()),
                            self._loop,
                        )
                except Exception as e:
                    if self._running:
                        logger.error("RealtimeSTT reader error", error=str(e))

        self._reader = threading.Thread(target=_reader_loop, daemon=True, name="realtimestt-reader")
        self._reader.start()
        logger.info(
            "VoiceReceiver prêt — modèle Whisper '{}' chargé, écoute active.", whisper_model
        )

    def _on_recording_start_cb(self) -> None:
        """Appelé par RealtimeSTT dès que le VAD détecte de la voix."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self._vad_queue.put(None),
                self._loop,
            )

    async def next_vad_start(self) -> None:
        """Attend le prochain signal VAD (voix détectée, avant Whisper)."""
        await self._vad_queue.get()

    _feed_count = 0

    def feed(self, pcm_float32: bytes) -> None:
        """Convertit PCM float32 → int16 et envoie à RealtimeSTT en sous-chunks Silero (512)."""
        if self._recorder is None:
            return
        audio: NDArray[np.float32] = np.frombuffer(pcm_float32, dtype=np.float32)
        int16: NDArray[np.int16] = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        data = int16.tobytes()
        # Silero VAD attend des fenêtres de 512 samples (1024 bytes) à 16 kHz
        for i in range(0, len(data), 1024):
            self._recorder.feed_audio(data[i : i + 1024])  # type: ignore[union-attr]
        self._feed_count += 1
        if self._feed_count % 20 == 1:
            amplitude = float(np.abs(audio).max())
            logger.debug(
                "Audio feed",
                chunk_n=self._feed_count,
                samples=len(audio),
                amplitude=f"{amplitude:.3f}",
            )

    async def next_transcript(self) -> str:
        """Attend la prochaine transcription complète (asyncio-safe)."""
        return await self._transcript_queue.get()

    def stop(self) -> None:
        """Arrête le thread lecteur et RealtimeSTT."""
        self._running = False
        try:
            self._recorder.stop()  # type: ignore[union-attr]
        except Exception:
            pass
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=3.0)
        logger.info("VoiceReceiver stopped")
