# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from datetime import datetime

import httpx
from loguru import logger

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.connectivity import is_offline_mode
from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.settings import settings


class HomeAssistantCollector(CollectorBase):
    """Collecteur proactif Home Assistant — alarme, fuites, fumée, etc."""

    name = "home_assistant"

    async def _collect(self) -> list[ContextItem]:
        token = settings.home_assistant_token.get_secret_value()
        if is_offline_mode() or not token:
            return []

        base_url = settings.home_assistant_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"}

        critical_entities: list[ContextItem] = []
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                r = await client.get(f"{base_url}/api/states")
                if r.status_code != 200:
                    return []
                states = r.json()

            for state in states:
                entity_id = state.get("entity_id", "")
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                current_state = state.get("state", "")
                friendly = state.get("attributes", {}).get("friendly_name", entity_id)

                alarm_states = ("triggered", "arming", "pending")
                if domain == "alarm_control_panel" and current_state in alarm_states:
                    critical_entities.append(
                        ContextItem(
                            type=ItemType.NEWS,
                            title=f"🚨 ALARME DÉCLENCHÉE — {friendly}",
                            summary=f"L'alarme est en état **{current_state}**",
                            raw=str(state),
                            source="home_assistant",
                            timestamp=datetime.now(),
                            priority=Priority.HIGH,
                            metadata={"entity_id": entity_id, "state": current_state},
                        )
                    )

                elif domain == "binary_sensor" and current_state == "on":
                    device_class = state.get("attributes", {}).get("device_class", "")
                    if device_class in ("smoke", "gas", "moisture", "leak", "carbon_monoxide"):
                        critical_entities.append(
                            ContextItem(
                                type=ItemType.NEWS,
                                title=f"⚠️ {friendly} — {device_class.upper()}",
                                summary=f"Capteur **{device_class}** activé",
                                raw=str(state),
                                source="home_assistant",
                                timestamp=datetime.now(),
                                priority=Priority.HIGH,
                                metadata={"entity_id": entity_id, "device_class": device_class},
                            )
                        )

            return critical_entities

        except Exception as e:
            collector.warning("JRV-PRO-001", "JRV-PRO-001", cause=e)
            logger.warning(f"HomeAssistantCollector error: {e}")
            return []
