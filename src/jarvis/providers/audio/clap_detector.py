# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

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
        """Lance le daemon de détection en background.

        Sur un serveur headless (VPS, conteneur Docker) sans périphérique audio
        d'entrée, la détection de clap ne peut pas fonctionner : le double-clap
        suppose un micro physique sur la machine qui héberge Jarvis. On le signale
        explicitement et on s'arrête proprement, plutôt que de tourner dans le vide
        (ou de mourir silencieusement dans la task asyncio).
        """
        self._running = True
        self._loop = asyncio.get_event_loop()

        try:
            sd.check_input_settings(
                samplerate=self.SAMPLE_RATE, channels=1, dtype="float32"
            )
        except Exception as exc:  # noqa: BLE001 — PortAudioError, ValueError, OSError…
            logger.warning(
                "ClapDetector désactivé : aucun périphérique audio d'entrée détecté "
                "({}). Normal sur un serveur headless/VPS : le double-clap nécessite un "
                "micro sur la machine hôte. Mets CLAP_DETECTION_ENABLED=false pour "
                "masquer cet avertissement.",
                exc,
            )
            self._running = False
            return

        logger.info("ClapDetector started", threshold=self._threshold)

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                blocksize=self.BLOCK_SIZE,
                dtype="float32",
                callback=self._audio_callback,
            ):
                while self._running:  # noqa: ASYNC110 — Event refactoring hors scope (stream sounddevice)
                    await asyncio.sleep(0.1)
        except sd.PortAudioError as exc:
            logger.warning(
                "ClapDetector arrêté : erreur audio PortAudio ({}). Micro hôte "
                "indisponible ?",
                exc,
            )
            self._running = False

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
