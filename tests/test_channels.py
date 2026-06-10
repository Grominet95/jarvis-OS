"""Tests du gateway de messagerie unifié Jarvis.

Couvre :
  - Conformité ABC de tous les adaptateurs
  - Routage d'un message via MessagingGateway.dispatch()
  - Continuité de session cross-plateforme (même session_id restauré)
  - Mode dual de TelegramChannel (legacy vs dispatch_cb)
  - Router FastAPI /api/channels/{platform}/webhook
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.interfaces.channels.base import ChannelAdapter, IncomingMessage, MessageTarget, Platform

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_jarvis_gateway(session_id: str = "sess-abc", response: str = "Bonjour !") -> MagicMock:
    """Crée un core.Gateway mocké retournant un session.id fixe."""
    session = MagicMock()
    session.id = session_id
    gw = MagicMock()
    gw.handle = AsyncMock(return_value=(session, "chat", response))
    return gw


def _make_incoming(
    platform: Platform = Platform.TELEGRAM,
    user_id: str = "42",
    text: str = "Salut Jarvis",
    channel_id: str = "100",
) -> IncomingMessage:
    return IncomingMessage(
        platform=platform,
        user_id=user_id,
        text=text,
        channel_id=channel_id,
    )


# ── Tests conformité ABC ──────────────────────────────────────────────────────


def test_channel_adapter_est_abstract() -> None:
    """ChannelAdapter ne peut pas être instancié directement."""
    with pytest.raises(TypeError):
        ChannelAdapter()  # type: ignore[abstract]


def test_tous_les_stubs_implementent_linterface() -> None:
    """WhatsApp, Signal, Slack implémentent ChannelAdapter (sans TypeError)."""
    from jarvis.interfaces.channels.signal_bot import SignalChannel
    from jarvis.interfaces.channels.slack_bot import SlackChannel
    from jarvis.interfaces.channels.whatsapp import WhatsAppChannel

    for cls in (WhatsAppChannel, SignalChannel, SlackChannel):
        adapter = cls()
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.platform in Platform


def test_telegram_channel_est_un_channel_adapter() -> None:
    from jarvis.interfaces.channels.telegram_bot import TelegramChannel

    ch = TelegramChannel()
    assert isinstance(ch, ChannelAdapter)
    assert ch.platform == Platform.TELEGRAM


def test_discord_channel_est_un_channel_adapter() -> None:
    from jarvis.interfaces.channels.discord_bot import DiscordChannel

    ch = DiscordChannel()
    assert isinstance(ch, ChannelAdapter)
    assert ch.platform == Platform.DISCORD


# ── Tests IncomingMessage ─────────────────────────────────────────────────────


def test_session_key_format() -> None:
    msg = _make_incoming(platform=Platform.TELEGRAM, user_id="99")
    assert msg.session_key == "telegram:99"


def test_session_key_discord() -> None:
    msg = _make_incoming(platform=Platform.DISCORD, user_id="456")
    assert msg.session_key == "discord:456"


# ── Tests MessagingGateway.dispatch() ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_appelle_jarvis_et_envoie_reponse(tmp_path: Path) -> None:
    """dispatch() appelle jarvis_gateway.handle() et adapter.send()."""
    from jarvis.interfaces.channels.gateway import MessagingGateway

    jarvis_gw = _make_jarvis_gateway(session_id="sess-1", response="OK !")
    gw = MessagingGateway(jarvis_gateway=jarvis_gw, session_map_path=tmp_path / "sessions.json")

    sent: list[tuple[str, MessageTarget]] = []

    class FakeAdapter(ChannelAdapter):
        platform = Platform.TELEGRAM  # type: ignore[assignment]

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send(self, reply: str, target: MessageTarget) -> None:
            sent.append((reply, target))

    gw.register(FakeAdapter())
    msg = _make_incoming(text="Bonjour", user_id="1")
    await gw.dispatch(msg)

    jarvis_gw.handle.assert_awaited_once()
    assert len(sent) == 1
    assert sent[0][0] == "OK !"
    assert sent[0][1].user_id == "1"


@pytest.mark.asyncio
async def test_dispatch_session_id_passe_au_deuxieme_appel(tmp_path: Path) -> None:
    """Le session_id retourné au 1er dispatch est reutilisé au 2ème."""
    from jarvis.interfaces.channels.gateway import MessagingGateway

    jarvis_gw = _make_jarvis_gateway(session_id="sess-xyz")
    gw = MessagingGateway(jarvis_gateway=jarvis_gw, session_map_path=tmp_path / "sessions.json")

    class FakeAdapter(ChannelAdapter):
        platform = Platform.TELEGRAM  # type: ignore[assignment]

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send(self, reply: str, target: MessageTarget) -> None:
            pass

    gw.register(FakeAdapter())
    msg = _make_incoming(user_id="7")

    await gw.dispatch(msg)
    await gw.dispatch(msg)

    calls = jarvis_gw.handle.call_args_list
    assert calls[0].kwargs.get("session_id") is None or calls[0].kwargs["session_id"] is None
    assert calls[1].kwargs["session_id"] == "sess-xyz"


# ── Tests continuité de session cross-plateforme ──────────────────────────────


@pytest.mark.asyncio
async def test_continuite_session_meme_user_cross_plateforme(tmp_path: Path) -> None:
    """Deux plateformes différentes ont des sessions indépendantes pour le même user_id."""
    from jarvis.interfaces.channels.gateway import MessagingGateway

    jarvis_gw = MagicMock()
    sess_tg = MagicMock()
    sess_tg.id = "sess-telegram"
    sess_dc = MagicMock()
    sess_dc.id = "sess-discord"
    jarvis_gw.handle = AsyncMock(
        side_effect=[
            (sess_tg, "chat", "tg-resp"),
            (sess_dc, "chat", "dc-resp"),
        ]
    )

    gw = MessagingGateway(jarvis_gateway=jarvis_gw, session_map_path=tmp_path / "sessions.json")

    class FakeAdapter(ChannelAdapter):
        def __init__(self, plat: Platform) -> None:
            self._plat = plat

        @property
        def platform(self) -> Platform:
            return self._plat

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send(self, reply: str, target: MessageTarget) -> None:
            pass

    gw.register(FakeAdapter(Platform.TELEGRAM))
    gw.register(FakeAdapter(Platform.DISCORD))

    tg_msg = _make_incoming(platform=Platform.TELEGRAM, user_id="42")
    dc_msg = _make_incoming(platform=Platform.DISCORD, user_id="42")

    await gw.dispatch(tg_msg)
    await gw.dispatch(dc_msg)

    assert gw._session_map["telegram:42"] == "sess-telegram"
    assert gw._session_map["discord:42"] == "sess-discord"


@pytest.mark.asyncio
async def test_session_map_persistee_sur_disque(tmp_path: Path) -> None:
    """La session map est sauvegardée en JSON après dispatch."""
    from jarvis.interfaces.channels.gateway import MessagingGateway

    jarvis_gw = _make_jarvis_gateway(session_id="persisted-id")
    path = tmp_path / "map.json"
    gw = MessagingGateway(jarvis_gateway=jarvis_gw, session_map_path=path)

    class FakeAdapter(ChannelAdapter):
        platform = Platform.TELEGRAM  # type: ignore[assignment]

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send(self, reply: str, target: MessageTarget) -> None:
            pass

    gw.register(FakeAdapter())
    await gw.dispatch(_make_incoming(user_id="99"))

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["telegram:99"] == "persisted-id"


@pytest.mark.asyncio
async def test_session_map_rechargee_depuis_disque(tmp_path: Path) -> None:
    """Une gateway relancée restaure la session map depuis le fichier JSON."""
    from jarvis.interfaces.channels.gateway import MessagingGateway

    path = tmp_path / "map.json"
    path.write_text(json.dumps({"telegram:5": "restored-sess"}), encoding="utf-8")

    jarvis_gw = _make_jarvis_gateway(session_id="new-sess")
    gw = MessagingGateway(jarvis_gateway=jarvis_gw, session_map_path=path)

    class FakeAdapter(ChannelAdapter):
        platform = Platform.TELEGRAM  # type: ignore[assignment]

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send(self, reply: str, target: MessageTarget) -> None:
            pass

    gw.register(FakeAdapter())
    await gw.dispatch(_make_incoming(user_id="5"))

    call_kwargs = jarvis_gw.handle.call_args.kwargs
    assert call_kwargs["session_id"] == "restored-sess"


# ── Tests TelegramChannel dual-mode ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_on_message_mode_dispatch_cb(tmp_path: Path) -> None:
    """Quand dispatch_cb est injecté, _on_message l'appelle en priorité."""
    from jarvis.interfaces.channels.telegram_bot import TelegramChannel

    ch = TelegramChannel()
    dispatched: list[IncomingMessage] = []

    async def fake_dispatch(msg: IncomingMessage) -> None:
        dispatched.append(msg)

    ch.set_dispatch(fake_dispatch)

    # Simule un Update Telegram
    update = MagicMock()
    update.effective_user.id = 42
    update.effective_chat.id = 100
    update.message.text = "Test dispatch"
    ctx = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    ch._owner_id = 42
    await ch._on_message(update, ctx)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Test dispatch"
    assert dispatched[0].platform == Platform.TELEGRAM
    assert dispatched[0].user_id == "42"


@pytest.mark.asyncio
async def test_telegram_on_message_mode_legacy() -> None:
    """Sans dispatch_cb, _on_message utilise le legacy gateway."""
    from jarvis.interfaces.channels.telegram_bot import TelegramChannel

    session = MagicMock()
    session.id = "leg-sess"
    legacy_gw = MagicMock()
    legacy_gw.handle = AsyncMock(return_value=(session, "chat", "Réponse legacy"))

    ch = TelegramChannel(gateway=legacy_gw)

    update = MagicMock()
    update.effective_user.id = 7
    update.effective_chat.id = 7
    update.message.text = "Hello"
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    ch._owner_id = 7
    await ch._on_message(update, ctx)

    legacy_gw.handle.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()
    call_args = update.message.reply_text.call_args
    assert "Réponse legacy" in call_args.args[0]


# ── Tests router FastAPI ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_plateforme_inconnue() -> None:
    """POST /api/channels/unknown/webhook → 404."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from jarvis.interfaces.api.channels import router

    test_app = FastAPI()
    test_app.include_router(router)
    client = TestClient(test_app, raise_server_exceptions=False)
    r = client.post("/api/channels/unknown/webhook", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_webhook_gateway_non_demarre() -> None:
    """POST /api/channels/telegram/webhook → 503 si messaging_gateway absent."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from jarvis.interfaces.api.channels import router

    test_app = FastAPI()
    test_app.include_router(router)
    client = TestClient(test_app, raise_server_exceptions=False)
    r = client.post("/api/channels/telegram/webhook", json={})
    assert r.status_code == 503
