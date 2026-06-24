# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import sys

# Force UTF-8 on stdout/stderr before anything logs. When the process is launched
# with its streams redirected to a file (e.g. jarvis.ps1 run), Python defaults to the
# legacy ANSI code page (cp1252 on FR Windows) with strict errors, so a single log
# line carrying a non-cp1252 glyph raises UnicodeEncodeError and crashes startup with
# an empty log. backslashreplace guarantees logging never raises again.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI  # ── [AUTH] ──
from fastapi.middleware.cors import CORSMiddleware  # ── [AUTH] ──
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from jarvis.analytics.registry import analytics_registry as _analytics_registry
from jarvis.bootstrap import build
from jarvis.capabilities.skills.dev_extensions import mount_dev_views
from jarvis.capabilities.skills.registry import skill_registry
from jarvis.engine.auth import verify_api_token  # ── [AUTH] ──
from jarvis.engine.background.routines import ROUTINES_ENABLED, Routine, RoutineStore
from jarvis.interfaces.api.admin import _ui_router as admin_ui_router
from jarvis.interfaces.api.admin import router as admin_router
from jarvis.interfaces.api.briefing import router as briefing_router
from jarvis.interfaces.api.budget import router as budget_router
from jarvis.interfaces.api.deezer import router as deezer_router
from jarvis.interfaces.api.globe import router as globe_router
from jarvis.interfaces.api.google_oauth import router as google_oauth_router
from jarvis.interfaces.api.http import _log_sink
from jarvis.interfaces.api.http import router as http_router
from jarvis.interfaces.api.local_music import router as local_music_router
from jarvis.interfaces.api.macropad_2k import _ui_router as macropad_ui_router
from jarvis.interfaces.api.macropad_2k import router as macropad_router
from jarvis.interfaces.api.music import router as music_router
from jarvis.interfaces.api.projects import router as projects_router
from jarvis.interfaces.api.routines import router as routines_router
from jarvis.interfaces.api.spotify import router as spotify_router
from jarvis.interfaces.api.websocket import router as ws_router
from jarvis.interfaces.api.widgets import router as widgets_router
from jarvis.interfaces.channels.setup import setup_channels
from jarvis.interfaces.channels.telegram_bot import get_telegram_channel
from jarvis.kernel.paths import UI_STATIC_DIR
from jarvis.kernel.settings import settings
from jarvis.providers.audio.clap_detector import ClapDetector
from jarvis.providers.memory.search import FTSIndex
from jarvis.providers.vision.daemon import run_vision_daemon

# load_dotenv() doit tourner avant toute logique module-level qui consomme os.environ
load_dotenv()

# ── Logging ──────────────────────────────────────────────────
_LOG_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> — {message}"
)

logger.remove()
logger.add(sys.stderr, level=settings.log_level, format=_LOG_FORMAT, colorize=True)
logger.add(_log_sink, level="INFO", format="{time:HH:mm:ss} | {level: <8} | {name} — {message}")


async def _fts_rebuild_if_empty(fts_index: FTSIndex, sessions_dir: Path) -> None:
    if await fts_index.is_empty() and sessions_dir.exists():
        await fts_index.rebuild(sessions_dir)


# ── Lifespan ─────────────────────────────────────────────────
# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Phase C — Étape 2 (a) : app.py utilise bootstrap.build() pour construire
    # le graphe complet. Plus aucune instanciation directe ici.

    container = build(settings=settings)
    app.state.container = container

    # Compat — copie chaque objet du Container dans app.state.X pour les
    # routers FastAPI qui font `request.app.state.X` directement.
    # (À élaguer en E quand les routers migreront vers `request.app.state
    # .container.X`.)
    app.state.gateway = container.gateway
    app.state.voice_gateway = container.voice_gateway
    app.state.tool_registry = container.tool_registry
    app.state.skill_registry = skill_registry  # singleton module historique
    app.state.session_store = container.session_store
    app.state.orchestrator = container.orchestrator
    app.state.initiative_executor = container.initiative_executor
    app.state.worker = container.worker
    app.state.consolidation = container.consolidation
    app.state.auto_dream = container.auto_dream
    app.state.proactive_queue = container.proactive_queue
    app.state.scheduler = container.scheduler
    app.state.notifications = container.notifications
    app.state.proactive_engine = container.proactive_engine
    app.state.approval_checker = container.approval_checker
    app.state.vector_index = container.vector_index
    app.state.fts_index = container.fts_index
    app.state.user_model = container.user_model
    app.state.memory_kernel = container.memory_kernel
    app.state.memory_mirror = container.memory_mirror
    app.state.skill_synthesizer = container.skill_synthesizer
    app.state.skill_lab = container.skill_lab
    app.state.skill_lifecycle = container.skill_lifecycle
    app.state.capability_engine = container.capability_engine
    app.state.curator = container.curator
    app.state.command_center = container.command_center

    # Singleton résiduel post-étape 2 (b) :
    #  - `tracker` (jarvis.engine.tracking) reste module-level pour cette étape
    #    (b) et bascule en injection constructeur dans l'étape (d) qui touche
    #    providers/llm/api.py + providers/audio/tts.py (commit isolé pour bisect).
    #  set_proactive_queue / set_approval_checker sont câblés directement dans
    #  bootstrap.build() (Phase G — polish post-v0.2.0).

    if settings.budget_enabled:
        logger.info(
            "BudgetGuard activé",
            monthly_usd=settings.budget_monthly_usd,
            per_project_usd=settings.budget_per_project_usd,
            warn_pct=settings.budget_warn_pct,
        )

    if settings.ingest_deep_enabled:
        logger.warning(
            "Memory Kernel DEEP INGEST activé : "
            "AutoDream.deep ingérera les sessions à chaque passe nocturne (3h)."
        )
    else:
        logger.info(
            "Memory Kernel DEEP INGEST désactivé "
            "(settings.ingest_deep_enabled=False) — flip pour activer."
        )
    if settings.auto_install_whitelisted_enabled:
        logger.warning(
            "Capability Engine AUTO-INSTALL flag ON — flag stocké mais INERTE "
            "en PHASE 5 MVP, toute candidate exige promote() humain."
        )
    if settings.autonomy_auto_execute_enabled:
        logger.warning(
            "Autonomy auto-exec flag ON — flag stocké mais INERTE en MVP, "
            "toute initiative ≥ niveau 3 passe par validation humaine."
        )

    # Async tasks à lancer après construction
    memory_dir = Path(settings.memory_dir)
    if container.vector_index.is_empty():
        asyncio.create_task(
            container.vector_index.reindex(
                topic_store=container.topic_store,
                transcripts_dir=memory_dir / "sessions",
            ),
            name="vector-index-reindex",
        )
    asyncio.create_task(
        _fts_rebuild_if_empty(container.fts_index, memory_dir / "sessions"),
        name="fts-index-reindex",
    )

    if settings.vision_object_detection:
        asyncio.create_task(run_vision_daemon(), name="vision-daemon")

    if settings.clap_detection_enabled:

        async def _on_clap() -> None:
            container.proactive_queue.broadcast_event({"type": "wake_up", "trigger": "clap"})
            logger.info("Wake up triggered by clap")

        # start() logue lui-même son démarrage effectif (ou un avertissement clair
        # si aucun micro n'est disponible, cf. cas headless/VPS).
        clap_detector = ClapDetector(callback=_on_clap)
        asyncio.create_task(clap_detector.start(), name="clap-detector")

    worker_task = asyncio.create_task(container.worker.run_loop(), name="background-worker")
    container.scheduler.start()

    # Routines

    if ROUTINES_ENABLED:
        _routine_store = RoutineStore()
        _default_routines: list[Routine] = []
        container.scheduler.start_routines(
            _default_routines,
            _routine_store,
            wake_engine=lambda: asyncio.create_task(
                container.proactive_engine.run_now(), name="routine-wake-engine"
            ),
        )
        app.state.routine_store = _routine_store
        logger.info("Routines moteur démarré")

    asyncio.create_task(container.proactive_engine.start(), name="proactive-engine")

    # AnalyticsRegistry (charge la config sauvegardée)

    logger.info("AnalyticsRegistry initialisé", widgets=len(_analytics_registry.get_active()))

    # ── Channels (Telegram/Discord) — hors-Container par design (interfaces L3) ─

    _messaging_gw = await setup_channels(app, container)

    logger.info(
        "Jarvis démarré",
        env=settings.environment,
        llm_provider=settings.llm_provider,
        memory_dir=str(memory_dir),
        tools=len(container.tool_registry.schemas()),
        skills=len(skill_registry.list_installed()),
        notification_queue_id=id(container.notifications),
    )
    yield

    container.scheduler.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    if _messaging_gw is not None:
        await _messaging_gw.stop_all()
    else:
        telegram = get_telegram_channel()
        if telegram:
            try:
                await telegram.stop()
            except RuntimeError as e:
                # Bug pré-existant : telegram.stop() lève si updater jamais démarré.
                # Cf. BACKLOG Phase C — résolution future hors-périmètre étape 2.
                logger.warning("Telegram shutdown ignored: %s", e)
    logger.info("Jarvis arrêté")


# ── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="Jarvis V3",
    description="Assistant personnel intelligent vocal temps réel.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── [AUTH] ───────────────────────────────────────────────────
# CORS : origines explicites si configurées, localhost par défaut en mode local.
# allow_credentials=True exige des origines nommées (jamais "*" + credentials).
_cors_origins: list[str] = settings.cors_allow_origins or (
    [f"http://localhost:{settings.port}", f"http://127.0.0.1:{settings.port}"]
    if not settings.api_auth_enabled
    else []
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
# Dépendance globale appliquée à toutes les routes FastAPI.
# Les pages HTML UI, le mount StaticFiles et les WebSockets sont gérés
# dans verify_api_token ; voir engine/auth.py pour le périmètre.
app.router.dependencies.append(Depends(verify_api_token))
# ── [/AUTH] ──────────────────────────────────────────────────

app.include_router(http_router)
app.include_router(ws_router)
app.include_router(admin_ui_router)
app.include_router(admin_router)
app.include_router(projects_router)
app.include_router(widgets_router)
app.include_router(spotify_router)
app.include_router(deezer_router)
app.include_router(local_music_router)
app.include_router(music_router)
app.include_router(globe_router)
app.include_router(briefing_router)
app.include_router(macropad_router)
app.include_router(macropad_ui_router)
app.include_router(google_oauth_router)

# ── [SURFACE] ────────────────────────────────────────────────────────────────
app.include_router(budget_router)
app.include_router(routines_router)

# ── [PHASE 6] Curator + Command Center routes
from jarvis.interfaces.api.curator import router as curator_router  # noqa: E402

app.include_router(curator_router)

# ── [UI/M5] État de santé des connecteurs (Réglages → Connexions)
from jarvis.interfaces.api.connectors import router as connectors_router  # noqa: E402

app.include_router(connectors_router)
# ── [/SURFACE] ───────────────────────────────────────────────────────────────


@app.get("/static/mapbox-style.json")
async def mapbox_style() -> FileResponse:
    return FileResponse(str(UI_STATIC_DIR / "mapbox-style.json"), media_type="application/json")


# Vues dev (extensions liées) montées AVANT le mount global pour les servir
# en priorité sous /static/skills/<name>. Inerte si la zone n'existe pas.
mount_dev_views(app)

# UI statique montée en dernier pour ne pas masquer les routes API
app.mount("/", StaticFiles(directory=str(UI_STATIC_DIR), html=True), name="ui")


def main() -> None:
    """Point d'entrée du process API (FastAPI). Appelé par :
    - `python -m jarvis.app` (entry point cible, B.4)
    - `python main.py` (shim racine pendant la migration)
    """
    uvicorn.run(
        "jarvis.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        reload_dirs=["src/jarvis", "prompts", "config"],
        log_level="warning",
    )


if __name__ == "__main__":
    main()
