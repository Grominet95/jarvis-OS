from __future__ import annotations

import socket
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from jarvis.interfaces.api.config._env import write_env_batch
from jarvis.kernel.bundle import prerequisites_status, stage_models_from_bundle
from jarvis.kernel.paths import FACES_DIR, PROJECT_ROOT
from jarvis.kernel.setup_layout import ensure_runtime_layout, is_setup_complete, read_env_file

router = APIRouter()


class SetupCompletePayload(BaseModel):
    user_firstname: str
    # « local » = Ollama (LLM_PROVIDER=local) ; les autres = backends API.
    api_backend: Literal["anthropic", "openai", "mistral", "gemini", "local"] = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_model: str = "mistral"
    ollama_base_url: str = "http://localhost:11434"
    proactive_city: str = "Paris"
    proactive_lat: str = "48.85"
    proactive_lon: str = "2.35"
    tts_provider: Literal["piper", "elevenlabs"] = "piper"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    voice_enabled: bool = False
    livekit_cloud: bool = False
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    deepgram_api_key: str = ""
    aisstream_key: str = ""
    face_recognition_enabled: bool = False
    port: int | None = None


def _find_available_port(start: int = 8000, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


@router.get("/api/setup/status")
async def setup_status() -> dict:
    env_path = PROJECT_ROOT / ".env"
    env = read_env_file(env_path)

    def _has(key: str) -> bool:
        return bool(env.get(key, "").strip())

    livekit_url = env.get("LIVEKIT_URL", "")
    # Backend effectif : « local » si Ollama, sinon le backend API configuré.
    is_local = env.get("LLM_PROVIDER", "api") == "local"
    effective_backend = "local" if is_local else env.get("API_BACKEND", "anthropic")
    return {
        "complete": is_setup_complete(env_path),
        "env_exists": env_path.is_file(),
        "user_firstname": env.get("USER_FIRSTNAME", ""),
        "api_backend": effective_backend,
        "port": int(env.get("PORT", "8000") or "8000"),
        "prerequisites": prerequisites_status(),
        "layout_created": ensure_runtime_layout(),
        # Valeurs non-secrètes — préremplissage lors d'une reconfiguration.
        "config": {
            "proactive_city": env.get("PROACTIVE_CITY", "Paris"),
            "proactive_lat": env.get("PROACTIVE_LAT", "48.85"),
            "proactive_lon": env.get("PROACTIVE_LON", "2.35"),
            "ollama_model": env.get("OLLAMA_MODEL", "mistral"),
            "ollama_base_url": env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            "elevenlabs_enabled": env.get("TTS_PROVIDER", "") == "elevenlabs",
            "elevenlabs_voice_id": env.get("ELEVENLABS_VOICE_ID", ""),
            "voice_enabled": _has("DEEPGRAM_API_KEY"),
            "livekit_cloud": livekit_url.startswith("wss://"),
            "livekit_url": livekit_url if livekit_url.startswith("wss://") else "",
            "face_recognition_enabled": env.get("FACE_RECOGNITION_ENABLED", "false") == "true",
        },
        # Présence des secrets (jamais leur valeur) — pour afficher "déjà configuré".
        "secrets_set": {
            "anthropic_api_key": _has("ANTHROPIC_API_KEY"),
            "openai_api_key": _has("OPENAI_API_KEY"),
            "mistral_api_key": _has("MISTRAL_API_KEY"),
            "gemini_api_key": _has("GEMINI_API_KEY"),
            "elevenlabs_api_key": _has("ELEVENLABS_API_KEY"),
            "deepgram_api_key": _has("DEEPGRAM_API_KEY"),
            "livekit_api_key": _has("LIVEKIT_API_KEY"),
            "livekit_api_secret": _has("LIVEKIT_API_SECRET"),
        },
    }


@router.get("/api/setup/prerequisites")
async def setup_prerequisites() -> dict:
    return prerequisites_status()


@router.post("/api/setup/bootstrap")
async def setup_bootstrap() -> dict:
    created = ensure_runtime_layout()
    staged = stage_models_from_bundle()
    return {"layout_created": created, "models_staged": staged}


@router.post("/api/setup/complete")
async def setup_complete(body: SetupCompletePayload) -> dict:
    # Reconfiguration : un secret laissé vide conserve la valeur déjà en place
    # (le wizard ne réaffiche jamais les clés, donc un champ vide = « ne pas toucher »).
    existing = read_env_file(PROJECT_ROOT / ".env")

    def _secret(value: str, key: str) -> str:
        return value.strip() or existing.get(key, "").strip()

    anthropic_api_key = _secret(body.anthropic_api_key, "ANTHROPIC_API_KEY")
    openai_api_key = _secret(body.openai_api_key, "OPENAI_API_KEY")
    mistral_api_key = _secret(body.mistral_api_key, "MISTRAL_API_KEY")
    gemini_api_key = _secret(body.gemini_api_key, "GEMINI_API_KEY")

    # Le LLM est FACULTATIF à l'onboarding : on peut terminer sans clé et la
    # renseigner plus tard dans les réglages. Seul le prénom reste requis.
    is_local = body.api_backend == "local"
    if not body.user_firstname.strip():
        raise HTTPException(400, "Prenom requis.")

    llm_provider = "local" if is_local else "api"
    # API_BACKEND reste une valeur API valide même en local (ignorée par le factory).
    api_backend = "anthropic" if is_local else body.api_backend

    ensure_runtime_layout()
    staged = stage_models_from_bundle()

    port = body.port or _find_available_port()
    livekit_url = ""
    livekit_api_key = ""
    livekit_api_secret = ""
    deepgram_api_key = ""

    if body.voice_enabled:
        deepgram_api_key = _secret(body.deepgram_api_key, "DEEPGRAM_API_KEY")
        if not deepgram_api_key:
            raise HTTPException(400, "Cle Deepgram requise pour le pipeline vocal.")
        if body.livekit_cloud:
            livekit_url = body.livekit_url.strip() or existing.get("LIVEKIT_URL", "")
            livekit_api_key = _secret(body.livekit_api_key, "LIVEKIT_API_KEY")
            livekit_api_secret = _secret(body.livekit_api_secret, "LIVEKIT_API_SECRET")
            if not livekit_url or not livekit_api_key or not livekit_api_secret:
                raise HTTPException(400, "URL et cles LiveKit Cloud requises.")
        else:
            livekit_url = "ws://localhost:7880"
            livekit_api_key = "devkey"
            livekit_api_secret = "devsecretdevsecretdevsecretdevsecret"

    updates = {
        "USER_FIRSTNAME": body.user_firstname.strip(),
        "LLM_PROVIDER": llm_provider,
        "API_BACKEND": api_backend,
        "ANTHROPIC_API_KEY": anthropic_api_key,
        "ANTHROPIC_MODEL": body.anthropic_model,
        "VOICE_ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
        "OPENAI_API_KEY": openai_api_key,
        "OPENAI_MODEL": body.openai_model,
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "ENVIRONMENT": "development",
        "LOG_LEVEL": "INFO",
        "PROACTIVE_LAT": body.proactive_lat.strip(),
        "PROACTIVE_LON": body.proactive_lon.strip(),
        "PROACTIVE_CITY": body.proactive_city.strip(),
        "TTS_PROVIDER": body.tts_provider,
        "ELEVENLABS_API_KEY": _secret(body.elevenlabs_api_key, "ELEVENLABS_API_KEY"),
        "ELEVENLABS_VOICE_ID": body.elevenlabs_voice_id.strip(),
        "ELEVENLABS_MODEL": body.elevenlabs_model,
        "WHISPER_MODEL": "tiny",
        "LIVEKIT_URL": livekit_url,
        "LIVEKIT_API_KEY": livekit_api_key,
        "LIVEKIT_API_SECRET": livekit_api_secret,
        "DEEPGRAM_API_KEY": deepgram_api_key,
        "AISSTREAM_KEY": _secret(body.aisstream_key, "AISSTREAM_KEY"),
        "FACE_RECOGNITION_ENABLED": "true" if body.face_recognition_enabled else "false",
        "SETUP_COMPLETE": "true",
        "MISTRAL_API_KEY": mistral_api_key,
        "MISTRAL_MODEL": body.mistral_model,
        "GEMINI_API_KEY": gemini_api_key,
        "GEMINI_MODEL": body.gemini_model,
        "OLLAMA_BASE_URL": body.ollama_base_url.strip() or "http://localhost:11434",
        "OLLAMA_MODEL": body.ollama_model.strip() or "mistral",
        "GOOGLE_API_KEY": existing.get("GOOGLE_API_KEY", ""),
    }

    write_env_batch(updates)
    return {
        "ok": True,
        "port": port,
        "models_staged": staged,
        "next": f"http://127.0.0.1:{port}/",
    }


@router.post("/api/setup/upload-face")
async def setup_upload_face(file: UploadFile = File(...)) -> dict:  # noqa: B008
    if not file.filename or not file.filename.lower().endswith((".jpg", ".jpeg")):
        raise HTTPException(400, "Fichier JPG requis.")
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    target = FACES_DIR / "reference.jpg"
    content = await file.read()
    if len(content) < 1024:
        raise HTTPException(400, "Image trop petite.")
    target.write_bytes(content)
    return {"saved": str(target.relative_to(PROJECT_ROOT)).replace("\\", "/")}
