from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

PREMADE_FALLBACK_VOICE_ID = "hpp4J3VqNfWAUOO0d1Us"
LIBRARY_VOICE_CATEGORIES = frozenset({"professional"})


def fetch_voices(api_key: str, timeout: float = 8.0) -> list[dict]:
    if not api_key.strip():
        return []
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key.strip()},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("voices", [])


def voice_api_available(category: str | None) -> bool:
    return (category or "").strip().lower() not in LIBRARY_VOICE_CATEGORIES


def resolve_voice_id(api_key: str, voice_id: str) -> str:
    voice_id = voice_id.strip()
    if not voice_id:
        return PREMADE_FALLBACK_VOICE_ID
    if not api_key.strip():
        return voice_id
    try:
        for voice in fetch_voices(api_key):
            if voice.get("voice_id") != voice_id:
                continue
            category = voice.get("category") or ""
            if voice_api_available(category):
                return voice_id
            logger.warning(
                "ELEVENLABS_VOICE_ID=%s (%s) is a library voice and cannot be used via the "
                "ElevenLabs API on a free plan — falling back to premade voice %s. Upgrade "
                "your ElevenLabs plan or pick a premade voice in Settings → Audio & voice.",
                voice_id,
                voice.get("name", "?"),
                PREMADE_FALLBACK_VOICE_ID,
            )
            return PREMADE_FALLBACK_VOICE_ID
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("ElevenLabs voice validation failed (%s) — keeping %s", exc, voice_id)
    return voice_id
