"""Helpers `.env` partagés par les sous-modules config (Phase E §E.1.3).

Constantes (clés sensibles, clés impactant runtime, mapping env→field
pydantic) + helpers de lecture/écriture/masking. Tout est privé : seuls
les sous-modules `config/*.py` les consomment.
"""

from __future__ import annotations

from pathlib import Path

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
    "ANTHROPIC_MODEL",
    "VOICE_ANTHROPIC_MODEL",
    "TTS_PROVIDER",
    "ELEVENLABS_MODEL",
}

# Ces clés déclenchent un hot-swap du provider LLM sans redémarrage.
_LLM_HOT_SWAP_KEYS = {"LLM_PROVIDER", "API_BACKEND", "OLLAMA_MODEL", "OLLAMA_BASE_URL"}

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
