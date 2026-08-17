# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import json
import urllib.error
import urllib.request
from functools import lru_cache

from loguru import logger

from jarvis.kernel.error_collector import collector  # jrv: autofix

PREMADE_FALLBACK_VOICE_ID = "hpp4J3VqNfWAUOO0d1Us"
LIBRARY_VOICE_CATEGORIES = frozenset({"professional"})

# `resolve_voice_id` est appelé depuis `entrypoint()` (async) via _build_voice_tts,
# et urlopen est bloquant : l'attente gèle la boucle LiveKit au démarrage. 3 s
# suffisent pour un GET /v1/voices, et le résultat est mémoïsé — la validation ne
# coûte qu'une fois par processus, pas à chaque construction du TTS.
_VOICES_TIMEOUT_S = 3.0


def fetch_voices(api_key: str, timeout: float = _VOICES_TIMEOUT_S) -> list[dict]:
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


@lru_cache(maxsize=8)
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
                "ELEVENLABS_VOICE_ID={} ({}) est une voix bibliothèque, inutilisable via "
                "l'API ElevenLabs sur un plan gratuit — repli sur la voix premade {}. "
                "Passe à un plan payant ou choisis une voix premade dans "
                "Réglages → Audio & voix.",
                voice_id,
                voice.get("name", "?"),
                PREMADE_FALLBACK_VOICE_ID,
            )
            return PREMADE_FALLBACK_VOICE_ID
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        collector.warning("JRV-AUD-001", "JRV-AUD-001", cause=exc)
        logger.warning("Validation de la voix ElevenLabs échouée ({}) — on garde {}", exc, voice_id)
    return voice_id
