# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
Jarvis Voice Agent — LiveKit Agents pipeline vocal.
Process indépendant de main.py FastAPI.
Lance avec : uv run python voice_agent.py dev
Test console (sans browser) : uv run python voice_agent.py console
"""

from __future__ import annotations

import logging
import os
import sys
import warnings

from dotenv import dotenv_values, load_dotenv
from livekit import rtc as lk_rtc
from livekit.agents import (
    Agent,
    AgentSession,
    WorkerOptions,
    cli,
    tts,
)
from livekit.agents import (
    llm as lk_llm,
)
from livekit.agents.voice.room_io import AudioInputOptions, RoomOptions
from livekit.plugins import deepgram, elevenlabs, silero
from livekit.plugins import google as lk_google
from livekit.plugins.google.beta import gemini_tts

from jarvis.bootstrap import build
from jarvis.capabilities.skills.registry import SkillRegistry
from jarvis.kernel.paths import PROJECT_ROOT  # noqa: E402
from jarvis.kernel.settings import settings

load_dotenv(PROJECT_ROOT / ".env")

# Réduit le bruit du terminal : warnings Python + format loguru aligné sur main.py.
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")
try:
    from loguru import logger as _loguru

    _loguru.remove()
    _loguru.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level>"
            " | <cyan>{name}</cyan> — {message}"
        ),
        colorize=True,
    )
except Exception:
    pass


logger = logging.getLogger("jarvis-voice")

# ─── Prompt système vocal (base) ───────────────────────────────────────────────

def _voice_system_base(name: str, profile: str = "") -> str:
    """Prompt vocal de base, personnalisé au prénom + bio (omise si vide)."""
    bio_line = f"- Tu connais {name} : {profile.strip()}.\n" if profile.strip() else ""
    return (
        f"\nTu es Jarvis, l'assistant IA personnel de {name}.\n\n"
        "Règles absolues pour la voix :\n"
        "- Réponses COURTES. Maximum 2-3 phrases sauf si l'utilisateur demande explicitement plus.\n"
        "- Pas de listes à puces, pas de markdown, pas d'astérisques.\n"
        "- Pas d'émojis.\n"
        "- Parle naturellement, comme dans une conversation.\n"
        '- Tu peux dire "mhm", "hmm", "ok", "allez" pour paraître naturel.\n'
        "- Si tu dois faire quelque chose d'écran (code, liste longue), dis-le brièvement\n"
        "  et propose de l'envoyer par écrit dans l'interface.\n"
        f"{bio_line}"
        '- Quand tu utilises un outil, annonce-le en 1 phrase courte avant (ex: "Je vérifie l\'imprimante…").\n\n'
        f"Réponds en français sauf si {name} parle en anglais.\n"
    )


# ─── Chargement des skills ─────────────────────────────────────────────────────


def _build_voice_instructions() -> str:
    """Prompt système = base + SYSTEM_PROMPT de chaque skill actif."""
    base = _voice_system_base(settings.display_name, settings.user_profile)
    try:
        reg = SkillRegistry.get_instance()
        skill_prompt = reg.get_combined_system_prompt()
        if skill_prompt:
            return base + "\n\n# SKILLS ACTIFS\n\n" + skill_prompt
    except Exception as e:
        logger.warning("Skills non chargés pour les instructions vocales: %s", e)
    return base


def _make_livekit_tool(jarvis_tool: object) -> lk_llm.RawFunctionTool:
    """Wraps un Jarvis Tool comme LiveKit RawFunctionTool."""
    schema = jarvis_tool.to_claude_schema()  # type: ignore[attr-defined]
    raw_schema = {
        "name": schema["name"],
        "description": schema["description"],
        "parameters": schema["input_schema"],
    }

    async def _execute(raw_arguments: dict[str, object]) -> str:
        result = await jarvis_tool.execute(**raw_arguments)  # type: ignore[attr-defined]
        return f"[ERREUR] {result.content}" if result.is_error else result.content

    return lk_llm.function_tool(_execute, raw_schema=raw_schema)


def _voice_broadcast(event: dict) -> None:
    """Envoie un événement UI via HTTP au serveur FastAPI (localhost)."""
    import json as _json
    import threading
    import urllib.request

    def _post() -> None:

        url = f"http://localhost:{settings.port}/internal/broadcast"
        data = _json.dumps(event).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            logger.debug("Voice broadcast HTTP fail: %s", e)

    threading.Thread(target=_post, daemon=True).start()


def _build_voice_tools() -> list:
    """Retourne les LiveKit tools en miroir du mode texte (jarvis.app).

    Phase C — Étape 1B : re-câblé sur bootstrap.build() partagé. Le process
    voix appelle son PROPRE `bootstrap.build()` (second composition root —
    process séparé du process API, ils partagent l'état via le SQLite WAL
    de MemoryKernel). Les 13 `__import__("jarvis.capabilities.tools.X")`
    lambdas qui re-instanciaient chaque outil disparaissent au profit de
    `container.tool_registry` — UNE source de vérité pour les outils
    enregistrés.

    Conséquence : la voix a désormais accès à TOUS les outils enregistrés
    dans le ToolRegistry du Container, et plus seulement le sous-ensemble
    historique de 13. Le sous-ensemble pertinent pour la voix vs les
    outils écrits-only (memory_search, etc.) sera filtré au cas par cas
    dans un commit ultérieur si nécessaire — à ce stade, on accepte
    l'élargissement (toutes les fonctions LiveKit sont déclarées, le LLM
    voix choisit lesquelles appeler selon le contexte).
    """

    # Container voix : SON PROPRE composition root (process séparé du process
    # API — ils partagent l'état via le SQLite WAL de MemoryKernel, cf.
    # PRAGMA WAL+busy_timeout posé en C.1.8).
    container = build()

    # tool_registry contient déjà les outils enregistrés via register() + les
    # outils des skills installés via replace_skill_tools(*skill_registry.
    # get_all_tools()) — voir bootstrap.build() section 5. Pas besoin
    # d'appel séparé à SkillRegistry ici.
    jarvis_tools = list(container.tool_registry._tools.values())

    tools = [_make_livekit_tool(t) for t in jarvis_tools]
    logger.info("Voice tools chargés: %s", [t._info.name for t in tools])
    return tools


# ─── Agent Jarvis ──────────────────────────────────────────────────────────────


class JarvisVoiceAgent(Agent):
    def __init__(self, instructions: str, tools: list) -> None:
        super().__init__(instructions=instructions, tools=tools)

    async def on_enter(self) -> None:
        _name = settings.display_name
        _greeting = (
            f"Systèmes en ligne. Bonjour {_name}." if settings.user_firstname.strip()
            else "Systèmes en ligne."
        )
        await self.session.say(
            _greeting,
            allow_interruptions=True,
        )


# ─── Prewarm — chargé une fois au démarrage du process ─────────────────────────


def prewarm(proc: object) -> None:
    """Pré-charge les skills, outils et le modèle VAD avant l'arrivée d'un job."""
    proc.userdata["instructions"] = _build_voice_instructions()  # type: ignore[attr-defined]
    proc.userdata["tools"] = _build_voice_tools()  # type: ignore[attr-defined]
    # Le modèle ONNX silero met ~300-800ms à charger ; le faire ici évite de payer
    # ce coût au premier clic micro.
    proc.userdata["vad"] = silero.VAD.load(  # type: ignore[attr-defined]
        min_speech_duration=0.05,
        min_silence_duration=0.2,
        activation_threshold=0.5,
    )
    logger.info("=" * 40)
    logger.info("✓ Jarvis vocal prêt — clique sur le micro")
    logger.info("=" * 40)


# ─── Routing LLM du pipeline LiveKit ───────────────────────────────────────────


def _build_voice_stt(env: dict) -> object:
    """STT du pipeline LiveKit, sélectionné via STT_PROVIDER (cloud).

    'deepgram' (défaut, meilleure latence) | 'openai' (Whisper) | 'google'
    (Cloud Speech, nécessite un service account GOOGLE_APPLICATION_CREDENTIALS).
    Repli sur Deepgram en cas d'erreur de construction (auth manquante, etc.).
    """
    provider = env.get("STT_PROVIDER", "deepgram").strip().lower()
    try:
        if provider == "openai":
            from livekit.plugins import openai as lk_openai

            stt = lk_openai.STT(
                model="gpt-4o-mini-transcribe",
                language="fr",
                api_key=env.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            )
            logger.info("STT pipeline = OpenAI (gpt-4o-mini-transcribe)")
            return stt
        if provider == "google":
            stt = lk_google.STT(languages="fr-FR", model="latest_long")
            logger.info("STT pipeline = Google Cloud Speech (latest_long)")
            return stt
    except Exception as e:
        logger.warning("STT '%s' indisponible (%s) -> repli Deepgram", provider, e)

    logger.info("STT pipeline = Deepgram (nova-2)")
    return deepgram.STT(
        model="nova-2", language="fr", smart_format=True, interim_results=True
    )


def _build_voice_elevenlabs(env: dict) -> object:
    """TTS ElevenLabs — repli fiable (quota large, faible latence avec flash)."""
    quebec = env.get("QUEBEC_MODE", "false").strip().lower() in ("true", "1", "yes")
    voice_id = env.get("QUEBEC_VOICE_ID") if quebec else env.get("ELEVENLABS_VOICE_ID", "")
    model = "eleven_multilingual_v2" if quebec else env.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
    return elevenlabs.TTS(
        model=model,
        voice_id=voice_id,
        api_key=env.get("ELEVENLABS_API_KEY", os.getenv("ELEVENLABS_API_KEY", "")),
        encoding="pcm_24000",
        chunk_length_schedule=[50, 90, 160, 250],
    )


def _build_voice_tts(env: dict) -> object:
    """TTS du pipeline LiveKit, sélectionné via TTS_PROVIDER.

    'gemini'     → voix Google naturelle, MAIS le free tier est très limité
                   (10 req/min) → enveloppé dans un FallbackAdapter vers
                   ElevenLabs : dès que Gemini renvoie 429 (quota), LiveKit
                   bascule sur ElevenLabs sans couper la conversation.
    'elevenlabs' → ElevenLabs seul (défaut).
    'piper'      → pas de plugin LiveKit temps réel → repli ElevenLabs.
    """
    provider = env.get("TTS_PROVIDER", "elevenlabs").strip().lower()
    has_eleven = bool(env.get("ELEVENLABS_API_KEY", os.getenv("ELEVENLABS_API_KEY", "")))

    if provider == "gemini":
        gemini = gemini_tts.TTS(
            model=env.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            voice_name=env.get("GEMINI_TTS_VOICE", "Kore"),
            api_key=env.get("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY", "")),
        )
        if has_eleven:
            logger.info(
                "TTS pipeline = Gemini (%s / %s) + repli ElevenLabs sur quota 429",
                env.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
                env.get("GEMINI_TTS_VOICE", "Kore"),
            )
            return tts.FallbackAdapter([gemini, _build_voice_elevenlabs(env)])
        logger.warning(
            "TTS pipeline = Gemini SANS repli (ELEVENLABS_API_KEY absente) — "
            "coupure audio probable dès que le quota Gemini (10/min) est atteint."
        )
        return gemini

    logger.info("TTS pipeline = ElevenLabs")
    return _build_voice_elevenlabs(env)


def _build_voice_llm(env: dict) -> object:
    """Construit le LLM du pipeline vocal LiveKit selon API_BACKEND.

    Le pipeline temps réel LiveKit utilise ses propres plugins LLM (process
    séparé du gateway in-house). On route ici vers le plugin correspondant au
    backend configuré pour ne pas forcer une dépendance Anthropic/Gemini.
    Fallback Gemini 2.5 Flash si le plugin du backend n'est pas installé ou si
    le backend n'est pas géré côté LiveKit.
    """
    backend = (env.get("API_BACKEND") or "anthropic").strip().lower()

    def _gemini() -> object:
        model = env.get("VOICE_LLM_MODEL") or "gemini-2.5-flash"
        return lk_google.LLM(model=model, temperature=0.7)

    try:
        if backend == "openai":
            from livekit.plugins import openai as lk_openai

            model = env.get("VOICE_LLM_MODEL") or env.get("OPENAI_MODEL") or "gpt-4o-mini"
            logger.info("Voice LLM — OpenAI %s", model)
            return lk_openai.LLM(model=model, temperature=0.7)

        if backend == "mistral":
            from livekit.plugins import openai as lk_openai

            model = env.get("VOICE_LLM_MODEL") or env.get("MISTRAL_MODEL") or "mistral-large-latest"
            logger.info("Voice LLM — Mistral %s", model)
            return lk_openai.LLM(
                model=model,
                temperature=0.7,
                base_url="https://api.mistral.ai/v1",
                api_key=env.get("MISTRAL_API_KEY", os.getenv("MISTRAL_API_KEY", "")),
            )

        if backend == "anthropic":
            from livekit.plugins import anthropic as lk_anthropic

            model = (
                env.get("VOICE_LLM_MODEL")
                or env.get("VOICE_ANTHROPIC_MODEL")
                or env.get("ANTHROPIC_MODEL")
                or "claude-haiku-4-5-20251001"
            )
            logger.info("Voice LLM — Anthropic %s", model)
            return lk_anthropic.LLM(model=model, temperature=0.7)
    except ImportError as exc:
        logger.warning(
            "Plugin LiveKit pour backend '%s' manquant (%s) — fallback Gemini. "
            "Installer le plugin correspondant via uv sync pour router le vocal sur ce backend.",
            backend,
            exc,
        )
        return _gemini()

    logger.info("Voice LLM — Gemini (backend '%s' non géré côté LiveKit)", backend)
    return _gemini()


# ─── Session et pipeline ───────────────────────────────────────────────────────


async def entrypoint(ctx: object) -> None:

    _env = dotenv_values(PROJECT_ROOT / ".env")

    # TTS sélectionné via TTS_PROVIDER (Gemini + repli ElevenLabs, ou ElevenLabs seul).
    _tts = _build_voice_tts(_env)

    # Pré-connecte la room avec un connect_timeout étendu pour éviter les retries v0/v1 de 5s.
    # livekit-agents utilise rtc.RoomOptions() sans connect_timeout (défaut Rust ~5s),
    # ce qui cause des timeouts systématiques sur le v0 path. On se connecte nous-mêmes d'abord.
    _info = getattr(ctx, "_info", None)
    if _info and not getattr(ctx, "_connected", False):
        try:
            await ctx.room.connect(
                _info.url,
                _info.token,
                options=lk_rtc.RoomOptions(auto_subscribe=True, connect_timeout=15.0),
            )
            ctx._connected = True  # empêche la double connexion dans session.start()
            logger.info("Room pre-connected: %s", ctx.room.name)
        except Exception as e:
            logger.warning("Pre-connect failed (%s), session.start() va réessayer", e)

    # Récupère les données pré-chargées par prewarm (fallback si prewarm non exécuté)
    userdata = getattr(ctx, "proc", None)
    userdata = getattr(userdata, "userdata", {}) if userdata else {}
    instructions = userdata.get("instructions") or _build_voice_instructions()
    tools = userdata.get("tools") or _build_voice_tools()
    vad = userdata.get("vad") or silero.VAD.load(
        min_speech_duration=0.05,
        min_silence_duration=0.2,
        activation_threshold=0.5,
    )

    session = AgentSession(
        # VAD — détection de voix (pré-chargé dans prewarm)
        vad=vad,
        # STT — sélectionné via STT_PROVIDER (deepgram / openai / google).
        stt=_build_voice_stt(_env),
        # LLM — routé selon API_BACKEND (fallback Gemini 2.5 Flash)
        llm=_build_voice_llm(_env),
        # TTS — sélectionné plus haut selon TTS_PROVIDER (Gemini ou ElevenLabs).
        tts=_tts,
        # Désactive l'adaptive interruption (agent-gateway.livekit.cloud) — local dev only
        turn_handling={"interruption": {"mode": "vad"}},
    )

    agent = JarvisVoiceAgent(instructions=instructions, tools=tools)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=RoomOptions(
            audio_input=AudioInputOptions(noise_cancellation=None),
        ),
    )


# ─── Lancement ────────────────────────────────────────────────────────────────


def main() -> None:
    """Point d'entrée du process voix (LiveKit). Appelé par :
    - `python -m jarvis.interfaces.voice.agent <args>` (entry point cible)
    - `python voice_agent.py <args>` (shim racine pendant la migration)
    """
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="jarvis",
            initialize_process_timeout=30.0,  # 10s par défaut, trop court si réseau lent
            max_retry=32,
            # Garde 1 process Python pré-chauffé (skills/tools/VAD déjà chargés)
            # pour que le clic micro ne paie pas un cold start de 5-7s.
            num_idle_processes=1,
        )
    )


if __name__ == "__main__":
    main()
