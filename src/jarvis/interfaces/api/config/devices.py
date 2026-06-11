"""Devices + Connectors API — Phase E §E.1.3.

Routes :
  - GET /api/settings/devices — host, Macropad, Bluetooth (macOS/Windows).
  - GET /api/settings/connectors — état des intégrations (Gmail, Spotify, …).
"""

from __future__ import annotations

import json as _json
import os
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path

from fastapi import APIRouter

from config.settings import settings as _s
from jarvis.hardware.macropad_2k.usb import usb_status
from jarvis.interfaces.api.config._env import _read_env

router = APIRouter()


_BT_ID_MAP = {
    "headphones": "audio · BT",
    "headset": "audio · BT",
    "mouse": "mouse · BT",
    "keyboard": "keyboard · BT",
    "gamepad": "gamepad · BT",
    "joystick": "gamepad · BT",
}


def _parse_bt_macos(out: str, devices: list) -> None:
    import re

    section: str | None = None
    cur: dict | None = None

    def _flush(d: dict | None) -> None:
        if not d:
            return
        name = d["_name"]
        if re.fullmatch(r"[0-9A-Fa-f:]+", name):
            return
        bt_type = d["_type"] or "Device"
        connected = d["_connected"]
        devices.append(
            {
                "name": name,
                "id": _BT_ID_MAP.get(bt_type.lower(), "bluetooth · BT"),
                "status": "Connected" if connected else "Nearby",
                "col": "green" if connected else "muted",
                "a": ["Type", bt_type],
                "b": ["Vendor", d["_vendor"] or "—"],
                "type": "bluetooth",
            }
        )

    for line in out.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 6 and stripped.endswith(":"):
            _flush(cur)
            cur = None
            if "Not Connected" in stripped:
                section = "not_connected"
            elif "Connected" in stripped:
                section = "connected"
            else:
                section = None
            continue

        if section is None:
            continue

        if indent == 10 and stripped.endswith(":"):
            _flush(cur)
            cur = {
                "_name": stripped[:-1],
                "_connected": section == "connected",
                "_type": None,
                "_vendor": None,
            }
            continue

        if cur and indent >= 14 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if key == "Minor Type":
                cur["_type"] = val
            elif key == "Vendor ID" and "004C" in val:
                cur["_vendor"] = "Apple"

    _flush(cur)


def _parse_bt_windows(devices: list) -> None:
    import re
    import subprocess

    skip = re.compile(
        r"(?i)enumerator|microsoft\s+bluetooth|^\s*intel\(r\)\s+wireless\s+bluetooth|"
        r"realtek\s+bluetooth|broadcom\s+bluetooth|virtual|rfcomm|"
        r"generic\s+attribute|device\s+association|le\s+audio|"
        r"^bluetooth\s+device\s*\("
    )
    ps = (
        "Get-PnpDevice -Class 'Bluetooth' -PresentOnly | "
        "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps],
        text=True,
        timeout=12,
    )
    items = _json.loads(out)
    if isinstance(items, dict):
        items = [items]
    seen: set[str] = set()
    for item in items:
        name = (item.get("FriendlyName") or "").strip() or "Unknown"
        if skip.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        status = (item.get("Status") or "Unknown").strip()
        ok = status == "OK"
        nl = name.lower()
        if "mouse" in nl:
            bt_id = _BT_ID_MAP["mouse"]
        elif "keyboard" in nl:
            bt_id = _BT_ID_MAP["keyboard"]
        elif "headphone" in nl or "headset" in nl or "airpods" in nl or "buds" in nl:
            bt_id = _BT_ID_MAP["headphones"]
        elif "gamepad" in nl or "controller" in nl or "xbox" in nl or "dualshock" in nl:
            bt_id = _BT_ID_MAP["gamepad"]
        else:
            bt_id = "bluetooth · BT"
        devices.append(
            {
                "name": name,
                "id": bt_id,
                "status": "Connected" if ok else "Nearby",
                "col": "green" if ok else "muted",
                "a": ["Type", "Bluetooth"],
                "b": ["État", status],
                "type": "bluetooth",
            }
        )


@router.get("/api/settings/devices")
async def get_devices() -> list:
    import platform
    import subprocess

    import psutil

    devices: list[dict] = []
    sys_name = platform.system()

    cpu_pct = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    ram_used = round(mem.used / (1024**3), 1)
    ram_total = round(mem.total / (1024**3), 1)
    battery = psutil.sensors_battery()

    if sys_name == "Darwin":
        try:
            model = subprocess.check_output(  # noqa: ASYNC221
                ["sysctl", "-n", "hw.model"], text=True, timeout=3
            ).strip()
        except Exception:
            model = platform.node().replace(".local", "") or "Mac"
        chip = platform.processor() or platform.machine()
        host_id = f"mac · {chip}"
    elif sys_name == "Windows":
        model = platform.node()
        host_id = f"windows · {platform.machine()}"
    else:
        model = platform.node().replace(".local", "") or "Linux"
        host_id = f"linux · {platform.machine()}"

    devices.append(
        {
            "name": model,
            "id": host_id,
            "status": "Active",
            "col": "green",
            "a": ["CPU", f"{cpu_pct}%"],
            "b": (
                ["Battery", f"{int(battery.percent)}%"]
                if battery
                else ["RAM", f"{ram_used} / {ram_total} GB"]
            ),
            "type": "host",
        }
    )

    try:
        st = usb_status()
        hid = bool(st.get("hidPresent"))
        boot = bool(st.get("bootloaderPresent"))
        if hid:
            mp_status = "Connected"
            mp_col = "green"
            a_pair = ("Mode", "HID")
            b_pair = ("Firmware", "Macropad 2 touches Le Labo")
        elif boot:
            mp_status = "Nearby"
            mp_col = "accent"
            a_pair = ("Mode", "Bootloader")
            b_pair = ("Flash", "USB prêt")
        else:
            mp_status = "Nearby"
            mp_col = "muted"
            a_pair = ("Mode", "—")
            b_pair = ("Studio", "Configurer le Macropad")
        devices.insert(
            1,
            {
                "name": "Macropad 2 touches Le Labo",
                "id": "macropad 2 touches · Le Labo",
                "status": mp_status,
                "col": mp_col,
                "a": list(a_pair),
                "b": list(b_pair),
                "type": "macropad",
            },
        )
    except Exception:
        pass

    if sys_name == "Darwin":
        try:
            out = subprocess.check_output(  # noqa: ASYNC221
                ["system_profiler", "SPBluetoothDataType"], text=True, timeout=6
            )
            _parse_bt_macos(out, devices)
        except Exception:
            pass
    elif sys_name == "Windows":
        try:
            _parse_bt_windows(devices)
        except Exception:
            pass

    return devices


@router.get("/api/settings/connectors")
async def get_connectors() -> list:
    env = _read_env()

    def _env_ok(*keys: str) -> bool:
        def _valid(v: str) -> bool:
            v = v.strip()
            return bool(v) and not v.startswith("...") and v != "—"

        return all(_valid(env.get(k) or os.getenv(k, "")) for k in keys)

    def _token_status(path: str) -> str:
        p = Path(path)
        if not p.exists():
            return "off"
        try:
            data = _json.loads(p.read_text())
            expiry = data.get("expiry") or data.get("expires_at")
            if expiry:
                exp = _dt.fromisoformat(expiry.replace("Z", "+00:00"))
                if exp < _dt.now(UTC):
                    return "expired"
            return "on"
        except Exception:
            return "on"

    connectors = [
        {
            "name": "Gmail",
            "sub": "OAuth · lecture + envoi",
            "status": _token_status(
                _s.google_credentials_path.replace("credentials", "gmail_token")
            ),
        },
        {
            "name": "Google Calendar",
            "sub": "OAuth · lecture + écriture",
            "status": _token_status(_s.google_token_path),
        },
        {
            "name": "Spotify",
            "sub": "OAuth · lecture musicale",
            "status": (
                "on"
                if _token_status(_s.spotify_token_path) == "on"
                and _env_ok("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
                else "expired"
                if _token_status(_s.spotify_token_path) == "expired"
                else "off"
            ),
        },
        {
            "name": "Deezer",
            "sub": "OAuth · lecture musicale",
            "status": (
                "on"
                if _token_status(_s.deezer_token_path) == "on"
                and _env_ok("DEEZER_APP_ID", "DEEZER_APP_SECRET")
                else "expired"
                if _token_status(_s.deezer_token_path) == "expired"
                else "off"
            ),
        },
        {
            "name": "Notion",
            "sub": "token intégration · workspace",
            "status": "on" if _env_ok("NOTION_TOKEN") else "off",
        },
        {
            "name": "Anthropic (Claude)",
            "sub": "LLM principal",
            "status": "on" if _env_ok("ANTHROPIC_API_KEY") else "off",
        },
        {
            "name": "ElevenLabs",
            "sub": "TTS — voix de Jarvis",
            "status": "on" if _env_ok("ELEVENLABS_API_KEY") else "off",
        },
        {
            "name": "OpenAI",
            "sub": "Whisper STT / fallback LLM",
            "status": "on" if _env_ok("OPENAI_API_KEY") else "off",
        },
        {
            "name": "Google (API Key)",
            "sub": "Gemini · autres services Google",
            "status": "on" if _env_ok("GOOGLE_API_KEY") else "off",
        },
        {
            "name": "LiveKit",
            "sub": "agent vocal temps réel",
            "status": "on"
            if _env_ok("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
            else "off",
        },
        {
            "name": "Deepgram",
            "sub": "STT alternatif",
            "status": "on" if _env_ok("DEEPGRAM_API_KEY") else "off",
        },
        {
            "name": "Mistral",
            "sub": "LLM alternatif",
            "status": "on" if _env_ok("MISTRAL_API_KEY") else "off",
        },
        # ── Messagerie ───────────────────────────────────────────────────────
        {
            "name": "Telegram",
            "sub": "bot · messagerie mobile",
            "status": (
                "on"
                if (
                    _env_ok("TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_ID")
                    and env.get("TELEGRAM_ENABLED", "").lower() in ("true", "1")
                )
                else "off"
            ),
            "group": "messaging",
        },
        {
            "name": "Discord",
            "sub": "bot · serveur Discord",
            "status": (
                "on"
                if (
                    _env_ok("DISCORD_BOT_TOKEN", "DISCORD_OWNER_ID")
                    and env.get("DISCORD_ENABLED", "").lower() in ("true", "1")
                )
                else "off"
            ),
            "group": "messaging",
        },
        {
            "name": "WhatsApp",
            "sub": "bot · bientôt disponible (Twilio / WABA)",
            "status": "soon",
            "group": "messaging",
        },
    ]
    return connectors
