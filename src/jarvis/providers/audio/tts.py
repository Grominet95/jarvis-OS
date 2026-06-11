from __future__ import annotations

import asyncio
import io
import wave
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger
from piper import PiperVoice

from config.settings import settings
from jarvis.kernel.contracts import UsageTracker
from jarvis.kernel.schemas import UsageEntry, calculate_cost


class TTSEngine:
    """Moteur TTS avec routing ElevenLabs / Piper selon TTS_PROVIDER.

    Phase C — étape 2 (d) : `tracker` reçu par injection (constructeur ou
    `set_tracker`). Aucun import depuis `jarvis.engine.*` (CYCLE 1 bouclé).
    """

    def __init__(self, tracker: UsageTracker | None = None) -> None:
        self._piper_voice: object = None
        self._tracker = tracker

    def set_tracker(self, tracker: UsageTracker) -> None:
        """Injection post-construction (le singleton module-level est créé
        avant que le Container n'existe ; bootstrap.build() pousse le tracker
        ici juste après instanciation)."""
        self._tracker = tracker

    async def synthesize(self, text: str) -> bytes:
        """Synthétise un texte → bytes audio. Route selon settings.tts_provider."""
        if not text.strip():
            return b""
        if settings.tts_provider == "elevenlabs":
            return await self._synthesize_elevenlabs(text)
        return await self._synthesize_piper(text)

    async def _synthesize_elevenlabs(self, text: str) -> bytes:
        """ElevenLabs streaming TTS — modèle turbo, latence ~300ms."""
        voice_id = (
            settings.quebec_voice_id if settings.quebec_mode else settings.elevenlabs_voice_id
        )
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": settings.elevenlabs_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True,
            },
            "optimize_streaming_latency": 3,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    logger.debug(
                        f"ElevenLabs TTS done — {len(text)} chars, {len(response.content)} bytes"
                    )
                    cost = calculate_cost(
                        "elevenlabs", settings.elevenlabs_model, characters=len(text)
                    )
                    if self._tracker is not None:
                        self._tracker.track(
                            UsageEntry(
                                timestamp=datetime.now().isoformat(),
                                provider="elevenlabs",
                                model=settings.elevenlabs_model,
                                characters=len(text),
                                cost_usd=cost,
                                context="conversation",
                            )
                        )
                    return response.content
                logger.error(f"ElevenLabs error {response.status_code} — {response.text[:300]}")
        except Exception as e:
            logger.error("ElevenLabs request failed", error=str(e))
        # Fallback Piper si ElevenLabs échoue
        logger.warning("Falling back to Piper TTS")
        return await self._synthesize_piper(text)

    async def _synthesize_piper(self, text: str) -> bytes:
        """Piper local — fallback ou provider principal."""
        logger.debug("Piper TTS request", chars=len(text))
        data = await asyncio.to_thread(self._piper_sync, text)
        logger.debug("Piper TTS done", bytes=len(data))
        return data

    def _piper_sync(self, text: str) -> bytes:

        if self._piper_voice is None:
            model_path = Path(settings.piper_model_path)
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Modèle Piper introuvable : {model_path}. "
                    "Lance : mkdir -p models/piper && "
                    "curl -L -o models/piper/fr_FR-upmc-medium.onnx <url>"
                )
            self._piper_voice = PiperVoice.load(str(model_path))
            logger.info("Piper model loaded", model=str(model_path))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._piper_voice.synthesize_wav(text, wf)  # type: ignore[union-attr]
        buf.seek(0)
        return buf.read()

    async def warmup(self) -> None:
        """Préchauffer le moteur TTS au démarrage."""
        await self.synthesize("Initialisation.")
        logger.info("TTS warmup done", provider=settings.tts_provider)


tts_engine = TTSEngine()
