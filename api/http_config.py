from __future__ import annotations

import json as _json
import os
from collections.abc import AsyncIterator
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.permissions import permissions as _perm_store

router = APIRouter()

# ── Helpers .env ──────────────────────────────────────────────────────────────

_ENV_PATH = Path(".env")

_SENSITIVE_KEYS = {
    "ANTHROPIC_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "GOOGLE_API_KEY",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "NOTION_TOKEN",
    "MISTRAL_API_KEY",
    "AISSTREAM_KEY",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "DEEZER_APP_ID",
    "DEEZER_APP_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
}

_RESTART_KEYS = {
    "ANTHROPIC_API_KEY",
    "ELEVENLABS_API_KEY",
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LLM_PROVIDER",
    "ANTHROPIC_MODEL",
    "VOICE_ANTHROPIC_MODEL",
    "TTS_PROVIDER",
    "ELEVENLABS_MODEL",
}

_SETTINGS_FIELD_MAP: dict[str, str] = {
    "TTS_PROVIDER": "tts_provider",
    "ELEVENLABS_MODEL": "elevenlabs_model",
    "ELEVENLABS_VOICE_ID": "elevenlabs_voice_id",
    "WHISPER_MODEL": "whisper_model",
    "LLM_PROVIDER": "llm_provider",
    "ANTHROPIC_MODEL": "anthropic_model",
    "VOICE_ANTHROPIC_MODEL": "voice_anthropic_model",
    "VISION_MODEL": "vision_model",
    "DOCKER_ENABLED": "docker_enabled",
    "DOCKER_BASE_IMAGE": "docker_base_image",
    "DOCKER_MEMORY_LIMIT": "docker_memory_limit",
    "DOCKER_CPU_LIMIT": "docker_cpu_limit",
    "DOCKER_TIMEOUT_SECONDS": "docker_timeout_seconds",
    "VISION_OBJECT_DETECTION": "vision_object_detection",
    "VISION_WEBCAM_INDEX": "vision_webcam_index",
    "VISION_YOLO_CONFIDENCE": "vision_yolo_confidence",
    "LOG_LEVEL": "log_level",
    "HOME_CITY": "home_city",
    "BRIEFING_HOUR": "briefing_hour",
    "CALENDAR_REMINDER_MINUTES": "calendar_reminder_minutes",
    "USER_FIRSTNAME": "user_firstname",
    "QUEBEC_MODE": "quebec_mode",
    "WAKEUP_ENABLED": "wakeup_enabled",
    "CLAP_DETECTION_ENABLED": "clap_detection_enabled",
    "MUSIC_PROVIDER": "music_provider",
    "DEEZER_APP_ID": "deezer_app_id",
    "DEEZER_APP_SECRET": "deezer_app_secret",
    "API_BACKEND": "api_backend",
    "OLLAMA_MODEL": "ollama_model",
    "OLLAMA_BASE_URL": "ollama_base_url",
}


def _mask(value: str) -> str:
    if not value or value.startswith("..."):
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return value[:4] + "•" * min(len(value) - 4, 24)


def _read_env() -> dict[str, str]:
    if not _ENV_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env(updates: dict[str, str]) -> None:
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines() if _ENV_PATH.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Permissions API ───────────────────────────────────────────────────────────


class PermissionPatch(BaseModel):
    enabled: bool


@router.get("/api/permissions")
async def get_permissions() -> dict[str, bool]:
    """Retourne l'état courant des permissions runtime."""
    return _perm_store.all()


@router.patch("/api/permissions/{key}")
async def patch_permission(key: str, body: PermissionPatch) -> dict[str, object]:
    """Active ou désactive une permission runtime (screen, camera, files)."""
    _perm_store.set(key, body.enabled)
    return {"key": key, "enabled": body.enabled}


# ── Settings API ──────────────────────────────────────────────────────────────


@router.get("/api/settings/env-status")
async def get_env_status(keys: str = Query("")) -> dict:
    """Retourne True/False par clé env — jamais les valeurs."""
    from dotenv import dotenv_values

    env_values = dotenv_values(".env")
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    return {k: bool(env_values.get(k, "").strip()) for k in key_list}


@router.get("/api/settings")
async def get_settings_endpoint() -> dict:
    import dataclasses as _dc

    from config.approvals import approval_config as _approval_cfg
    from config.settings import settings as _s

    env = _read_env()

    def _env_val(key: str) -> str:
        return env.get(key, os.getenv(key, ""))

    def _ev(key: str, field: str) -> Any:  # noqa: ANN401
        """Lit depuis .env d'abord (toujours frais), puis in-memory settings."""
        raw = env.get(key)
        if raw is None:
            return getattr(_s, field)
        field_info = type(_s).model_fields.get(field)
        ann = field_info.annotation if field_info else None
        if ann is bool:
            return raw.lower() in ("true", "1", "yes", "on")
        if ann is int:
            try:
                return int(raw)
            except (ValueError, TypeError):
                return getattr(_s, field)
        if ann is float:
            try:
                return float(raw)
            except (ValueError, TypeError):
                return getattr(_s, field)
        return raw

    api_keys_masked = {k: _mask(_env_val(k)) for k in sorted(_SENSITIVE_KEYS)}

    return {
        "audio": {
            "tts_provider": _ev("TTS_PROVIDER", "tts_provider"),
            "elevenlabs_model": _ev("ELEVENLABS_MODEL", "elevenlabs_model"),
            "whisper_model": _ev("WHISPER_MODEL", "whisper_model"),
        },
        "llm": {
            "llm_provider": _ev("LLM_PROVIDER", "llm_provider"),
            "api_backend": _ev("API_BACKEND", "api_backend"),
            "anthropic_model": _ev("ANTHROPIC_MODEL", "anthropic_model"),
            "voice_anthropic_model": _ev("VOICE_ANTHROPIC_MODEL", "voice_anthropic_model"),
            "vision_model": _ev("VISION_MODEL", "vision_model"),
            "ollama_model": _ev("OLLAMA_MODEL", "ollama_model"),
            "ollama_base_url": _ev("OLLAMA_BASE_URL", "ollama_base_url"),
        },
        "api_keys": api_keys_masked,
        "docker": {
            "docker_enabled": _ev("DOCKER_ENABLED", "docker_enabled"),
            "docker_base_image": _ev("DOCKER_BASE_IMAGE", "docker_base_image"),
            "docker_memory_limit": _ev("DOCKER_MEMORY_LIMIT", "docker_memory_limit"),
            "docker_cpu_limit": _ev("DOCKER_CPU_LIMIT", "docker_cpu_limit"),
            "docker_timeout_seconds": _ev("DOCKER_TIMEOUT_SECONDS", "docker_timeout_seconds"),
        },
        "proactive": {
            "home_city": _ev("HOME_CITY", "home_city"),
            "briefing_hour": _ev("BRIEFING_HOUR", "briefing_hour"),
            "calendar_reminder_minutes": _ev(
                "CALENDAR_REMINDER_MINUTES", "calendar_reminder_minutes"
            ),
        },
        "vision": {
            "vision_object_detection": _ev("VISION_OBJECT_DETECTION", "vision_object_detection"),
            "vision_webcam_index": _ev("VISION_WEBCAM_INDEX", "vision_webcam_index"),
            "vision_yolo_confidence": _ev("VISION_YOLO_CONFIDENCE", "vision_yolo_confidence"),
        },
        "memory": {
            "memory_dir": _ev("MEMORY_DIR", "memory_dir"),
        },
        "jarvis": {
            "user_firstname": _ev("USER_FIRSTNAME", "user_firstname"),
            "quebec_mode": _ev("QUEBEC_MODE", "quebec_mode"),
            "wakeup_enabled": _ev("WAKEUP_ENABLED", "wakeup_enabled"),
            "clap_detection_enabled": _ev("CLAP_DETECTION_ENABLED", "clap_detection_enabled"),
            "log_level": _ev("LOG_LEVEL", "log_level"),
            "environment": _ev("ENVIRONMENT", "environment"),
        },
        "music": {
            "music_provider": _ev("MUSIC_PROVIDER", "music_provider"),
        },
        "approvals": _dc.asdict(_approval_cfg),
    }


class SettingUpdateBody(BaseModel):
    key: str
    value: str


@router.post("/api/settings/update")
async def update_setting(body: SettingUpdateBody) -> dict:
    from config.settings import settings as _s

    env_key = body.key.upper()
    _write_env({env_key: body.value})
    os.environ[env_key] = body.value

    field_name = _SETTINGS_FIELD_MAP.get(env_key)
    if field_name and hasattr(_s, field_name):
        fields = type(_s).model_fields
        field = fields.get(field_name)
        annotation = field.annotation if field else None
        try:
            if annotation is bool:
                converted: Any = body.value.lower() in ("true", "1", "yes", "on")
            elif annotation is int:
                converted = int(body.value)
            elif annotation is float:
                converted = float(body.value)
            else:
                converted = body.value
            object.__setattr__(_s, field_name, converted)
        except (ValueError, TypeError):
            object.__setattr__(_s, field_name, body.value)

    needs_restart = env_key in _RESTART_KEYS
    return {"ok": True, "key": body.key, "needs_restart": needs_restart}


# ── Ollama ────────────────────────────────────────────────────────────────────


@router.get("/api/ollama/models")
async def get_ollama_models() -> dict:
    """Liste les modèles téléchargés sur le serveur Ollama local."""
    from config.settings import settings as _s

    base_url = _s.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return {"available": True, "models": data.get("models", [])}
    except Exception:
        return {"available": False, "models": []}


class OllamaPullBody(BaseModel):
    model: str


@router.post("/api/ollama/pull")
async def pull_ollama_model(body: OllamaPullBody) -> StreamingResponse:
    """Télécharge un modèle Ollama en streaming SSE (progress events)."""
    from config.settings import settings as _s

    base_url = _s.ollama_base_url.rstrip("/")

    async def _stream() -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/pull",
                    json={"name": body.model, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield f"data: {line}\n\n"
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield 'data: {"done":true}\n\n'

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Devices ───────────────────────────────────────────────────────────────────

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
    import json as _json
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
        from hardware.macropad_2k.usb import usb_status

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
    import json as _json

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
                from datetime import datetime as _dt

                exp = _dt.fromisoformat(expiry.replace("Z", "+00:00"))
                if exp < _dt.now(UTC):
                    return "expired"
            return "on"
        except Exception:
            return "on"

    from config.settings import settings as _s

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


@router.get("/api/settings/voices")
async def get_voices() -> list[dict]:
    import httpx

    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": key},
            )
        if r.status_code == 200:
            voices = r.json().get("voices", [])
            return [{"id": v["voice_id"], "name": v["name"]} for v in voices]
    except Exception:
        pass
    return []


class TestKeyBody(BaseModel):
    provider: str
    key: str


@router.post("/api/settings/test-key")
async def test_api_key(body: TestKeyBody) -> dict:
    import httpx

    provider = body.provider.lower()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if provider == "anthropic":
                r = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": body.key, "anthropic-version": "2023-06-01"},
                )
                return {"ok": r.status_code == 200}
            if provider == "elevenlabs":
                r = await client.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": body.key},
                )
                return {"ok": r.status_code == 200}
            if provider == "openai":
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {body.key}"},
                )
                return {"ok": r.status_code == 200}
            if provider == "deepgram":
                r = await client.get(
                    "https://api.deepgram.com/v1/projects",
                    headers={"Authorization": f"Token {body.key}"},
                )
                return {"ok": r.status_code == 200}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "Provider inconnu"}


# ── Approvals API ─────────────────────────────────────────────────────────────


@router.get("/api/approvals/config")
async def get_approvals_config() -> dict:
    """Retourne la configuration courante des approbations."""
    from dataclasses import asdict

    from config.approvals import approval_config

    return asdict(approval_config)


class ApprovalCategoryUpdate(BaseModel):
    mode: str  # "always" | "ask" | "never"


@router.patch("/api/approvals/config/{category}")
async def update_approval_category(category: str, body: ApprovalCategoryUpdate) -> dict:
    """Met à jour le mode d'une catégorie d'approbation."""
    from config.approvals import ApprovalMode, approval_config, save_approval_config

    if not hasattr(approval_config, category):
        raise HTTPException(404, f"Catégorie inconnue: {category}")
    try:
        mode = ApprovalMode(body.mode)
    except ValueError:
        msg = f"Mode invalide: {body.mode}. Valeurs: always, ask, never"
        raise HTTPException(400, msg) from None
    object.__setattr__(approval_config, category, mode)
    save_approval_config(approval_config)
    return {"category": category, "mode": body.mode}


class ApprovalResolveBody(BaseModel):
    approved: bool


@router.post("/api/approvals/{action_id}/resolve")
async def resolve_approval(action_id: str, body: ApprovalResolveBody, request: Request) -> dict:
    """Résout une demande d'approbation en attente."""
    checker = getattr(request.app.state, "approval_checker", None)
    if checker is None:
        raise HTTPException(503, "ApprovalChecker non disponible")
    checker.resolve(action_id, body.approved)
    return {"status": "ok", "approved": body.approved}
