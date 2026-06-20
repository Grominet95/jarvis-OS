from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_WHISPER = frozenset(
    {
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-large-v2",
        "distil-medium.en",
        "distil-small.en",
        "distil-large-v3",
        "large-v3-turbo",
        "turbo",
    }
)


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
    api_backend: Literal["anthropic", "mistral", "openai", "gemini"] = Field(
        default="anthropic",
        description="Backend API principal quand LLM_PROVIDER=api.",
    )

    # Anthropic
    anthropic_api_key: SecretStr = Field(default=SecretStr(""), description="Clé API Anthropic.")
    anthropic_model: str = Field(
        default="claude-sonnet-4-6",
        description="Modèle Anthropic à utiliser.",
    )
    voice_anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Modèle Anthropic pour la voix (plus rapide).",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="Modèle OpenAI à utiliser pour le LLM principal.",
    )

    # Mistral
    mistral_api_key: SecretStr = Field(default=SecretStr(""), description="Clé API Mistral.")
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
    host: str = Field(
        default="127.0.0.1",
        description=(
            "Adresse d'écoute du serveur. '127.0.0.1' (défaut) = localhost uniquement. "
            "Mettre explicitement '0.0.0.0' pour exposer l'API hors de la machine "
            "(Tailscale, VPN, VPS). Ne jamais exposer sans API_AUTH_ENABLED=true."
        ),
    )
    port: int = Field(default=8000)
    environment: Literal["development", "production"] = Field(default="development")

    # ── Sécurité réseau ───────────────────────────────────────
    api_auth_enabled: bool = Field(
        default=False,
        description=(
            "Active l'authentification Bearer sur toutes les routes API. "
            "Désactivé par défaut pour ne pas casser l'usage local. "
            "Obligatoire dès que l'API est exposée hors localhost (Tailscale, VPS)."
        ),
    )
    api_token: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Token Bearer attendu si api_auth_enabled=True. Générer avec : openssl rand -hex 32"
        ),
    )
    cors_allow_origins: list[str] = Field(
        default_factory=list,
        description=(
            'Origines CORS autorisées (ex: ["http://mon-pc.tailscale:8000"]). '
            "Vide + auth désactivée = localhost par défaut. "
            "Ne jamais laisser vide avec auth activée et exposition réseau."
        ),
    )

    # ── Mémoire ───────────────────────────────────────────────
    memory_dir: str = Field(
        default="memory_data",
        description="Répertoire racine des données mémoire (MEMORY.md, topics/, sessions/).",
    )
    autonomy_auto_execute_enabled: bool = Field(
        default=False,
        description=(
            "PHASE 6 — Active l'auto-exécution des initiatives de niveau "
            "d'autonomie ≥ 3 (SANDBOX, MODIFY_PROJECT) quand le gate composite "
            "(§9) renvoie 'auto'. DÉSACTIVÉ par défaut : toute initiative "
            "qui demanderait une auto-exécution passe par validation humaine "
            "en MVP, peu importe son niveau. À NE FLIPPER QU'APRÈS observation "
            "validée (sous-mouvement séparé). Niveau 5 EXTERNAL_ACTION "
            "(publier/payer/contacter) reste systématiquement en validation "
            "humaine — ce flag NE peut PAS contourner la règle CDC §10.1."
        ),
    )
    auto_install_whitelisted_enabled: bool = Field(
        default=False,
        description=(
            "PHASE 5 — Active l'auto-installation des skills candidates qui "
            "(1) sont issues du CapabilityEngine, (2) passent le sandbox vert, "
            "(3) matchent un domaine listé dans config/permissions.yaml. "
            "DÉSACTIVÉ par défaut : aucune route auto en MVP, toute candidate "
            "passe par promote() humain. À NE FLIPPER QU'APRÈS observation "
            "validée (sous-mouvement séparé, équivalent du flag "
            "ingest_deep_enabled de PHASE 3 MOUVEMENT 2). "
            "Même quand True : INSTALL_PACKAGE et MODIFY_CORE restent "
            "systématiquement en validation humaine, le gate composite §9 ne "
            "peut pas être contourné."
        ),
    )
    ingest_deep_enabled: bool = Field(
        default=False,
        description=(
            "Active l'ingestion BATCH des sessions dans le Memory Kernel lors de "
            "la passe nocturne AutoDream.deep_analyze() (1× par 24h à 3h du mat). "
            "Une seule extraction par session JSONL — pas une boucle par message — "
            "donc le dédoublonnage intra-batch est garanti par le matcher v2. "
            "Les hooks micro (consolidation._run + auto_dream._run_micro à chaque "
            "échange) NE sont JAMAIS branchés au Kernel : c'est une décision "
            "Generative Agents (synthèse périodique sur la conversation complète, "
            "pas extraction à chaud message par message). "
            "Désactivé par défaut tant que la trace 3-5 jours n'a pas été validée."
        ),
    )

    # ── Outils ────────────────────────────────────────────────
    cli_whitelist_path: str = Field(
        default="config/tools.yaml",
        description="Chemin vers le fichier YAML de scripts CLI whitelistés.",
    )
    allow_unsandboxed_exec: bool = Field(
        default=False,
        description=(
            "Autorise ExecuteCLITool à s'exécuter sans sandbox (tmpdir isolé + env restreint). "
            "Désactivé par défaut. N'activer qu'en dev local en connaissance de cause."
        ),
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
    google_gmail_token_path: str = Field(
        default="config/google_gmail_token.json",
        description="Chemin vers le token OAuth2 Gmail (généré automatiquement).",
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
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Clé API OpenAI (LLM principal si api_backend=openai, TTS, Vision).",
    )
    stt_provider: Literal["deepgram", "whisper"] = Field(
        default="deepgram",
        description="Backend STT : 'deepgram' (cloud, rapide) ou 'whisper' (local, hors-ligne).",
    )
    deepgram_api_key: SecretStr = Field(
        default=SecretStr(""), description="Clé API Deepgram (STT Nova-2 streaming)."
    )
    whisper_model: str = Field(
        default="tiny",
        description="Taille du modèle faster-whisper : tiny, base, small, medium, large.",
    )

    @field_validator("whisper_model", mode="before")
    @classmethod
    def _validate_whisper_model(cls, v: str) -> str:
        if v not in _VALID_WHISPER:
            return "tiny"
        return v

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
    elevenlabs_api_key: SecretStr = Field(default=SecretStr(""), description="Clé API ElevenLabs.")
    elevenlabs_voice_id: str = Field(default="", description="ID de la voix ElevenLabs.")
    elevenlabs_model: str = Field(
        default="eleven_flash_v2_5",
        description="Modèle ElevenLabs : eleven_flash_v2_5 (~75ms) ou eleven_turbo_v2_5 (~300ms).",
    )

    # ── Notion ────────────────────────────────────────────────
    notion_token: SecretStr = Field(
        default=SecretStr(""), description="Token d'intégration Notion."
    )
    notion_page_id: str = Field(
        default="",
        description="ID de la page Notion des tâches (depuis l'URL).",
    )

    # ── AIS Stream (navires) ─────────────────────────────────
    aisstream_key: SecretStr = Field(
        default=SecretStr(""),
        description="Clé API AISstream.io (navires temps réel).",
    )

    # ── Mapbox (globe natif) ──────────────────────────────────
    mapbox_token: SecretStr = Field(
        default=SecretStr(""), description="Token Mapbox GL JS (projection globe native)."
    )

    # ── MapTiler (carte détaillée) ────────────────────────────
    maptiler_key: SecretStr = Field(
        default=SecretStr(""), description="Clé API MapTiler (free tier, carte détaillée globe V2)."
    )

    # ── Musique ───────────────────────────────────────────────
    music_provider: str = Field(
        default="", description="Fournisseur de musique actif: spotify | deezer | local"
    )

    # ── Spotify ───────────────────────────────────────────────
    spotify_client_id: str = Field(default="", description="Spotify app Client ID.")
    spotify_client_secret: SecretStr = Field(
        default=SecretStr(""), description="Spotify app Client Secret."
    )
    spotify_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/spotify/callback",
        description="URI de callback OAuth Spotify.",
    )
    spotify_token_path: str = Field(
        default="config/spotify_token.json",
        description="Fichier de token Spotify (généré automatiquement).",
    )

    # ── Deezer ────────────────────────────────────────────────
    deezer_app_id: str = Field(default="", description="Deezer app ID.")
    deezer_app_secret: SecretStr = Field(default=SecretStr(""), description="Deezer app secret.")
    deezer_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/deezer/callback",
        description="URI de callback OAuth Deezer.",
    )
    deezer_token_path: str = Field(
        default="config/deezer_token.json",
        description="Fichier de token Deezer (généré automatiquement).",
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

    # ── Budget & coût ─────────────────────────────────────────
    budget_enabled: bool = Field(
        default=False,
        description="Active le contrôle de budget (hard-stop + alertes). Désactivé par défaut.",
    )
    budget_monthly_usd: float = Field(
        default=10.0,
        description="Plafond mensuel global en USD (toutes dépenses LLM/API confondues).",
    )
    budget_per_project_usd: float = Field(
        default=2.0,
        description="Plafond par run de projet agent en USD.",
    )
    budget_warn_pct: float = Field(
        default=80.0,
        description="Seuil d'alerte budget (% du plafond). Déclenche une notification.",
    )
    max_concurrent_workers: int = Field(
        default=3,
        description="Nombre maximal de workers agentiques simultanés.",
    )

    # ── Fusion 360 MCP ────────────────────────────────────────
    fusion_enabled: bool = Field(
        default=False,
        description="Active l'intégration Fusion 360 (MCP HTTP).",
    )
    fusion_mcp_url: str = Field(
        default="http://127.0.0.1:27182/mcp",
        description="URL complète du serveur MCP Fusion 360.",
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

    # ── Utilisateur ──────────────────────────────────────────
    user_firstname: str = Field(
        default="",
        description="Prénom de l'utilisateur (USER_FIRSTNAME dans .env).",
    )
    user_profile: str = Field(
        default="",
        description=(
            "Bio courte de l'utilisateur (USER_PROFILE dans .env), injectée dans le "
            "moteur proactif. Ex. 'entrepreneur tech, YouTuber hardware, Lyon'. Vide = omis."
        ),
    )

    @property
    def display_name(self) -> str:
        """Prénom à utiliser dans les prompts. Repli sur 'Barth' si non configuré."""
        return (self.user_firstname or "").strip() or "Barth"

    # ── Wake Up sequence ─────────────────────────────────────
    wakeup_enabled: bool = Field(
        default=False,
        description="Active la séquence wake up (veille + clap + scan facial). Désactiver en dev.",
    )

    # ── Mode Québécois ────────────────────────────────────────
    quebec_mode: bool = Field(
        default=False,
        description=(
            "Active le mode Québécois : voix québécoise + dialecte québécois dans le prompt."
        ),
    )
    quebec_voice_id: str = Field(
        default="RBhYSNMNu6b2CGZ9Fn1M",
        description="ID de la voix ElevenLabs québécoise.",
    )

    # ── Logging ───────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")


# Singleton — importé partout via `from config.settings import settings`
settings = Settings()
