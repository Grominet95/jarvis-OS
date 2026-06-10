"""Gateway de messagerie unifié Jarvis.

MessagingGateway orchestre N ChannelAdapters, assure la continuité de session
cross-plateforme en persistant un mapping (platform:user_id → session_id) sur
disque, et route chaque message entrant vers le core.Gateway Jarvis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from jarvis.interfaces.channels.base import ChannelAdapter, IncomingMessage, MessageTarget

if TYPE_CHECKING:
    from jarvis.engine.gateway import Gateway as JarvisGateway

_SESSION_MAP_FILE = Path("memory/messaging_sessions.json")


class MessagingGateway:
    """Orchestre plusieurs ChannelAdapters avec continuité de session.

    Usage::

        gw = MessagingGateway(jarvis_gateway=app.state.gateway)
        gw.register(TelegramChannel(...))
        gw.register(DiscordChannel(...))
        await gw.start_all()
        # ...
        await gw.stop_all()
    """

    def __init__(
        self,
        jarvis_gateway: JarvisGateway,
        session_map_path: Path = _SESSION_MAP_FILE,
    ) -> None:
        self._jarvis = jarvis_gateway
        self._adapters: dict[str, ChannelAdapter] = {}
        self._session_map_path = session_map_path
        self._session_map: dict[str, str] = self._load_session_map()

    # ── Gestion des adaptateurs ───────────────────────────────────────────────

    def register(self, adapter: ChannelAdapter) -> None:
        """Enregistre un adaptateur et lui injecte le callback de dispatch."""
        adapter.set_dispatch(self.dispatch)
        self._adapters[adapter.platform.value] = adapter
        logger.info("Canal enregistré", platform=adapter.platform.value)

    async def start_all(self) -> None:
        """Démarre tous les adaptateurs enregistrés."""
        for adapter in self._adapters.values():
            await adapter.start()

    async def stop_all(self) -> None:
        """Arrête proprement tous les adaptateurs."""
        for adapter in self._adapters.values():
            await adapter.stop()

    # ── Dispatch ─────────────────────────────────────────────────────────────

    async def dispatch(self, msg: IncomingMessage) -> None:
        """Route un message entrant vers Jarvis et renvoie la réponse au bon canal.

        La session est restaurée depuis le mapping persisté si elle existe,
        ou créée à la volée par le core.Gateway.
        """
        session_id = self._session_map.get(msg.session_key)

        logger.debug(
            "Dispatch message",
            platform=msg.platform.value,
            user_id=msg.user_id,
            session_id=session_id,
            text=msg.text[:60],
        )

        session, _route, response = await self._jarvis.handle(
            msg.text,
            session_id=session_id,
            stream=False,
        )

        # Persiste le session_id (nouveau ou restauré)
        self._session_map[msg.session_key] = session.id
        self._save_session_map()

        adapter = self._adapters.get(msg.platform.value)
        if adapter is None:
            logger.warning("Adaptateur introuvable pour la réponse", platform=msg.platform.value)
            return

        target = MessageTarget(
            platform=msg.platform,
            user_id=msg.user_id,
            channel_id=msg.channel_id,
        )
        await adapter.send(str(response), target)

    # ── Persistance session map ───────────────────────────────────────────────

    def _load_session_map(self) -> dict[str, str]:
        if self._session_map_path.exists():
            try:
                return json.loads(self._session_map_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Impossible de charger messaging_sessions.json", error=str(exc))
        return {}

    def _save_session_map(self) -> None:
        try:
            self._session_map_path.parent.mkdir(parents=True, exist_ok=True)
            self._session_map_path.write_text(
                json.dumps(self._session_map, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Impossible de sauvegarder messaging_sessions.json", error=str(exc))
