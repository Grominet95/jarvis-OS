from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from jarvis.capabilities.tools.spotify import SpotifyTool
from jarvis.engine.background.notifications import NotificationQueue, ProactiveQueue
from jarvis.engine.background.worker import BackgroundTask, BackgroundWorker
from jarvis.engine.gateway import _FALLBACK, Gateway
from jarvis.engine.router import RouteEnum
from jarvis.interfaces.api.logs import _log_buffer
from jarvis.providers.memory.auto_dream import AutoDream
from jarvis.providers.memory.consolidation import ConsolidationAgent
from jarvis.providers.vision.objects_queue import get_vision_objects_queue

router = APIRouter()

_spotify_tool = SpotifyTool()

# Cooldown présence : évite les annonces répétées quand la caméra est rouverte
_PRESENCE_COOLDOWN_S = 600  # 10 min entre deux annonces du même état
_presence_last_notified: dict[bool, float] = {True: 0.0, False: 0.0}


# ── /ws/logs — stream log buffer to the dashboard Système › Logs panel ────────
# Format pushed to client:
# { lv: "ok"|"info"|"warn"|"err", parts: [{t: string, cls?: "accent"|"dim"}] }
@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    """Streams the in-memory log ring buffer to the Système › Logs panel.
    Sends the last 50 entries on connect, then pushes new lines as they arrive.
    """

    await websocket.accept()
    last_sent = 0
    try:
        # Send buffered lines on connect
        snapshot = list(_log_buffer)
        for raw in snapshot[-50:]:
            msg = _format_log_line(raw)
            await websocket.send_json(msg)
        last_sent = len(_log_buffer)

        while True:
            await asyncio.sleep(0.8)
            buf = list(_log_buffer)
            new_lines = buf[last_sent:]
            for raw in new_lines:
                msg = _format_log_line(raw)
                try:
                    await websocket.send_json(msg)
                except Exception:
                    return
            last_sent = len(buf)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws/logs error", error=str(e))


def _format_log_line(raw: str) -> dict:
    """Wrap a plain loguru string line into the { lv, parts } schema."""
    import re

    # loguru format: "HH:MM:SS | LEVEL    | name — message"
    m = re.match(r"^(\d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(.+?)(?:\s*—\s*(.*))?$", raw)
    if m:
        level_raw = m.group(2).lower().strip()
        source = m.group(3).strip()
        message = (m.group(4) or "").strip()
        lv = {
            "info": "info",
            "warning": "warn",
            "error": "err",
            "success": "ok",
            "debug": "info",
        }.get(level_raw, "info")
        parts: list[dict] = [
            {"t": source, "cls": "accent"},
        ]
        if message:
            parts.append({"t": " · " + message})
        return {"lv": lv, "parts": parts}
    # Fallback: treat whole line as plain message
    return {"lv": "info", "parts": [{"t": raw}]}


_GESTURE_DIRECT_ACTIONS: dict[str, str] = {
    "Open_Palm": "toggle",
    "Victory": "next",
}

_GESTURE_LLM_COMMANDS: dict[str, str] = {
    "Thumb_Up": "Oui, confirme",
    "Thumb_Down": "Non, annule",
    "Pointing_Up": "Hey Jarvis",
}

_PRESENCE_MSGS: dict[bool, str] = {
    True: "L'utilisateur est revenu devant l'ordinateur.",
    False: "L'utilisateur s'est éloigné de l'ordinateur.",
}


async def _handle_vision_event(
    data: dict,
    websocket: WebSocket,
    gateway: Gateway,
    notifications: NotificationQueue,
) -> None:
    """Traite un événement MediaPipe reçu depuis le navigateur."""
    event = data.get("event")

    if event == "presence":
        active: bool = bool(data.get("active", True))
        now = time.time()
        if now - _presence_last_notified[active] >= _PRESENCE_COOLDOWN_S:
            _presence_last_notified[active] = now
            notifications.add(_PRESENCE_MSGS[active])
        logger.debug("Vision presence", active=active)
        return

    if event == "gesture_direct":
        gesture = data.get("gesture", "")
        action = _GESTURE_DIRECT_ACTIONS.get(gesture)
        if action:
            result = await _spotify_tool.execute(action=action)
            logger.info(
                "Vision gesture direct", gesture=gesture, action=action, ok=not result.is_error
            )
        return

    if event == "gesture_volume":
        delta = int(data.get("delta", 0))
        if delta:
            result = await _spotify_tool.execute(action="volume_delta", delta=delta)
            logger.debug("Vision gesture volume", delta=delta, ok=not result.is_error)
        return

    if event == "gesture":
        gesture = data.get("gesture", "")
        message = _GESTURE_LLM_COMMANDS.get(gesture)
        if not message:
            return
        logger.info("Vision gesture LLM", gesture=gesture, message=message)
        session_id: str | None = data.get("session_id")
        session, route, response = await gateway.handle(
            message=message, session_id=session_id, stream=True
        )
        await websocket.send_json(
            {"type": "start", "session_id": str(session.id), "route": route.value}
        )
        full = ""
        if isinstance(response, str):
            full = response
            await websocket.send_json({"type": "chunk", "content": response})
        else:
            try:
                async for chunk in response:
                    full += chunk
                    await websocket.send_json({"type": "chunk", "content": chunk})
            except Exception as e:
                logger.error("Vision gesture stream error", error=str(e))
                full = _FALLBACK
                await websocket.send_json({"type": "chunk", "content": _FALLBACK})
        session.add_message("assistant", full)
        await websocket.send_json({"type": "done"})


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket de chat texte. Protocole JSON :

    Client → Server : {"message": "...", "session_id": "uuid|null"}
    Server → Client :
      {"type": "start",  "session_id": "...", "route": "I|CF|BG"}
      {"type": "chunk",  "content": "..."}
      {"type": "done"}
      {"type": "error",  "content": "..."}

    Pour la route BG : l'ack est streamé token par token, "done" est envoyé dès que
    l'ack est terminé, et la tâche background est soumise APRÈS — elle ne bloque jamais
    le client.
    """
    await websocket.accept()
    logger.info("WebSocket connection opened")

    gateway: Gateway = websocket.app.state.gateway
    worker: BackgroundWorker = websocket.app.state.worker
    consolidation: ConsolidationAgent = websocket.app.state.consolidation
    auto_dream: AutoDream = websocket.app.state.auto_dream
    proactive: ProactiveQueue = websocket.app.state.proactive_queue
    notifications: NotificationQueue = websocket.app.state.notifications

    sub_q = proactive.subscribe()
    objects_q = get_vision_objects_queue().subscribe()

    async def _push_proactive() -> None:
        while True:
            item = await sub_q.get()
            try:
                if isinstance(item, dict):
                    await websocket.send_json(item)
                else:
                    await websocket.send_json({"type": "notification", "content": item})
            except Exception as e:
                logger.warning("Proactive push failed", error=str(e))

    async def _push_vision_objects() -> None:
        while True:
            objects = await objects_q.get()
            try:
                await websocket.send_json({"type": "vision_objects", "objects": objects})
            except Exception:
                pass

    pusher_task = asyncio.create_task(_push_proactive(), name="ws-proactive-pusher")
    vision_pusher_task = asyncio.create_task(_push_vision_objects(), name="ws-vision-pusher")

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "JSON invalide."})
                continue

            # ── Vision events (MediaPipe) ─────────────────────────────────────
            if data.get("type") == "vision_event":
                await _handle_vision_event(data, websocket, gateway, notifications)
                continue

            message: str = data.get("message", "").strip()
            session_id: str | None = data.get("session_id")

            if not message:
                await websocket.send_json({"type": "error", "content": "Message vide."})
                continue

            # Signaler l'activité — le ProactiveEngine attendra avant son prochain appel LLM
            proactive_engine = getattr(websocket.app.state, "proactive_engine", None)
            if proactive_engine is not None:
                proactive_engine.signal_user_activity()

            session, route, response = await gateway.handle(
                message=message,
                session_id=session_id,
                stream=True,
            )

            logger.debug("Route", route=route.value, session_id=str(session.id))
            await websocket.send_json(
                {"type": "start", "session_id": str(session.id), "route": route.value}
            )

            full = ""
            if isinstance(response, str):
                full = response
                await websocket.send_json({"type": "chunk", "content": response})
            else:
                try:
                    async for chunk in response:
                        full += chunk
                        await websocket.send_json({"type": "chunk", "content": chunk})
                except Exception as e:
                    logger.error("Stream error", error=str(e))
                    full = _FALLBACK
                    await websocket.send_json({"type": "chunk", "content": _FALLBACK})

            session.add_message("assistant", full)

            # ── "done" envoyé en premier — client débloqué ────────────────────
            await websocket.send_json({"type": "done"})

            # ── BG : soumission APRÈS "done" (gateway ne soumet plus) ─────────
            if route is RouteEnum.BACKGROUND:
                worker.submit(BackgroundTask(session_id=str(session.id), instruction=message))
                logger.info("BackgroundTask submitted", session_id=str(session.id))

            # ── PROJECT : lancement orchestrateur APRÈS "done" ────────────────
            elif route is RouteEnum.PROJECT:
                orchestrator = getattr(websocket.app.state, "orchestrator", None)
                if orchestrator:

                    async def _run_project(
                        msg: str = message, _orch: object = orchestrator
                    ) -> None:
                        try:
                            await _orch.create_and_run(msg)
                        except Exception as exc:
                            logger.error("Project creation failed", error=str(exc))
                            proactive.broadcast_event(
                                {
                                    "type": "notification",
                                    "content": f"Erreur création projet : {exc}",
                                }
                            )

                    asyncio.create_task(_run_project(), name=f"project-{str(session.id)[:8]}")
                    logger.info("Project task launched", session_id=str(session.id))

            # ── mémoire post-done, hors chemin critique ───────────────────────
            # sleep(2) laisse la connexion HTTP principale se libérer avant que
            # le background_llm parte — évite la contention sur le client Anthropic.
            await asyncio.sleep(2)
            asyncio.create_task(
                consolidation._run_safe(user_message=message, assistant_message=full),
                name="consolidation",
            )
            asyncio.create_task(
                auto_dream._run_micro_safe(user_message=message, assistant_message=full),
                name="autodream-micro",
            )
            _user_model = getattr(websocket.app.state, "user_model", None)
            if _user_model is not None:
                _user_model.fire(user_message=message, assistant_message=full)

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error("WebSocket fatal error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "content": "Erreur serveur."})
        except Exception:
            pass
    finally:
        pusher_task.cancel()
        vision_pusher_task.cancel()
        proactive.unsubscribe(sub_q)
        get_vision_objects_queue().unsubscribe(objects_q)
