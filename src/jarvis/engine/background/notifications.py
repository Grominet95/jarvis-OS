from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from loguru import logger

from jarvis.kernel.settings import settings


@dataclass
class Notification:
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NotificationQueue:
    """File thread-safe (single-threaded asyncio) des notifications en attente.

    add() : push une notification depuis n'importe quelle coroutine.
    drain() : vide et retourne la liste — appelé par le Gateway avant chaque réponse.
    """

    def __init__(self) -> None:
        self._pending: list[Notification] = []

    def add(self, content: str) -> None:
        self._pending.append(Notification(content=content))
        logger.debug("NotificationQueue.add", queue_id=id(self), total=len(self._pending))

    def drain(self) -> list[Notification]:
        pending, self._pending = self._pending, []
        logger.debug("NotificationQueue.drain", queue_id=id(self), drained=len(pending))
        return pending


class ProactiveQueue:
    """Broadcast temps-réel vers toutes les WebSockets actives.

    Chaque connexion souscrit via subscribe() et obtient sa propre asyncio.Queue.
    Le scheduler appelle broadcast() (str) ou broadcast_event() (dict structuré).
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[str | dict]] = []

    def subscribe(self) -> asyncio.Queue[str | dict]:
        q: asyncio.Queue[str | dict] = asyncio.Queue()
        self._subscribers.append(q)
        logger.debug("ProactiveQueue: subscriber added", total=len(self._subscribers))
        return q

    def unsubscribe(self, q: asyncio.Queue[str | dict]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass
        logger.debug("ProactiveQueue: subscriber removed", total=len(self._subscribers))

    def broadcast(self, content: str) -> None:
        for q in self._subscribers:
            q.put_nowait(content)
        logger.info(
            "ProactiveQueue: broadcast",
            subscribers=len(self._subscribers),
            preview=content[:60],
        )

    def broadcast_event(self, event: dict) -> None:
        for q in self._subscribers:
            q.put_nowait(event)
        logger.info(
            "ProactiveQueue: broadcast_event",
            type=event.get("type"),
            subscribers=len(self._subscribers),
        )


# ── Module-level helpers pour les presets ───────────────────────────────────

_proactive_queue_instance: ProactiveQueue | None = None


def set_proactive_queue(q: ProactiveQueue) -> None:
    global _proactive_queue_instance
    _proactive_queue_instance = q
    # Phase F : ré-enregistre dans kernel.notifications pour que les
    # capabilities (preset, executor) puissent broadcaster sans importer
    # jarvis.engine.* (RÈGLE 2).
    from jarvis.kernel.notifications import set_proactive_queue as _kernel_set

    _kernel_set(q)


async def broadcast_event(event: dict) -> None:
    if _proactive_queue_instance:
        _proactive_queue_instance.broadcast_event(event)


def get_broadcast_fn() -> object:
    """Retourne la fonction de broadcast adaptée au contexte (main ou voice agent)."""
    if _proactive_queue_instance is not None:
        return _proactive_queue_instance.broadcast_event
    # Fallback process séparé (ex. voice_agent) : HTTP POST vers le serveur FastAPI
    import json as _json
    import threading
    import urllib.request

    def _http_broadcast(event: dict) -> None:

        def _post() -> None:
            url = f"http://localhost:{settings.port}/internal/broadcast"
            data = _json.dumps(event).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass

        threading.Thread(target=_post, daemon=True).start()

    return _http_broadcast


async def broadcast_audio(audio_bytes: bytes) -> None:
    if _proactive_queue_instance and audio_bytes:
        import base64

        _proactive_queue_instance.broadcast_event(
            {
                "type": "audio",
                "data": base64.b64encode(audio_bytes).decode(),
            }
        )
