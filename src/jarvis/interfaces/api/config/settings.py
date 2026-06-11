"""Settings API + hot-swap LLM provider — Phase E §E.1.3.

Routes :
  - GET  /api/settings/env-status — booléens par clé (jamais les valeurs).
  - GET  /api/settings — état complet groupé par domaine, API keys maskées.
  - POST /api/settings/update — modifie .env, mute in-memory, hot-swap LLM
    si la clé impacte le provider.
  - GET  /api/settings/voices — liste ElevenLabs.
  - POST /api/settings/test-key — sonde une clé API (Anthropic, …).
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import dotenv_values
from fastapi import APIRouter, Query, Request
from loguru import logger
from pydantic import BaseModel

from jarvis.interfaces.api.config._env import (
    _LLM_HOT_SWAP_KEYS,
    _RESTART_KEYS,
    _SENSITIVE_KEYS,
    _SETTINGS_FIELD_MAP,
    _mask,
    _read_env,
    _write_env,
)
from jarvis.kernel.approvals import approval_config as _approval_cfg
from jarvis.kernel.settings import settings as _s
from jarvis.providers.llm.factory import create_background_llm, get_llm_provider

router = APIRouter()


@router.get("/api/settings/env-status")
async def get_env_status(keys: str = Query("")) -> dict:
    """Retourne True/False par clé env — jamais les valeurs."""
    env_values = dotenv_values(".env")
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    return {k: bool(env_values.get(k, "").strip()) for k in key_list}


@router.get("/api/settings")
async def get_settings_endpoint() -> dict:
    import dataclasses as _dc

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
async def update_setting(request: Request, body: SettingUpdateBody) -> dict:
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

    # Hot-swap LLM provider sans redémarrage (LLM_PROVIDER, API_BACKEND, OLLAMA_MODEL…)
    if env_key in _LLM_HOT_SWAP_KEYS:
        try:
            new_llm = get_llm_provider()
            new_bg_llm = create_background_llm()
            gw = getattr(request.app.state, "gateway", None)
            if gw is not None:
                # Chat principal + voice gateway — agents primaires
                object.__setattr__(gw._agent, "_llm", new_llm)
                vgw = getattr(request.app.state, "voice_gateway", None)
                if vgw is not None:
                    object.__setattr__(vgw._agent, "_llm", new_llm)

                # CrossSessionRecall (partagé entre gateway et voice_gateway)
                recall = getattr(gw, "_recall", None)
                if recall is not None and hasattr(recall, "_llm"):
                    object.__setattr__(recall, "_llm", new_bg_llm)

                # LLMs background (consolidation, auto_dream, user_model)
                for attr in ("consolidation", "auto_dream", "user_model"):
                    obj = getattr(request.app.state, attr, None)
                    if obj is not None and hasattr(obj, "_llm"):
                        object.__setattr__(obj, "_llm", new_bg_llm)

                # BackgroundWorker
                worker = getattr(request.app.state, "worker", None)
                if worker is not None and hasattr(worker, "_llm"):
                    object.__setattr__(worker, "_llm", new_llm)

                # InitiativeGenerator (dans ProactiveEngine)
                pe = getattr(request.app.state, "proactive_engine", None)
                if pe is not None:
                    gen = getattr(pe, "_generator", None)
                    if gen is not None and hasattr(gen, "_llm"):
                        object.__setattr__(gen, "_llm", new_llm)

                # SkillSynthesizer
                synth = getattr(request.app.state, "skill_synthesizer", None)
                if synth is not None and hasattr(synth, "_llm"):
                    object.__setattr__(synth, "_llm", new_llm)

                logger.info(
                    "LLM provider hot-swapped"
                    " (main + voice + recall + background + worker + proactive + skills)",
                    provider=_s.llm_provider,
                    model=getattr(new_llm, "_model", "?"),
                )
                needs_restart = False
            else:
                logger.warning("LLM hot-swap skipped — gateway not in app.state")
                needs_restart = True
        except Exception as exc:
            logger.warning("LLM hot-swap failed — redémarrage requis", error=str(exc))
            needs_restart = True

    return {"ok": True, "key": body.key, "needs_restart": needs_restart}


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
