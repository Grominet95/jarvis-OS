# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import json
import os

from loguru import logger

import websockets

from jarvis.engine.background.notifications import NotificationQueue


class HomeAssistantWSClient:
    """Client WebSocket temps réel pour Home Assistant."""

    def __init__(self, notification_queue: NotificationQueue | None = None):
        self.base_url = os.getenv("HA_URL", "http://homeassistant.local:8123")
        self.ws_url = self.base_url.replace("http", "ws") + "/api/websocket"
        self.token = os.getenv("HA_TOKEN", "")
        self.notification_queue = notification_queue
        self._running = False

    async def start(self):
        if not self.token:
            logger.warning("HA WebSocket désactivé (pas de token)")
            return

        self._running = True
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                    auth_msg = await ws.recv()
                    if json.loads(auth_msg).get("type") != "auth_ok":
                        logger.error("Échec auth WebSocket HA")
                        return

                    await ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed" }))

                    logger.info("WebSocket Home Assistant connecté (temps réel)")

                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "event":
                            event = data.get("event", {})
                            entity_id = event.get("data", {}).get("entity_id", "")
                            new_state = event.get("data", {}).get("new_state", {})

                            if "alarm_control_panel" in entity_id and new_state.get("state") == "triggered":
                                self._notify(f"🚨 ALARME DÉCLENCHÉE en temps réel : {entity_id}")

                            if new_state.get("state") == "on" and any(x in entity_id for x in ["smoke", "leak", "gas", "co"]):
                                self._notify(f"⚠️ Capteur critique activé : {entity_id}")

            except Exception as e:
                if self._running:
                    logger.warning(f"WebSocket HA erreur, reconnexion... : {e}")
                    await asyncio.sleep(10)

    def _notify(self, message: str):
        if self.notification_queue:
            self.notification_queue.add(message)
        logger.warning(message)

    async def stop(self):
        self._running = False
