"""Canal Discord pour Jarvis.

Implémente ChannelAdapter via discord.py (py-cord / discord.py ≥ 2.x).
Le package discord n'est pas dans les dépendances par défaut — le canal
se désactive proprement si l'import échoue (même garde que telegram_bot.py).

Variables d'environnement requises :
  DISCORD_BOT_TOKEN  — token du bot Discord
  DISCORD_OWNER_ID   — ID numérique (int) du seul utilisateur autorisé
"""

from __future__ import annotations

import os

from loguru import logger

from jarvis.interfaces.channels.base import (
    ChannelAdapter,
    DispatchCallback,
    IncomingMessage,
    MessageTarget,
    Platform,
)

try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordChannel(ChannelAdapter):
    """Adaptateur Discord pour le MessagingGateway Jarvis.

    Envoie un seul message par réponse à l'utilisateur autorisé.
    Tronque les réponses dépassant 2000 caractères (limite Discord).
    """

    platform = Platform.DISCORD  # type: ignore[assignment]

    def __init__(self) -> None:
        self._dispatch_cb: DispatchCallback | None = None
        self._token = os.getenv("DISCORD_BOT_TOKEN", "")
        self._owner_id = int(os.getenv("DISCORD_OWNER_ID", "0"))
        self._client: discord.Client | None = None  # type: ignore[name-defined]

    # ── ChannelAdapter ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not DISCORD_AVAILABLE:
            logger.warning("discord.py non installé — canal Discord désactivé")
            return
        if not self._token:
            logger.warning("DISCORD_BOT_TOKEN absent — canal Discord désactivé")
            return
        if not self._owner_id:
            logger.warning("DISCORD_OWNER_ID absent — canal Discord désactivé")
            return

        intents = discord.Intents.default()  # type: ignore[attr-defined]
        intents.message_content = True
        self._client = discord.Client(intents=intents)  # type: ignore[attr-defined]

        @self._client.event  # type: ignore[attr-defined]
        async def on_ready() -> None:
            logger.info("Canal Discord démarré", user=str(self._client.user))  # type: ignore[union-attr]

        @self._client.event  # type: ignore[attr-defined]
        async def on_message(message: discord.Message) -> None:  # type: ignore[name-defined]
            if message.author == self._client.user:  # type: ignore[union-attr]
                return
            if message.author.id != self._owner_id:
                await message.channel.send("⛔ Accès non autorisé.")
                return
            if not message.content:
                return

            logger.info("[Discord] Message reçu", text=message.content[:60])

            if self._dispatch_cb is not None:
                msg = IncomingMessage(
                    platform=Platform.DISCORD,
                    user_id=str(message.author.id),
                    text=message.content,
                    channel_id=str(message.channel.id),
                    raw=message,
                )
                await self._dispatch_cb(msg)
            else:
                logger.warning("[Discord] Aucun dispatch configuré — message ignoré")

        import asyncio

        asyncio.create_task(
            self._client.start(self._token),  # type: ignore[union-attr]
            name="discord-bot",
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()  # type: ignore[union-attr]

    async def send(self, reply: str, target: MessageTarget) -> None:
        """Envoie la réponse dans le canal d'origine (ou en DM si channel_id absent)."""
        if self._client is None:
            return
        text = reply[:1990] + "\n\n_[réponse tronquée]_" if len(reply) > 2000 else reply
        try:
            if target.channel_id:
                channel = self._client.get_channel(int(target.channel_id))  # type: ignore[union-attr]
                if channel is not None:
                    await channel.send(text)  # type: ignore[attr-defined]
                    return
            # Fallback : DM à l'owner
            user = await self._client.fetch_user(int(target.user_id))  # type: ignore[union-attr]
            await user.send(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Discord] Erreur envoi message", error=str(exc))
