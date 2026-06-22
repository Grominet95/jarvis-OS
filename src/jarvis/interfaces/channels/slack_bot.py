# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Stub Slack pour Jarvis — à implémenter via Slack Bolt SDK."""

from __future__ import annotations

from jarvis.interfaces.channels.base import ChannelAdapter, MessageTarget, Platform


class SlackChannel(ChannelAdapter):
    """Stub Slack — enregistrable dans MessagingGateway, non fonctionnel."""

    platform = Platform.SLACK  # type: ignore[assignment]

    async def start(self) -> None:
        raise NotImplementedError("Slack non implémenté — utiliser Slack Bolt for Python.")

    async def stop(self) -> None:
        pass

    async def send(self, reply: str, target: MessageTarget) -> None:
        raise NotImplementedError("Slack non implémenté.")
