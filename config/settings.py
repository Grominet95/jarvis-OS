from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration centrale de Jarvis, chargée depuis .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────
    llm_provider: Literal["api", "local"] = Field(
        default="api",
        description="'api' pour Anthropic/Mistral, 'local' pour Ollama.",
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Clé API Anthropic.")
    anthropic_model: str = Field(
        default="claude-sonnet-4-6",
        description="Modèle Anthropic à utiliser.",
    )
    voice_anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Modèle Anthropic pour la voix (plus rapide).",
    )

    # Mistral
    mistral_api_key: str = Field(default="", description="Clé API Mistral.")
    mistral_model: str = Field(
        default="mistral-large-latest",
        description="Modèle Mistral à utiliser.",
    )

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="URL du serveur Ollama.",
    )
    ollama_model: str = Field(default="mistral", description="Modèle Ollama à utiliser.")

    # ── Serveur ───────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    environment: Literal["development", "production"] = Field(default="development")

    # ── Mémoire ───────────────────────────────────────────────
    memory_dir: str = Field(
        default="memory_data",
        description="Répertoire racine des données mémoire (MEMORY.md, topics/, sessions/).",
    )

    # ── Outils ────────────────────────────────────────────────
    cli_whitelist_path: str = Field(
        default="config/tools.yaml",
        description="Chemin vers le fichier YAML de scripts CLI whitelistés.",
    )
    skills_dir: str = Field(
        default="skills",
        description="Répertoire racine des skills OpenClaw/ClawHub.",
    )
    file_search_roots: list[str] = Field(
        default=["~/"],
        description="Répertoires racines autorisés pour la lecture/recherche de fichiers.",
    )
    google_credentials_path: str = Field(
        default="config/google_credentials.json",
        description="Chemin vers le fichier credentials OAuth2 Google.",
    )
    google_token_path: str = Field(
        default="config/google_token.json",
        description="Chemin vers le token OAuth2 Google (généré automatiquement).",
    )

    # ── Vision ───────────────────────────────────────────────────
    vision_model: str = Field(
        default="gpt-4o",
        description="Modèle OpenAI pour la vision (GPT-4o Vision).",
    )
    vision_webcam_index: int = Field(
        default=0,
        description="Index de la webcam OpenCV (0 = première caméra détectée).",
    )
    vision_screen_max_width: int = Field(
        default=1280,
        description="Largeur max de la capture écran avant envoi à l'API.",
    )
    vision_jpeg_quality: int = Field(
        default=75,
        description="Qualité JPEG des captures (50-85 est suffisant pour l'analyse).",
    )
    vision_object_detection: bool = Field(
        default=False,
        description="Active le daemon de détection d'objets YOLOv8n (webcam en background).",
    )
    vision_yolo_confidence: float = Field(
        default=0.5,
        description="Seuil de confiance YOLOv8n (0.0–1.0).",
    )

    # ── Audio / STT / TTS ─────────────────────────────────────
    openai_api_key: str = Field(default="", description="Clé API OpenAI (TTS + Vision).")
    whisper_model: str = Field(
        default="tiny",
        description="Taille du modèle faster-whisper : tiny, base, small, medium, large.",
    )
    tts_voice: str = Field(
        default="alloy",
        description="Voix OpenAI TTS : alloy, echo, fable, onyx, nova, shimmer.",
    )
    tts_provider: str = Field(
        default="piper",
        description="Moteur TTS : 'piper' (local) ou 'elevenlabs'.",
    )
    piper_model_path: str = Field(
        default="models/piper/fr_FR-upmc-medium.onnx",
        description="Chemin vers le modèle Piper ONNX.",
    )
    elevenlabs_api_key: str = Field(default="", description="Clé API ElevenLabs.")
    elevenlabs_voice_id: str = Field(default="", description="ID de la voix ElevenLabs.")
    elevenlabs_model: str = Field(
        default="eleven_flash_v2_5",
        description="Modèle ElevenLabs : eleven_flash_v2_5 (~75ms) ou eleven_turbo_v2_5 (~300ms).",
    )

    # ── Notion ────────────────────────────────────────────────
    notion_token: str = Field(default="", description="Token d'intégration Notion.")
    notion_page_id: str = Field(
        default="",
        description="ID de la page Notion des tâches (depuis l'URL).",
    )

    # ── AIS Stream (navires) ─────────────────────────────────
    aisstream_key: str = Field(default="", description="Clé API AISstream.io (navires temps réel).")

    # ── Spotify ───────────────────────────────────────────────
    spotify_client_id: str = Field(default="", description="Spotify app Client ID.")
    spotify_client_secret: str = Field(default="", description="Spotify app Client Secret.")
    spotify_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/spotify/callback",
        description="URI de callback OAuth Spotify.",
    )
    spotify_token_path: str = Field(
        default="config/spotify_token.json",
        description="Fichier de token Spotify (généré automatiquement).",
    )

    # ── Proactivité ───────────────────────────────────────────
    home_city: str = Field(default="Paris", description="Ville pour la météo du briefing.")
    briefing_hour: int = Field(default=9, description="Heure du morning briefing (0-23).")
    calendar_reminder_minutes: int = Field(
        default=10,
        description="Délai de rappel avant un event calendar (minutes).",
    )
    proactive_lat: float = Field(default=45.75, description="Latitude pour la météo proactive.")
    proactive_lon: float = Field(default=4.85, description="Longitude pour la météo proactive.")
    proactive_city: str = Field(default="Lyon", description="Nom de ville pour la météo proactive.")

    # ── Docker V2 ────────────────────────────────────────────
    docker_enabled: bool = Field(
        default=False,
        description="Active l'exécution des projets dans des containers Docker isolés.",
    )
    docker_base_image: str = Field(
        default="python:3.11-slim",
        description="Image Docker de base pour les containers worker.",
    )
    docker_memory_limit: str = Field(
        default="512m",
        description="Limite mémoire des containers Docker (ex: 512m, 1g).",
    )
    docker_cpu_limit: float = Field(
        default=1.0,
        description="Limite CPU des containers Docker (1.0 = 1 cœur).",
    )
    docker_network: str = Field(
        default="none",
        description="Mode réseau Docker : 'none' (isolé) ou 'bridge' (internet limité).",
    )
    docker_timeout_seconds: int = Field(
        default=300,
        description="Timeout max par step Docker en secondes.",
    )

    # ── Imprimante 3D (BambuLab) ──────────────────────────────
    printer_ip: str = Field(
        default="",
        description="IP locale de la BambuLab.",
    )
    printer_serial: str = Field(
        default="",
        description="Numéro de série BambuLab (ex: 01P00A123456789).",
    )
    printer_access_code: str = Field(
        default="",
        description="Code d'accès BambuLab — 8 chiffres dans Bambu Studio → Settings → Printer.",
    )

    # ── Fusion 360 MCP ────────────────────────────────────────
    fusion_mcp_port: int = Field(
        default=27182,
        description="Port du serveur MCP Fusion 360 (visible dans Fusion → Préférences → Add-Ins).",
    )

    # ── Face Recognition ──────────────────────────────────────
    face_recognition_enabled: bool = Field(
        default=False,
        description="Active la reconnaissance faciale dans le daemon vision.",
    )
    face_recognition_threshold: float = Field(
        default=0.45,
        description="Distance max pour une correspondance (plus bas = plus strict).",
    )

    # ── Clap Detection ────────────────────────────────────────
    clap_detection_enabled: bool = Field(
        default=False,
        description="Active la détection de double clap pour le wake up.",
    )
    clap_amplitude_threshold: float = Field(
        default=0.35,
        description="Seuil d'amplitude pour détecter un clap (0.0-1.0).",
    )

    # ── Logging ───────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="DEBUG")


# Singleton — importé partout via `from config.settings import settings`
settings = Settings()
