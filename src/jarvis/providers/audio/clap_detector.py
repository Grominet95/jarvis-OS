"""
Détection de double clap via le micro.
Algorithme : spike d'amplitude court et bref × 2 dans une fenêtre temporelle.
Inspiré de github.com/huwprosser/clap-detection
"""

from __future__ import annotations

import asyncio
import time

import numpy as np
import sounddevice as sd
from loguru import logger

from jarvis.kernel.settings import settings


class ClapDetector:
    """
    Détecte un double clap et appelle un callback async.
    Paramètres :
      - AMPLITUDE_THRESHOLD : sensibilité (0.0-1.0). Augmenter si trop de faux positifs.
      - MAX_CLAP_DURATION   : durée max d'un clap valide en secondes (un clap = bref)
      - DOUBLE_CLAP_WINDOW  : fenêtre max entre deux claps pour un double clap
      - COOLDOWN            : délai minimum entre deux déclenchements
    """

    MAX_CLAP_DURATION = 0.15  # Un clap dure moins de 150ms
    DOUBLE_CLAP_WINDOW = 0.8  # Les deux claps arrivent en moins de 800ms
    COOLDOWN = 2.0  # Minimum 2s entre deux wake ups

    SAMPLE_RATE = 16000
    BLOCK_SIZE = 512  # ~32ms par bloc

    def __init__(self, callback: object) -> None:
        """
        callback : coroutine async appelée quand double clap détecté
        Signature : async def on_clap() -> None
        """
        self._callback = callback
        self._threshold = settings.clap_amplitude_threshold
        self._clap_times: list[float] = []
        self._last_trigger = 0.0
        self._in_clap = False
        self._clap_start = 0.0
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Lance le daemon de détection en background."""
        self._running = True
        self._loop = asyncio.get_event_loop()
        logger.info("ClapDetector started", threshold=self._threshold)

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            blocksize=self.BLOCK_SIZE,
            dtype="float32",
            callback=self._audio_callback,
        ):
            while self._running:  # noqa: ASYNC110 — Event refactoring hors scope (stream sounddevice)
                await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False

    def _audio_callback(
        self, indata: object, frames: int, time_info: object, status: object
    ) -> None:
        """Appelé par sounddevice pour chaque bloc audio."""
        if status:
            return

        amplitude = float(np.abs(indata).max())
        now = time.time()

        if amplitude > self._threshold:
            if not self._in_clap:
                self._in_clap = True
                self._clap_start = now
        else:
            if self._in_clap:
                duration = now - self._clap_start
                self._in_clap = False

                if duration <= self.MAX_CLAP_DURATION:
                    self._register_clap(now)

    def _register_clap(self, now: float) -> None:
        """Enregistre un clap et vérifie si c'est un double clap."""
        self._clap_times = [t for t in self._clap_times if now - t <= self.DOUBLE_CLAP_WINDOW]

        self._clap_times.append(now)

        if len(self._clap_times) >= 2:
            if now - self._last_trigger >= self.COOLDOWN:
                self._last_trigger = now
                self._clap_times.clear()
                logger.info("ClapDetector: double clap détecté → wake up")

                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._callback(), self._loop)
