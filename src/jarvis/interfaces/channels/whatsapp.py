# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Stub WhatsApp pour Jarvis — à implémenter via Twilio ou WhatsApp Business API."""

from __future__ import annotations

from jarvis.interfaces.channels.base import ChannelAdapter, MessageTarget, Platform


class WhatsAppChannel(ChannelAdapter):
    """Stub WhatsApp — enregistrable dans MessagingGateway, non fonctionnel."""

    platform = Platform.WHATSAPP  # type: ignore[assignment]

    async def start(self) -> None:
        raise NotImplementedError("WhatsApp non implémenté — utiliser Twilio ou WABA API.")

    async def stop(self) -> None:
        pass

    async def send(self, reply: str, target: MessageTarget) -> None:
        raise NotImplementedError("WhatsApp non implémenté.")
