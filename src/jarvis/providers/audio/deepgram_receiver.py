# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import json

import aiohttp
import numpy as np
from loguru import logger
from numpy.typing import NDArray

from jarvis.kernel.settings import settings

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramReceiver:
    """Transcription temps réel via Deepgram Nova-2 (cloud streaming).

    Interface identique à VoiceReceiver — feed() + next_transcript() + next_vad_start().
    Latence ~200ms vs ~900ms pour Whisper local. Pas de téléchargement de modèle.
    """

    def __init__(self) -> None:
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._vad_queue: asyncio.Queue[None] = asyncio.Queue()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._send_task: asyncio.Task | None = None
        self._running = False
        self._pending: list[str] = []

    # ── Public interface (identique à VoiceReceiver) ──────────────────────────

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Établit la connexion Deepgram WebSocket (appelé via asyncio.to_thread)."""
        self._loop = loop
        self._running = True
        future = asyncio.run_coroutine_threadsafe(self._connect(), loop)
        future.result(timeout=15.0)
        logger.info("DeepgramReceiver prêt — Deepgram Nova-2 streaming actif")

    def feed(self, pcm_float32: bytes) -> None:
        """Convertit PCM float32 → int16 et envoie à Deepgram."""
        if not self._running or self._loop is None or self._loop.is_closed():
            return
        audio: NDArray[np.float32] = np.frombuffer(pcm_float32, dtype=np.float32)
        int16: NDArray[np.int16] = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        asyncio.run_coroutine_threadsafe(
            self._audio_queue.put(int16.tobytes()),
            self._loop,
        )

    async def next_transcript(self) -> str:
        return await self._transcript_queue.get()

    async def next_vad_start(self) -> None:
        await self._vad_queue.get()

    def stop(self) -> None:
        self._running = False
        if self._loop and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop).result(timeout=5.0)
            except Exception:
                pass
        logger.info("DeepgramReceiver stopped")

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _connect(self) -> None:
        api_key = settings.deepgram_api_key.get_secret_value()
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY manquant dans .env")

        params = (
            "model=nova-2"
            "&language=fr"
            "&encoding=linear16"
            "&sample_rate=16000"
            "&channels=1"
            "&interim_results=true"
            "&smart_format=true"
            "&endpointing=300"
            "&vad_events=true"
        )
        url = f"{_DEEPGRAM_WS_URL}?{params}"

        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            url,
            headers={"Authorization": f"Token {api_key}"},
            heartbeat=10.0,
        )
        self._recv_task = asyncio.create_task(self._recv_loop(), name="deepgram-recv")
        self._send_task = asyncio.create_task(self._send_loop(), name="deepgram-send")
        logger.debug("Deepgram WebSocket connected")

    async def _recv_loop(self) -> None:
        try:
            async for msg in self._ws:  # type: ignore[union-attr]
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    break
        except Exception as e:
            if self._running:
                logger.error("Deepgram recv error", error=str(e))

    async def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            return

        msg_type = data.get("type", "")

        if msg_type == "SpeechStarted":
            self._pending = []
            await self._vad_queue.put(None)
            logger.debug("Deepgram VAD: speech started")

        elif msg_type == "Results":
            is_final: bool = data.get("is_final", False)
            speech_final: bool = data.get("speech_final", False)

            if is_final:
                try:
                    text = data["channel"]["alternatives"][0]["transcript"].strip()
                    if text:
                        self._pending.append(text)
                except (KeyError, IndexError):
                    pass

            if speech_final:
                full = " ".join(self._pending).strip()
                self._pending = []
                if full:
                    logger.debug("Deepgram final transcript", text=full)
                    await self._transcript_queue.put(full)

        elif msg_type == "Metadata":
            logger.debug("Deepgram metadata", data=data)

        elif msg_type == "Error":
            logger.error("Deepgram error message", data=data)

    async def _send_loop(self) -> None:
        try:
            while self._running:
                audio = await self._audio_queue.get()
                if self._ws and not self._ws.closed:
                    await self._ws.send_bytes(audio)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._running:
                logger.error("Deepgram send error", error=str(e))

    async def _disconnect(self) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        for task in (self._recv_task, self._send_task):
            if task:
                task.cancel()
