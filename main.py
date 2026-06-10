from __future__ import annotations

import asyncio
import os
import sys
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

import channels.telegram_bot as _tg_module
from agent.orchestrator import ProjectOrchestrator
from agent.reflexion import Reflexion
from api.admin import _ui_router as admin_ui_router
from api.admin import router as admin_router
from api.deezer import router as deezer_router
from api.globe import router as globe_router
from api.google_oauth import router as google_oauth_router
from api.http import _log_sink
from api.http import router as http_router
from api.http_budget import router as budget_router
from api.http_routines import router as routines_router
from api.local_music import router as local_music_router
from api.macropad_2k import _ui_router as macropad_ui_router
from api.macropad_2k import router as macropad_router
from api.music import router as music_router
from api.projects import router as projects_router
from api.spotify import router as spotify_router
from api.voice_ws import router as voice_router
from api.websocket import router as ws_router
from api.widgets import router as widgets_router
from background.notifications import NotificationQueue, ProactiveQueue
from background.scheduler import Scheduler
from background.worker import BackgroundWorker
from channels.telegram_bot import TelegramChannel, get_telegram_channel
from config.settings import settings
from core.agent import Agent
from core.approval_checker import ApprovalChecker
from core.auth import verify_api_token  # ── [AUTH] ──
from core.gateway import Gateway
from core.session import SessionManager
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.llm.factory import create_background_llm, get_llm_provider
from jarvis.providers.memory.auto_dream import AutoDream
from jarvis.providers.memory.consolidation import ConsolidationAgent, CrossSessionRecall
from jarvis.providers.memory.index import MemoryIndex
from jarvis.providers.memory.ingest import MemoryIngest
from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.search import FTSIndex, VectorIndex
from jarvis.providers.memory.sessions import SessionStore
from jarvis.providers.memory.topics import TopicStore
from jarvis.providers.memory.user_model import UserModel
from proactive.engine import ProactiveEngine
from skills.registry import skill_registry
from tools.browser import BrowserTool
from tools.calendar import CalendarCreateTool, CalendarListTool
from tools.cli import CLIRunnerTool, ExecuteCLITool
from tools.filesystem import FindFilesTool, ReadFileTool
from tools.gmail import GmailListTool
from tools.memory import (
    CrossSessionRecallTool,
    MemoryLoadTopicTool,
    MemorySearchTool,
    MemoryTopicWriteTool,
)
from tools.notion import NotionTasksTool
from tools.preset import ExecutePresetTool
from tools.registry import ToolRegistry
from tools.show_view import ShowViewTool
from tools.spotify import SpotifyTool
from tools.subagent import ScriptRPCTool, SpawnSubagentTool
from tools.vision import VisionTool
from tools.weather import WeatherTool

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
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    memory_dir = Path(settings.memory_dir)

    session_store = SessionStore(memory_dir / "sessions")
    memory_index = MemoryIndex(memory_dir)
    topic_store = TopicStore(memory_dir / "topics")
    user_prefs_path = memory_dir / "user_prefs.md"

    vector_index = VectorIndex(index_dir=memory_dir / "vector_index")
    if vector_index.is_empty():
        # Construction initiale en arrière-plan — ne bloque pas le démarrage
        asyncio.create_task(
            vector_index.reindex(
                topic_store=topic_store,
                transcripts_dir=memory_dir / "sessions",
            ),
            name="vector-index-reindex",
        )

    fts_index = FTSIndex(db_path=memory_dir / "fts_index.db")
    asyncio.create_task(
        _fts_rebuild_if_empty(fts_index, memory_dir / "sessions"),
        name="fts-index-reindex",
    )

    llm = get_llm_provider()
    background_llm = create_background_llm()
    # En mode local, la voix utilise le même provider Ollama (pas d'Anthropic disponible)
    voice_llm = (
        get_llm_provider()
        if settings.llm_provider == "local"
        else AnthropicProvider(model=settings.voice_anthropic_model, max_tokens=1024)
    )

    # ── Skill registry ───────────────────────────────────────
    # singleton chargé à l'import — reload() pour forcer un rechargement
    skill_registry.reload()

    # ── Tool registry ────────────────────────────────────────
    _root = Path(__file__).parent
    _google_creds = (_root / settings.google_credentials_path).resolve()
    _gmail_token = (_root / "config/google_gmail_token.json").resolve()
    _calendar_token = (_root / settings.google_token_path).resolve()

    allowed_roots = [Path(r).expanduser().resolve() for r in settings.file_search_roots]
    calendar_list_tool = CalendarListTool(
        credentials_path=_google_creds,
        token_path=_calendar_token,
    )
    tool_registry = ToolRegistry()
    tool_registry.register(
        WeatherTool(),
        BrowserTool(),
        VisionTool(),
        ReadFileTool(allowed_roots=allowed_roots),
        FindFilesTool(allowed_roots=allowed_roots),
        CLIRunnerTool(whitelist_path=Path(settings.cli_whitelist_path)),
        ExecuteCLITool(),
        calendar_list_tool,
        CalendarCreateTool(
            credentials_path=_google_creds,
            token_path=_calendar_token,
        ),
        NotionTasksTool(),
        MemoryTopicWriteTool(vector_index=vector_index),
        MemoryLoadTopicTool(),
        MemorySearchTool(vector_index=vector_index),
        SpotifyTool(),
        GmailListTool(
            credentials_path=_google_creds,
            token_path=_gmail_token,
        ),
    )
    # Enregistre les outils fournis par les skills installés
    tool_registry.replace_skill_tools(*skill_registry.get_all_tools())

    user_model_path = memory_dir / "user_model.md"

    agent = Agent(
        llm=llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
        user_model_path=user_model_path,
    )
    voice_agent = Agent(
        llm=voice_llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
        user_model_path=user_model_path,
    )
    session_manager = SessionManager(store=session_store)

    # ── Memory Kernel + Ingest (PHASE 2/3, MOUVEMENT 2 option D) ────────────
    # Le Kernel est TOUJOURS instancié (la PHASE 2 Reflexion en a besoin pour
    # les leçons de mission). L'ingestion BATCH des sessions conversationnelles
    # est branchée UNIQUEMENT sur AutoDream.deep (passe nocturne à 3h), sous
    # contrôle du flag settings.ingest_deep_enabled (défaut False).
    #
    # ConsolidationAgent + AutoDream micro (hooks à chaque message) NE SONT
    # JAMAIS branchés au Kernel : décision Generative Agents (synthèse
    # périodique sur la conversation complète, pas extraction à chaud
    # message-par-message qui doublonnerait et ferait du bruit).
    _memory_kernel = MemoryKernel(memory_dir / "jarvis_memory.db")
    _memory_ingest = MemoryIngest(kernel=_memory_kernel, llm=background_llm)
    _deep_ingest = _memory_ingest if settings.ingest_deep_enabled else None

    # Miroir Markdown du Kernel (§6.7) — régénéré en passe nocturne deep,
    # SQLite → MD strictement unidirectionnel. Lisible via Atelier/Mémoire/Facts.
    from jarvis.providers.memory.mirror import MemoryMirror

    _memory_mirror = MemoryMirror(_memory_kernel, memory_dir / "mirror")
    app.state.memory_kernel = _memory_kernel
    app.state.memory_mirror = _memory_mirror
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

    consolidation = ConsolidationAgent(
        llm=background_llm,
        memory_index=memory_index,
        topic_store=topic_store,
        memory_ingest=None,  # JAMAIS branché — choix d'archi (cf. ci-dessus).
    )

    auto_dream = AutoDream(
        llm=background_llm,
        prefs_path=user_prefs_path,
        sessions_dir=memory_dir / "sessions",
        memory_ingest=_deep_ingest,  # consommé UNIQUEMENT par _run_deep.
        mirror=_memory_mirror,  # régénéré après ingest deep (§6.7).
    )

    notifications = NotificationQueue()
    proactive_queue = ProactiveQueue()
    # Tools core (indépendants des skills installés)
    tool_registry.register(ShowViewTool(broadcast_event=proactive_queue.broadcast_event))
    tool_registry.register(ExecutePresetTool())
    approval_checker = ApprovalChecker(broadcast_event=proactive_queue.broadcast_event)

    # ── [MEMORY-RECALL] ──────────────────────────────────────────────────────
    _cross_recall = CrossSessionRecall(
        llm=background_llm,
        fts_index=fts_index,
        vector_index=vector_index,
    )
    _user_model = UserModel(llm=background_llm, model_path=user_model_path)
    tool_registry.register(
        CrossSessionRecallTool(fts_index=fts_index, vector_index=vector_index),
    )
    logger.info("Memory recall initialisé (FTS5 + vecteur + UserModel)")
    # ── [/MEMORY-RECALL] ─────────────────────────────────────────────────────

    # Expose singletons pour les presets (executor + tool)
    from background.notifications import set_proactive_queue
    from core.gateway import set_tool_registry

    set_proactive_queue(proactive_queue)
    set_tool_registry(tool_registry)
    # ── [BUDGET] ─────────────────────────────────────────────────────────────
    from core.budget import BudgetGuard, set_budget_guard

    if settings.budget_enabled:
        _budget_guard: BudgetGuard | None = BudgetGuard(
            notify_callback=proactive_queue.broadcast_event
        )
        set_budget_guard(_budget_guard)
        logger.info(
            "BudgetGuard activé",
            monthly_usd=settings.budget_monthly_usd,
            per_project_usd=settings.budget_per_project_usd,
            warn_pct=settings.budget_warn_pct,
        )
    else:
        _budget_guard = None
    # ── [/BUDGET] ────────────────────────────────────────────────────────────

    # ── [SKILL LAB] PHASE 4 — porte unique d'entrée pour les skills générées
    # Le Lab doit être construit AVANT le SkillCreateTool car celui-ci passe
    # désormais par lab.propose_from_trajectory() (aucune installation directe
    # possible — pas de backdoor pour le voice agent).
    from skills.lab import SkillLab
    from skills.lifecycle import SkillLifecycle
    from skills.synthesizer import SkillSynthesizer
    from tools.skills import SkillCreateTool, SkillImproveTool, SkillListTool

    _synthesizer = SkillSynthesizer(llm=llm)
    app.state.skill_synthesizer = _synthesizer

    _skill_lifecycle = SkillLifecycle(db_path=memory_dir / "jarvis_memory.db")
    _skill_lab = SkillLab(
        kernel=_memory_kernel,
        lifecycle=_skill_lifecycle,
        synthesizer=_synthesizer,
        registry_reload=skill_registry.reload,
    )
    app.state.skill_lab = _skill_lab
    app.state.skill_lifecycle = _skill_lifecycle

    # SkillCreateTool est obligatoirement câblé au Lab : il ne peut PAS
    # installer directement, il propose une candidate qui doit passer par
    # le sandbox + validation humaine.
    tool_registry.register(
        SkillCreateTool(lab=_skill_lab),
        SkillImproveTool(synthesizer=_synthesizer),
        SkillListTool(),
    )
    logger.info(
        "Skills tools enregistrés (skill_create→Lab, skill_improve, skill_list)"
    )
    logger.info(
        "Skill Lab activé — polling Kernel skill_candidate_proposal nocturne (3h05)"
    )
    # ── [/SKILL LAB] ─────────────────────────────────────────────────────────

    # ── [CAPABILITY ENGINE] PHASE 5 — auto-extension contrôlée
    # Détecte les gaps signalés par l'agent et délègue au Skill Lab. AUCUNE
    # auto-installation en MVP (cf. CDC §8) : toute candidate exige promote()
    # humain, peu importe le verdict sandbox ou la whitelist.
    from agent.capability_engine import CapabilityEngine, Whitelist
    from tools.capability import ReportMissingCapabilityTool

    _whitelist = Whitelist.load(Path("config/permissions.yaml"))
    _capability_engine = CapabilityEngine(
        kernel=_memory_kernel,
        lab=_skill_lab,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        whitelist=_whitelist,
        auto_install_enabled=settings.auto_install_whitelisted_enabled,
    )
    app.state.capability_engine = _capability_engine
    tool_registry.register(
        ReportMissingCapabilityTool(engine=_capability_engine),
    )
    if settings.auto_install_whitelisted_enabled:
        logger.warning(
            "Capability Engine AUTO-INSTALL flag ON — flag stocké mais INERTE "
            "en PHASE 5 MVP, toute candidate exige promote() humain."
        )
    else:
        logger.info(
            "Capability Engine activé — toute candidate exige validation humaine "
            f"({len(_whitelist.domains)} domaine(s) whitelistés, inertes en MVP)"
        )
    # ── [/CAPABILITY ENGINE] ─────────────────────────────────────────────────

    # ── [BACKENDS] ───────────────────────────────────────────────────────────
    # Agent doit être créé AVANT cet bloc (SpawnSubagentTool référence l'agent).
    from config.backends import backends_config as _backends_cfg

    tool_registry.register(
        SpawnSubagentTool(agent=agent),
        ScriptRPCTool(
            tool_registry=tool_registry,
            workspace_path=str(Path(settings.memory_dir) / "rpc_workspace"),
        ),
    )
    logger.info(
        "Backend tools enregistrés",
        default_backend=str(_backends_cfg.default_backend),
        tools=["spawn_subagent", "execute_script"],
    )
    # ── [/BACKENDS] ──────────────────────────────────────────────────────────

    # PHASE 2 — Reflexion post-mission. Toujours actif (ingestion uniquement à la
    # clôture d'une mission, fréquence basse) ; consomme le _memory_ingest
    # construit plus haut.
    _reflexion = Reflexion(
        llm=background_llm,
        kernel=_memory_kernel,
        memory_ingest=_memory_ingest,
    )

    orchestrator = ProjectOrchestrator(
        broadcast_event=proactive_queue.broadcast_event,
        budget_guard=_budget_guard,
        reflexion=_reflexion,
    )

    # ── [INITIATIVES] ────────────────────────────────────────────────────────
    from proactive.executor import InitiativeExecutor as _InitiativeExecutor
    from proactive.store import InitiativeStore as _InitiativeStore

    _initiative_store = _InitiativeStore()
    _initiative_executor = _InitiativeExecutor(
        store=_initiative_store,
        broadcast_event=proactive_queue.broadcast_event,
        orchestrator=orchestrator,
        approval_checker=approval_checker,
        budget_guard=_budget_guard,
    )
    # ── [/INITIATIVES] ───────────────────────────────────────────────────────

    # ── [CURATOR + COMMAND CENTER] PHASE 6 — maintenance nocturne + vue agrégée
    # Curator : tourne dans le scheduler (3h10), produit un rapport, n'applique
    # RIEN automatiquement en MVP. Endpoint manuel /api/curator/scan pour
    # itérer pendant l'observation.
    # Command Center : agrégateur lecture-seule des workstreams (initiatives,
    # missions, budget, skills). Sert au dashboard, ne court-circuite aucun
    # endpoint des phases précédentes.
    from proactive.command_center import CommandCenter
    from proactive.curator import Curator

    _curator = Curator(
        kernel=_memory_kernel,
        skill_lifecycle=_skill_lifecycle,
        initiative_store=_initiative_store,
        budget_guard=_budget_guard,
        reports_dir=Path(settings.memory_dir) / "curator_reports",
    )
    _command_center = CommandCenter(
        initiative_store=_initiative_store,
        project_store=orchestrator._store,
        budget_guard=_budget_guard,
        skill_lifecycle=_skill_lifecycle,
    )
    app.state.curator = _curator
    app.state.command_center = _command_center
    if settings.autonomy_auto_execute_enabled:
        logger.warning(
            "Autonomy auto-exec flag ON — flag stocké mais INERTE en MVP, "
            "toute initiative ≥ niveau 3 passe par validation humaine."
        )
    else:
        logger.info("Autonomy auto-exec désactivé (MVP) — toute initiative validée humaine")
    logger.info("Curator activé (rapport-only en MVP, scan nocturne à 3h10)")
    logger.info("Command Center activé (vue agrégée lecture-seule)")
    # ── [/CURATOR + COMMAND CENTER] ──────────────────────────────────────────

    worker = BackgroundWorker(llm=llm, notifications=notifications, tool_registry=tool_registry)
    worker_task = asyncio.create_task(worker.run_loop(), name="background-worker")

    if settings.vision_object_detection:
        from vision.daemon import run_vision_daemon

        asyncio.create_task(run_vision_daemon(), name="vision-daemon")

    if settings.clap_detection_enabled:
        from audio.clap_detector import ClapDetector

        async def _on_clap() -> None:
            proactive_queue.broadcast_event({"type": "wake_up", "trigger": "clap"})
            logger.info("Wake up triggered by clap")

        clap_detector = ClapDetector(callback=_on_clap)
        asyncio.create_task(clap_detector.start(), name="clap-detector")
        logger.info("ClapDetector started")

    scheduler = Scheduler(
        proactive=proactive_queue,
        auto_dream=auto_dream,
        calendar_tool=calendar_list_tool,
        skill_lab=_skill_lab,
        curator=_curator,
    )
    scheduler.start()

    proactive_engine = ProactiveEngine(
        notification_queue=notifications,
        broadcast_event=proactive_queue.broadcast_event,
        interval_minutes=30,
    )
    asyncio.create_task(proactive_engine.start(), name="proactive-engine")

    # ── [ROUTINES] ────────────────────────────────────────────────────────────
    from background.routines import ROUTINES_ENABLED, Routine, RoutineStore  # noqa: F401

    if ROUTINES_ENABLED:
        _routine_store = RoutineStore()
        # Étendre _default_routines ici ou via l'API pour ajouter des routines.
        _default_routines: list[Routine] = []
        scheduler.start_routines(
            _default_routines,
            _routine_store,
            wake_engine=lambda: asyncio.create_task(
                proactive_engine.run_now(), name="routine-wake-engine"
            ),
        )
        app.state.routine_store = _routine_store
        logger.info("Routines moteur démarré", store=str(_routine_store._path))
    # ── [/ROUTINES] ───────────────────────────────────────────────────────────

    # Le worker LiveKit (vocal) tourne dans un process séparé via `voice_agent.py dev`
    # lancé par `jarvis start`. main.py ne s'occupe que du backend FastAPI / texte.

    app.state.orchestrator = orchestrator
    app.state.initiative_executor = _initiative_executor
    app.state.session_store = session_store
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.gateway = Gateway(
        session_manager=session_manager,
        agent=agent,
        notifications=notifications,
        worker=worker,
        recall=_cross_recall,
    )
    app.state.voice_gateway = Gateway(
        session_manager=session_manager,
        agent=voice_agent,
        notifications=notifications,
        worker=worker,
        recall=_cross_recall,
    )
    app.state.worker = worker
    app.state.consolidation = consolidation
    app.state.auto_dream = auto_dream
    app.state.proactive_queue = proactive_queue
    app.state.scheduler = scheduler
    app.state.notifications = notifications
    app.state.proactive_engine = proactive_engine
    app.state.approval_checker = approval_checker
    app.state.vector_index = vector_index
    app.state.fts_index = fts_index
    app.state.user_model = _user_model
    from core.approval_checker import set_approval_checker

    set_approval_checker(approval_checker)

    # Initialiser le registry analytics (charge la config sauvegardée)
    from analytics.registry import analytics_registry as _analytics_registry

    logger.info("AnalyticsRegistry initialisé", widgets=len(_analytics_registry.get_active()))

    # ── [GATEWAY] ────────────────────────────────────────────────────────────
    from api.channels import router as channels_router
    from channels.discord_bot import DiscordChannel
    from channels.gateway import MessagingGateway
    from core.connectivity import is_offline_mode

    _messaging_gw: MessagingGateway | None = None
    _telegram_enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    _discord_enabled = os.getenv("DISCORD_ENABLED", "false").lower() == "true"
    _messaging_enabled = os.getenv("MESSAGING_GATEWAY_ENABLED", "false").lower() == "true"

    # En mode local, les canaux réseau (Telegram, Discord) ne démarrent pas :
    # leur long-polling spamme les logs avec des erreurs réseau en boucle hors-ligne.
    if is_offline_mode() and (_telegram_enabled or _discord_enabled or _messaging_enabled):
        logger.info(
            "Canaux réseau (Telegram/Discord) désactivés — mode local actif",
            telegram=_telegram_enabled,
            discord=_discord_enabled,
        )
    elif _messaging_enabled:
        _messaging_gw = MessagingGateway(jarvis_gateway=app.state.gateway)

        if _telegram_enabled:
            telegram = TelegramChannel()
            _tg_module._telegram_instance = telegram
            _messaging_gw.register(telegram)

        if _discord_enabled:
            _messaging_gw.register(DiscordChannel())

        app.state.messaging_gateway = _messaging_gw
        app.include_router(channels_router)
        await _messaging_gw.start_all()
        logger.info(
            "MessagingGateway démarré",
            adapters=list(_messaging_gw._adapters.keys()),
        )
    elif _telegram_enabled:
        # Mode legacy : Telegram seul, session non persistée
        telegram = TelegramChannel(gateway=app.state.gateway)
        _tg_module._telegram_instance = telegram
        asyncio.create_task(telegram.start(), name="telegram-bot")
        logger.info("Canal Telegram démarré (mode legacy)")
    # ── [/GATEWAY] ───────────────────────────────────────────────────────────

    logger.info(
        "Jarvis démarré",
        env=settings.environment,
        llm_provider=settings.llm_provider,
        memory_dir=str(memory_dir),
        tools=len(tool_registry.schemas()),
        skills=len(skill_registry.list_installed()),
        notification_queue_id=id(notifications),
    )
    yield

    scheduler.stop()
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
            await telegram.stop()
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
    ["http://localhost:8000", "http://127.0.0.1:8000"]
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
# Les fichiers statiques (StaticFiles ASGI mount) et les WebSockets sont
# gérés séparément dans verify_api_token ; voir core/auth.py pour le périmètre.
app.router.dependencies.append(Depends(verify_api_token))
# ── [/AUTH] ──────────────────────────────────────────────────

app.include_router(http_router)
app.include_router(ws_router)
app.include_router(voice_router)
app.include_router(admin_ui_router)
app.include_router(admin_router)
app.include_router(projects_router)
app.include_router(widgets_router)
app.include_router(spotify_router)
app.include_router(deezer_router)
app.include_router(local_music_router)
app.include_router(music_router)
app.include_router(globe_router)
app.include_router(macropad_router)
app.include_router(macropad_ui_router)
app.include_router(google_oauth_router)

# ── [SURFACE] ────────────────────────────────────────────────────────────────
app.include_router(budget_router)
app.include_router(routines_router)

# ── [PHASE 6] Curator + Command Center routes
from api.http_curator import router as curator_router  # noqa: E402

app.include_router(curator_router)

# ── [UI/M5] État de santé des connecteurs (Réglages → Connexions)
from api.http_connectors import router as connectors_router  # noqa: E402

app.include_router(connectors_router)
# ── [/SURFACE] ───────────────────────────────────────────────────────────────


@app.get("/static/mapbox-style.json")
async def mapbox_style() -> FileResponse:
    return FileResponse("ui/static/mapbox-style.json", media_type="application/json")


# Vues dev (extensions liées) montées AVANT le mount global pour les servir
# en priorité sous /static/skills/<name>. Inerte si la zone n'existe pas.
from skills.dev_extensions import mount_dev_views  # noqa: E402

mount_dev_views(app)

# UI statique montée en dernier pour ne pas masquer les routes API
app.mount("/", StaticFiles(directory="ui/static", html=True), name="ui")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        reload_dirs=[
            "api",
            "agent",
            "audio",
            "background",
            "config",
            "core",
            "macropad_2k",
            "llm",
            "memory",
            "prompts",
            "skills",
            "tools",
            "ui",
        ],
        log_level="warning",
    )
