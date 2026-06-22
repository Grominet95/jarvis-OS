# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Stub Signal pour Jarvis — à implémenter via signal-cli ou AsamiSignal."""

from __future__ import annotations

from jarvis.interfaces.channels.base import ChannelAdapter, MessageTarget, Platform


class SignalChannel(ChannelAdapter):
    """Stub Signal — enregistrable dans MessagingGateway, non fonctionnel."""

    platform = Platform.SIGNAL  # type: ignore[assignment]

    async def start(self) -> None:
        raise NotImplementedError("Signal non implémenté — utiliser signal-cli REST API.")

    async def stop(self) -> None:
        pass

    async def send(self, reply: str, target: MessageTarget) -> None:
        raise NotImplementedError("Signal non implémenté.")
