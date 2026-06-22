# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import base64
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from jeepney import DBusAddress, Properties, new_method_call
from jeepney.io.blocking import DBusConnection, open_dbus_connection
from loguru import logger

router = APIRouter(prefix="/api/local-music")

# Pochette : on n'embarque que des fichiers locaux raisonnables (anti-DoS mémoire).
_ART_MAX_BYTES = 5 * 1024 * 1024

# ── Backend macOS : nowplaying-cli (champs ligne par ligne) ───────────────────
_FIELDS = ["title", "artist", "album", "artworkURL", "playbackRate", "duration", "elapsedTime"]

# ── Backend Linux : MPRIS2 via D-Bus (jeepney, multi-distro, sans binaire) ────
_MPRIS_PREFIX = "org.mpris.MediaPlayer2."
_MPRIS_PATH = "/org/mpris/MediaPlayer2"
_MPRIS_IFACE = "org.mpris.MediaPlayer2.Player"
_MPRIS_METHODS = {"play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous"}

_DBUS_DAEMON = DBusAddress(
    "/org/freedesktop/DBus", bus_name="org.freedesktop.DBus", interface="org.freedesktop.DBus"
)


def _backend() -> str | None:
    """Stratégie "now playing" : macOS (nowplaying-cli) ou Linux (MPRIS/D-Bus)."""
    if shutil.which("nowplaying-cli"):
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


# ── macOS ─────────────────────────────────────────────────────────────────────
async def _run(cmd: str, *args: str) -> str | None:
    """Exécute nowplaying-cli (macOS)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "nowplaying-cli",
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return stdout.decode().strip()
    except FileNotFoundError:
        logger.debug("nowplaying-cli not installed")
        return None
    except (TimeoutError, Exception) as e:  # noqa: BLE001
        logger.debug("nowplaying-cli error", error=str(e))
        return None


def _macos_state_from_output(output: str) -> dict:
    """Parse la sortie de `nowplaying-cli get`."""
    lines = output.split("\n")
    if len(lines) < len(_FIELDS):
        return {"connected": True, "is_playing": False, "track": None}

    values = dict(zip(_FIELDS, lines, strict=False))
    title = values.get("title", "")
    if not title or title == "null":
        return {"connected": True, "is_playing": False, "track": None}

    try:
        rate = float(values.get("playbackRate") or 0)
    except ValueError:
        rate = 0.0
    try:
        duration_ms = int(float(values.get("duration") or 0) * 1000)
    except ValueError:
        duration_ms = 0
    try:
        progress_ms = int(float(values.get("elapsedTime") or 0) * 1000)
    except ValueError:
        progress_ms = 0

    art = values.get("artworkURL", "")
    return {
        "connected": True,
        "is_playing": rate > 0,
        "track": title,
        "artist": values.get("artist", "") or "",
        "album": values.get("album", "") or "",
        "album_art": art if art and art != "null" else None,
        "progress_ms": progress_ms,
        "duration_ms": duration_ms,
    }


async def _macos_player_state() -> dict:
    output = await _run("get", *_FIELDS)
    if output is None:
        return {"connected": False}
    return _macos_state_from_output(output)


# ── Linux (MPRIS / D-Bus) ──────────────────────────────────────────────────────
def _sniff_mime(data: bytes) -> str:
    if data[:8].startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _resolve_art(art_url: str) -> str | None:
    """URL de pochette utilisable par le navigateur.

    http(s)/data → tels quels ; file:// → lus et embarqués en data: URI (le
    navigateur refuse les file:// servis depuis une page http). Sinon None.
    """
    if not art_url:
        return None
    if art_url.startswith(("http://", "https://", "data:")):
        return art_url
    if art_url.startswith("file://"):
        try:
            path = Path(unquote(urlparse(art_url).path))
            if not path.is_file() or path.stat().st_size > _ART_MAX_BYTES:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        return f"data:{_sniff_mime(data)};base64,{base64.b64encode(data).decode('ascii')}"
    return None


def _state_from_mpris(status: str, metadata: dict, position_us: int) -> dict:
    """Construit l'état lecteur depuis les propriétés MPRIS (variants déjà déballés)."""
    title = str(metadata.get("xesam:title") or "").strip()
    if not title:
        return {"connected": True, "is_playing": False, "track": None}

    artist_val = metadata.get("xesam:artist")
    if isinstance(artist_val, (list, tuple)):
        artist = ", ".join(str(a) for a in artist_val)
    else:
        artist = str(artist_val or "")

    try:
        duration_ms = int(metadata.get("mpris:length") or 0) // 1000
    except (ValueError, TypeError):
        duration_ms = 0

    return {
        "connected": True,
        "is_playing": status == "Playing",
        "track": title,
        "artist": artist,
        "album": str(metadata.get("xesam:album") or ""),
        "album_art": _resolve_art(str(metadata.get("mpris:artUrl") or "")),
        "progress_ms": int(position_us) // 1000,
        "duration_ms": duration_ms,
    }


def _list_players(conn: DBusConnection) -> list[str]:
    names = conn.send_and_get_reply(new_method_call(_DBUS_DAEMON, "ListNames")).body[0]
    return [n for n in names if n.startswith(_MPRIS_PREFIX)]


def _pick_player(conn: DBusConnection, players: list[str]) -> str:
    """Préfère un lecteur en cours de lecture, sinon le premier disponible."""
    for p in players:
        try:
            props = Properties(DBusAddress(_MPRIS_PATH, bus_name=p, interface=_MPRIS_IFACE))
            status = conn.send_and_get_reply(props.get("PlaybackStatus")).body[0][1]
            if status == "Playing":
                return p
        except Exception:  # noqa: BLE001
            continue
    return players[0]


def _mpris_state_blocking() -> dict:
    """Lit l'état MPRIS via D-Bus (bloquant — à lancer dans un thread)."""
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception as e:  # noqa: BLE001
        logger.debug("Session D-Bus indisponible", error=str(e))
        return {"connected": False}
    try:
        players = _list_players(conn)
        if not players:
            return {"connected": True, "is_playing": False, "track": None}
        props = Properties(
            DBusAddress(_MPRIS_PATH, bus_name=_pick_player(conn, players), interface=_MPRIS_IFACE)
        )
        status = conn.send_and_get_reply(props.get("PlaybackStatus")).body[0][1]
        raw_meta = conn.send_and_get_reply(props.get("Metadata")).body[0][1]
        metadata = {k: v[1] for k, v in raw_meta.items()}
        try:
            position = conn.send_and_get_reply(props.get("Position")).body[0][1]
        except Exception:  # noqa: BLE001
            position = 0
        return _state_from_mpris(status, metadata, int(position or 0))
    except Exception as e:  # noqa: BLE001
        logger.debug("Lecture MPRIS échouée", error=str(e))
        return {"connected": True, "is_playing": False, "track": None}
    finally:
        conn.close()


def _mpris_control_blocking(method: str) -> None:
    """Envoie une commande MPRIS (Play/Pause/Next/Previous)."""
    try:
        conn = open_dbus_connection(bus="SESSION")
    except Exception:  # noqa: BLE001
        return
    try:
        players = _list_players(conn)
        if not players:
            return
        addr = DBusAddress(
            _MPRIS_PATH, bus_name=_pick_player(conn, players), interface=_MPRIS_IFACE
        )
        conn.send_and_get_reply(new_method_call(addr, method))
    except Exception as e:  # noqa: BLE001
        logger.debug("Contrôle MPRIS échoué", error=str(e))
    finally:
        conn.close()


# ── Dispatch ────────────────────────────────────────────────────────────────────
async def _get_player_state() -> dict:
    backend = _backend()
    if backend == "macos":
        return await _macos_player_state()
    if backend == "linux":
        return await asyncio.to_thread(_mpris_state_blocking)
    return {"connected": False}


async def _control(action: str) -> None:
    backend = _backend()
    if backend == "macos":
        await _run(action)
    elif backend == "linux":
        await asyncio.to_thread(_mpris_control_blocking, _MPRIS_METHODS[action])


@router.get("/player")
async def get_player() -> JSONResponse:
    return JSONResponse(await _get_player_state())


@router.post("/play")
async def play() -> JSONResponse:
    await _control("play")
    return JSONResponse({"ok": True})


@router.post("/pause")
async def pause() -> JSONResponse:
    await _control("pause")
    return JSONResponse({"ok": True})


@router.post("/next")
async def next_track() -> JSONResponse:
    await _control("next")
    return JSONResponse({"ok": True})


@router.post("/previous")
async def previous_track() -> JSONResponse:
    await _control("previous")
    return JSONResponse({"ok": True})
