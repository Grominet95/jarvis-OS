# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Wiring des canaux messaging au boot du process API.

Hors-Container par design (CDC §C.1) : Telegram/Discord/MessagingGateway
sont des interfaces L3, ils vivent à côté du graphe d'objets construit par
`bootstrap.build()`. Le boot du process API instancie le gateway et les
adapters à partir des flags d'env, puis les attache à `app.state` et
au router FastAPI dédié.

Extrait du lifespan d'app.py au polish post-v0.2.0 (Phase G) — réduit le
poids d'app.py sans déplacer de logique métier.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from fastapi import FastAPI
from loguru import logger

import jarvis.interfaces.channels.telegram_bot as _tg_module
from jarvis.interfaces.api.channels import router as channels_router
from jarvis.interfaces.channels.discord_bot import DiscordChannel
from jarvis.interfaces.channels.gateway import MessagingGateway
from jarvis.interfaces.channels.telegram_bot import TelegramChannel
from jarvis.kernel.connectivity import is_offline_mode

if TYPE_CHECKING:
    from jarvis.bootstrap import Container


async def setup_channels(app: FastAPI, container: Container) -> MessagingGateway | None:
    """Construit et démarre les canaux messaging selon les flags env.

    Lecture de `TELEGRAM_ENABLED`, `DISCORD_ENABLED`, `MESSAGING_GATEWAY_ENABLED`.
    Trois branches mutuellement exclusives :
      - mode offline avec un canal activé : log info, rien démarré ;
      - `MESSAGING_GATEWAY_ENABLED=true` : Gateway + adapters + router monté,
        retourne le Gateway pour shutdown symétrique ;
      - `TELEGRAM_ENABLED=true` seul : TelegramChannel legacy en tâche asyncio.

    Retourne le `MessagingGateway` instancié (mode gateway uniquement) ou
    `None` sinon — le caller l'utilise pour `await gw.stop_all()` au shutdown.
    """
    telegram_enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    discord_enabled = os.getenv("DISCORD_ENABLED", "false").lower() == "true"
    messaging_enabled = os.getenv("MESSAGING_GATEWAY_ENABLED", "false").lower() == "true"

    if is_offline_mode() and (telegram_enabled or discord_enabled or messaging_enabled):
        logger.info(
            "Canaux réseau (Telegram/Discord) désactivés — mode local actif",
            telegram=telegram_enabled,
            discord=discord_enabled,
        )
        return None

    if messaging_enabled:
        messaging_gw = MessagingGateway(jarvis_gateway=container.gateway)
        if telegram_enabled:
            telegram = TelegramChannel()
            _tg_module._telegram_instance = telegram
            messaging_gw.register(telegram)
        if discord_enabled:
            messaging_gw.register(DiscordChannel())
        app.state.messaging_gateway = messaging_gw
        app.include_router(channels_router)
        await messaging_gw.start_all()
        logger.info(
            "MessagingGateway démarré",
            adapters=list(messaging_gw._adapters.keys()),
        )
        return messaging_gw

    if telegram_enabled:
        telegram = TelegramChannel(gateway=container.gateway)
        _tg_module._telegram_instance = telegram
        asyncio.create_task(telegram.start(), name="telegram-bot")
        logger.info("Canal Telegram démarré (mode legacy)")

    return None
