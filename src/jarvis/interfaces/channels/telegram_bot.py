"""Canal Telegram pour Jarvis.

Implémente ChannelAdapter pour s'intégrer au MessagingGateway unifié.
Compatible avec l'ancien mode (gateway= passé directement au constructeur)
pour ne pas casser le démarrage existant dans main.py.

Un seul utilisateur autorisé : TELEGRAM_OWNER_ID.
"""

from __future__ import annotations

import logging
import os

from loguru import logger


class _TelegramNetworkFilter(logging.Filter):
    """Réduit les NetworkError/ConnectError du polling loop en DEBUG (spam hors-ligne).

    Couvre python-telegram-bot v20 (requests) et v21+ (httpx).
    """

    _NOISE = (
        "NetworkError",
        "ConnectError",
        "TimedOut",
        "polling for updates",
        "httpcore",
        "ConnectTimeout",
        "ReadError",
        "RemoteProtocolError",
        "Connection refused",
        "getaddrinfo failed",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(kw in msg for kw in self._NOISE):
            if record.levelno >= logging.ERROR:
                logging.getLogger("telegram.ext._utils.networkloop").debug(
                    "Telegram hors-ligne — retry automatique en cours"
                )
            return False
        return True


# Appliqué une seule fois au module level sur toute la hiérarchie telegram + httpx
_tg_filter = _TelegramNetworkFilter()
logging.getLogger("telegram").addFilter(_tg_filter)
logging.getLogger("httpx").addFilter(_tg_filter)

from jarvis.interfaces.channels.base import (  # noqa: E402
    ChannelAdapter,
    DispatchCallback,
    IncomingMessage,
    MessageTarget,
    Platform,
)

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


_telegram_instance: TelegramChannel | None = None


def get_telegram_channel() -> TelegramChannel | None:
    return _telegram_instance


class TelegramChannel(ChannelAdapter):
    """Canal Telegram pour Jarvis.

    Peut fonctionner en deux modes :
    - Mode legacy : gateway= (core.Gateway) passé directement, session créée à chaque message
    - Mode MessagingGateway : set_dispatch() injecte le callback, session persistée cross-messages
    """

    platform = Platform.TELEGRAM  # type: ignore[assignment]

    def __init__(self, gateway: object = None) -> None:
        self._legacy_gateway = gateway
        self._dispatch_cb: DispatchCallback | None = None
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._owner_id = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
        self._app: Application | None = None  # type: ignore[type-arg]
        self._started = False

    # ── ChannelAdapter ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Démarre le polling Telegram (idempotent)."""
        if self._started:
            return
        if not TELEGRAM_AVAILABLE:
            logger.warning("python-telegram-bot non installé — canal Telegram désactivé")
            return
        if not self._token:
            logger.warning("TELEGRAM_BOT_TOKEN absent — canal Telegram désactivé")
            return
        if not self._owner_id:
            logger.warning("TELEGRAM_OWNER_ID absent — canal Telegram désactivé")
            return

        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("initiatives", self._cmd_initiatives))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_error_handler(self._on_error)

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._started = True
        logger.info("Canal Telegram démarré")

    async def _on_error(self, update: object, context: object) -> None:
        """Dégrade les NetworkError hors-ligne en DEBUG pour éviter le spam de logs."""
        exc = getattr(context, "error", None)
        if exc is None:
            return
        exc_name = type(exc).__name__
        if "NetworkError" in exc_name or "ConnectError" in exc_name or "TimedOut" in exc_name:
            logger.debug("Telegram hors-ligne — retry automatique ({})", exc_name)
        else:
            logger.error("Telegram error: {}", exc)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._started = False

    async def send(self, reply: str, target: MessageTarget) -> None:
        """Envoie une réponse à l'utilisateur Telegram désigné par target."""
        if not self._app:
            return
        chat_id = target.channel_id or target.user_id
        if not chat_id:
            return
        text = reply[:4000] + "\n\n_[réponse tronquée]_" if len(reply) > 4000 else reply
        await self._app.bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode="Markdown",
        )

    # ── Notification proactive (mode legacy) ─────────────────────────────────

    async def send_message(self, text: str) -> None:
        """Envoie un message proactif à l'owner (notifications Jarvis)."""
        if self._app and self._owner_id:
            await self._app.bot.send_message(
                chat_id=self._owner_id,
                text=text,
                parse_mode="Markdown",
            )

    # ── Handlers internes ─────────────────────────────────────────────────────

    def _is_owner(self, update: Update) -> bool:  # type: ignore[name-defined]
        return update.effective_user.id == self._owner_id

    async def _on_message(
        self,
        update: Update,  # type: ignore[name-defined]
        ctx: ContextTypes.DEFAULT_TYPE,  # type: ignore[name-defined]
    ) -> None:
        if not self._is_owner(update):
            await update.message.reply_text("⛔ Accès non autorisé.")
            return

        user_text = update.message.text
        logger.info("[Telegram] Message reçu", text=user_text[:60])

        await ctx.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        # Mode MessagingGateway (prioritaire)
        if self._dispatch_cb is not None:
            msg = IncomingMessage(
                platform=Platform.TELEGRAM,
                user_id=str(update.effective_user.id),
                text=user_text,
                channel_id=str(update.effective_chat.id),
                raw=update,
            )
            await self._dispatch_cb(msg)
            return

        # Mode legacy
        if self._legacy_gateway is not None:
            _, _route, response = await self._legacy_gateway.handle(
                user_text,
                stream=False,
            )
            text = str(response)
            if len(text) > 4000:
                text = text[:3990] + "\n\n_[réponse tronquée]_"
            await update.message.reply_text(text, parse_mode="Markdown")
            return

        logger.warning("[Telegram] Aucun gateway configuré — message ignoré")

    async def _cmd_start(
        self,
        update: Update,  # type: ignore[name-defined]
        ctx: ContextTypes.DEFAULT_TYPE,  # type: ignore[name-defined]
    ) -> None:
        if not self._is_owner(update):
            return
        await update.message.reply_text(
            "🤖 *Jarvis connecté.*\n\n"
            "Envoie-moi n'importe quel message ou utilise les commandes :\n"
            "/status — état du système\n"
            "/initiatives — tes initiatives en attente\n"
            "/help — toutes les commandes",
            parse_mode="Markdown",
        )

    async def _cmd_status(
        self,
        update: Update,  # type: ignore[name-defined]
        ctx: ContextTypes.DEFAULT_TYPE,  # type: ignore[name-defined]
    ) -> None:
        if not self._is_owner(update):
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:8000/api/health")
                health = r.json()
            checks = health.get("checks", {})
            lines = []
            for name, info in checks.items():
                emoji = (
                    "✅" if info["status"] == "ok" else "⚠️" if info["status"] == "warning" else "❌"
                )
                lines.append(f"{emoji} *{name}* — {info['detail']}")
            text = "🖥 *Jarvis Doctor*\n\n" + "\n".join(lines)
        except Exception as e:  # noqa: BLE001
            text = f"❌ Impossible de joindre Jarvis : {e}"
        await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_initiatives(
        self,
        update: Update,  # type: ignore[name-defined]
        ctx: ContextTypes.DEFAULT_TYPE,  # type: ignore[name-defined]
    ) -> None:
        if not self._is_owner(update):
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("http://localhost:8000/api/initiatives")
                data = r.json()
            initiatives = [i for i in data.get("initiatives", []) if i.get("status") == "pending"]
            if not initiatives:
                await update.message.reply_text("✅ Aucune initiative en attente.")
                return
            lines = [f"⚡ *{len(initiatives)} initiative(s) en attente*\n"]
            for ini in initiatives[:5]:
                priority = ini.get("priority", "")
                emoji = "🔴" if priority == "high" else "🟡" if priority == "medium" else "⚪"
                lines.append(f"{emoji} {ini.get('title', '?')}")
            if len(initiatives) > 5:
                lines.append(f"\n_+{len(initiatives) - 5} autres — voir le Command Center_")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:  # noqa: BLE001
            await update.message.reply_text(f"❌ Erreur : {e}")

    async def _cmd_help(
        self,
        update: Update,  # type: ignore[name-defined]
        ctx: ContextTypes.DEFAULT_TYPE,  # type: ignore[name-defined]
    ) -> None:
        if not self._is_owner(update):
            return
        text = (
            "🤖 *Jarvis — Commandes Telegram*\n\n"
            "*/status* — état de tous les composants\n"
            "*/initiatives* — liste des initiatives en attente\n"
            "*/help* — cette aide\n\n"
            "*Message libre* — parle à Jarvis normalement :\n"
            '• _"Quelle est la météo à Lyon ?"\n'
            '• "Lance le preset travail"\n'
            '• "Mets du Booba sur Spotify"\n'
            '• "Quelles sont mes tâches du jour ?"\n'
            '• "État de mon impression 3D ?"_'
        )
        await update.message.reply_text(text, parse_mode="Markdown")
