from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from jarvis.engine.background.notifications import ProactiveQueue
from jarvis.engine.background.worker import BackgroundTask, BackgroundWorker
from jarvis.engine.gateway import _FALLBACK, Gateway
from jarvis.engine.router import RouteEnum
from jarvis.kernel.settings import settings
from jarvis.providers.audio.chunker import StreamChunker
from jarvis.providers.audio.deepgram_receiver import DeepgramReceiver
from jarvis.providers.audio.receiver import VoiceReceiver
from jarvis.providers.audio.tts import tts_engine
from jarvis.providers.memory.auto_dream import AutoDream
from jarvis.providers.memory.consolidation import ConsolidationAgent

router = APIRouter()


@dataclass
class VoiceSession:
    """État d'une connexion voix — partagé entre le receive-loop et le process-loop."""

    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)


async def _respond_voice(
    websocket: WebSocket,
    text_stream: AsyncIterator[str],
    session: VoiceSession,
) -> tuple[str, bool]:
    """Stream LLM → phrases → TTS → audio envoyé phrase par phrase.

    Retourne (texte_complet, interrompu).
    Envoie les events : llm_start, tts_start, done.
    Vérifie session.interrupt_event à chaque token et avant chaque chunk TTS.
    """
    chunker = StreamChunker()
    full_text = ""
    llm_started = False
    tts_started = False

    async for token in text_stream:
        if session.interrupt_event.is_set():
            session.interrupt_event.clear()
            return full_text, True

        full_text += token
        await websocket.send_json({"type": "chunk", "content": token})

        if not llm_started:
            await websocket.send_json({"type": "llm_start"})
            llm_started = True

        for sentence in chunker.feed(token):
            if session.interrupt_event.is_set():
                session.interrupt_event.clear()
                return full_text, True

            logger.debug("TTS chunk", text=sentence[:40])
            audio_bytes = await tts_engine.synthesize(sentence)

            if not tts_started:
                await websocket.send_json({"type": "tts_start"})
                tts_started = True

            await websocket.send_bytes(audio_bytes)

    remainder = chunker.flush()
    if remainder and not session.interrupt_event.is_set():
        if not tts_started:
            await websocket.send_json({"type": "tts_start"})
        audio_bytes = await tts_engine.synthesize(remainder)
        await websocket.send_bytes(audio_bytes)

    await websocket.send_json({"type": "done"})
    return full_text, False


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket) -> None:
    """WebSocket audio — VAD et transcription assurés par RealtimeSTT côté serveur.

    Client → Server :
      binary frames  : PCM float32, 16 kHz, mono (continu)
      {"type": "interrupt"} : barge-in — coupe la réponse en cours

    Server → Client :
      {"type": "vad_start"}                     ← VAD détecte la voix
      {"type": "transcript",  "text": "..."}
      {"type": "stt_done",    "transcript": "..."} ← Whisper terminé
      {"type": "start",       "session_id": "...", "route": "I|CF|BG"}
      {"type": "llm_start"}                     ← premier token LLM
      {"type": "chunk",       "content": "..."}  ← tokens LLM
      binary frames          : WAV Piper (phrase par phrase)
      {"type": "tts_start"}                     ← premier audio envoyé
      {"type": "done"}                          ← stream LLM terminé
      {"type": "tts_done"}                      ← audio terminé côté serveur
      {"type": "interrupted"}                   ← barge-in confirmé
      {"type": "error",       "content": "..."}
    """
    await websocket.accept()
    logger.info("Voice WebSocket connected")

    gateway: Gateway = websocket.app.state.voice_gateway
    worker: BackgroundWorker = websocket.app.state.worker
    consolidation: ConsolidationAgent = websocket.app.state.consolidation
    auto_dream: AutoDream = websocket.app.state.auto_dream
    proactive: ProactiveQueue = websocket.app.state.proactive_queue

    # Restaure la session existante si le client passe un session_id
    initial_session_id: str | None = websocket.query_params.get("session_id") or None

    loop = asyncio.get_running_loop()
    if settings.stt_provider == "deepgram":
        receiver: VoiceReceiver | DeepgramReceiver = DeepgramReceiver()
    else:
        receiver = VoiceReceiver()
    await asyncio.to_thread(receiver.start, loop)

    voice_session = VoiceSession()
    sub_q = proactive.subscribe()

    # ── VAD watcher : envoie vad_start dès que le VAD détecte de la voix ──────
    async def _vad_watcher() -> None:
        while True:
            await receiver.next_vad_start()
            try:
                await websocket.send_json({"type": "vad_start"})
            except Exception:
                break

    # ── Proactif vocal ────────────────────────────────────────────────────────
    async def _push_proactive_voice() -> None:
        while True:
            content = await sub_q.get()
            try:
                await websocket.send_json({"type": "notification", "content": content})
                if content.strip():
                    audio_bytes = await tts_engine.synthesize(content)
                    await websocket.send_bytes(audio_bytes)
                    await websocket.send_json({"type": "tts_done"})
            except Exception as e:
                logger.warning("Voice proactive push failed", error=str(e))

    # ── Process loop ──────────────────────────────────────────────────────────
    async def process_loop() -> None:
        session_id: str | None = initial_session_id
        while True:
            text = await receiver.next_transcript()
            logger.debug("Transcript received", text=text[:60])

            await websocket.send_json({"type": "transcript", "text": text})
            await websocket.send_json({"type": "stt_done", "transcript": text})

            voice_session.interrupt_event.clear()

            session, route, response = await gateway.handle(
                message=text.strip() + " [voix]",
                session_id=session_id,
                stream=True,
            )
            session_id = str(session.id)
            await websocket.send_json(
                {"type": "start", "session_id": session_id, "route": route.value}
            )

            interrupted = False

            if isinstance(response, str):
                await websocket.send_json({"type": "llm_start"})
                await websocket.send_json({"type": "chunk", "content": response})
                full = response
                if full.strip() and not voice_session.interrupt_event.is_set():
                    await websocket.send_json({"type": "tts_start"})
                    audio_out = await tts_engine.synthesize(full)
                    await websocket.send_bytes(audio_out)
                await websocket.send_json({"type": "done"})
            else:
                try:
                    full, interrupted = await _respond_voice(websocket, response, voice_session)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("Voice stream error", error=str(e))
                    full = _FALLBACK
                    await websocket.send_json({"type": "chunk", "content": _FALLBACK})
                    await websocket.send_json({"type": "done"})

            session.add_message("assistant", full)

            if interrupted:
                await websocket.send_json({"type": "interrupted"})
            else:
                await websocket.send_json({"type": "tts_done"})

            if route is RouteEnum.BACKGROUND:
                worker.submit(BackgroundTask(session_id=session_id, instruction=text))

            await asyncio.sleep(2)
            asyncio.create_task(
                consolidation._run_safe(user_message=text, assistant_message=full),
                name="consolidation",
            )
            asyncio.create_task(
                auto_dream._run_micro_safe(user_message=text, assistant_message=full),
                name="autodream-micro",
            )

    process_task = asyncio.create_task(process_loop(), name="voice-process-loop")
    proactive_task = asyncio.create_task(_push_proactive_voice(), name="voice-proactive-pusher")
    vad_task = asyncio.create_task(_vad_watcher(), name="voice-vad-watcher")

    try:
        while True:
            msg = await websocket.receive()
            raw_bytes = msg.get("bytes")
            if raw_bytes:
                receiver.feed(raw_bytes)
            else:
                # JSON message du client (barge-in, etc.)
                text_data = msg.get("text")
                if text_data:
                    try:
                        data = json.loads(text_data)
                        if data.get("type") == "interrupt":
                            voice_session.interrupt_event.set()
                            logger.info("Barge-in interrupt received")
                            await websocket.send_json({"type": "interrupted"})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected")
    except Exception as e:
        logger.error("Voice WebSocket error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "content": "Erreur serveur."})
        except Exception:
            pass
    finally:
        process_task.cancel()
        proactive_task.cancel()
        vad_task.cancel()
        proactive.unsubscribe(sub_q)
        await asyncio.to_thread(receiver.stop)
