from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from agent.orchestrator import ProjectOrchestrator
from api.admin import _ui_router as admin_ui_router
from api.admin import router as admin_router
from api.http import router as http_router
from api.projects import router as projects_router
from api.voice_ws import router as voice_router
from api.websocket import router as ws_router
from api.globe import router as globe_router
from api.spotify import router as spotify_router
from api.widgets import router as widgets_router
from background.notifications import NotificationQueue, ProactiveQueue
from proactive.engine import ProactiveEngine
from background.scheduler import Scheduler
from background.worker import BackgroundWorker
from config.settings import settings
from core.agent import Agent
from core.approval_checker import ApprovalChecker
from core.gateway import Gateway
from core.session import SessionManager
from llm.api import AnthropicProvider
from llm.factory import create_background_llm, get_llm_provider
from memory.auto_dream import AutoDream
from memory.consolidation import ConsolidationAgent
from memory.index import MemoryIndex
from memory.sessions import SessionStore
from memory.topics import TopicStore
from skills._registry import SkillRegistry
from tools.browser import BrowserTool
from tools.vision import VisionTool
from tools.calendar import CalendarCreateTool, CalendarListTool
from tools.cli import CLIRunnerTool, ExecuteCLITool
from tools.gmail import GmailListTool
from tools.filesystem import FindFilesTool, ReadFileTool
from tools.memory import MemoryTopicWriteTool
from tools.notion import NotionTasksTool
from tools.registry import ToolRegistry
from tools.fusion import FusionTool
from tools.printer import Printer3DTool
from tools.spotify import SpotifyTool
from tools.weather import WeatherTool

# ── Logging ──────────────────────────────────────────────────
_LOG_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan> — {message}"
)
from api.http import _log_sink

logger.remove()
logger.add(sys.stderr, level=settings.log_level, format=_LOG_FORMAT, colorize=True)
logger.add(_log_sink, level="INFO", format="{time:HH:mm:ss} | {level: <8} | {name} — {message}")


# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    memory_dir = Path(settings.memory_dir)

    session_store = SessionStore(memory_dir / "sessions")
    memory_index = MemoryIndex(memory_dir)
    topic_store = TopicStore(memory_dir / "topics")
    user_prefs_path = memory_dir / "user_prefs.md"

    llm = get_llm_provider()
    background_llm = create_background_llm()
    voice_llm = AnthropicProvider(model=settings.voice_anthropic_model, max_tokens=1024)

    # ── Skill registry ───────────────────────────────────────
    skill_registry = SkillRegistry(Path(settings.skills_dir))

    # ── Tool registry ────────────────────────────────────────
    allowed_roots = [Path(r).expanduser().resolve() for r in settings.file_search_roots]
    calendar_list_tool = CalendarListTool(
        credentials_path=Path(settings.google_credentials_path),
        token_path=Path(settings.google_token_path),
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
            credentials_path=Path(settings.google_credentials_path),
            token_path=Path(settings.google_token_path),
        ),
        NotionTasksTool(),
        MemoryTopicWriteTool(),
        Printer3DTool(),
        FusionTool(),
        SpotifyTool(),
        GmailListTool(
            credentials_path=Path(settings.google_credentials_path),
            token_path=Path(settings.google_token_path).parent / "google_gmail_token.json",
        ),
    )

    agent = Agent(
        llm=llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
    )
    voice_agent = Agent(
        llm=voice_llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
    )
    session_manager = SessionManager(store=session_store)
    consolidation = ConsolidationAgent(
        llm=background_llm, memory_index=memory_index, topic_store=topic_store
    )

    auto_dream = AutoDream(
        llm=background_llm,
        prefs_path=user_prefs_path,
        sessions_dir=memory_dir / "sessions",
    )

    notifications = NotificationQueue()
    proactive_queue = ProactiveQueue()
    approval_checker = ApprovalChecker(broadcast_event=proactive_queue.broadcast_event)
    orchestrator = ProjectOrchestrator(broadcast_event=proactive_queue.broadcast_event)
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
    )
    scheduler.start()

    proactive_engine = ProactiveEngine(
        notification_queue=notifications,
        broadcast_event=proactive_queue.broadcast_event,
        interval_minutes=30,
    )
    asyncio.create_task(proactive_engine.start(), name="proactive-engine")

    # ── LiveKit Voice Agent ──────────────────────────────────
    voice_server = None
    voice_agent_task = None
    if os.getenv("LIVEKIT_URL"):
        try:
            from livekit.agents import WorkerOptions
            from livekit.agents.worker import AgentServer
            from voice_agent import entrypoint as voice_entrypoint
            voice_server = AgentServer.from_server_options(
                WorkerOptions(entrypoint_fnc=voice_entrypoint, agent_name="jarvis")
            )
            voice_agent_task = asyncio.create_task(voice_server.run(), name="livekit-voice-agent")

            def _on_voice_task_done(t: asyncio.Task) -> None:
                if not t.cancelled() and t.exception():
                    logger.error("LiveKit voice agent crash", error=str(t.exception()))

            voice_agent_task.add_done_callback(_on_voice_task_done)
            logger.info("LiveKit voice agent démarré")
        except Exception as e:
            logger.warning("LiveKit voice agent non démarré", error=str(e))
    else:
        logger.info("LIVEKIT_URL absent — voice agent LiveKit désactivé")

    app.state.orchestrator = orchestrator
    app.state.session_store = session_store
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.state.gateway = Gateway(
        session_manager=session_manager,
        agent=agent,
        notifications=notifications,
        worker=worker,
    )
    app.state.voice_gateway = Gateway(
        session_manager=session_manager,
        agent=voice_agent,
        notifications=notifications,
        worker=worker,
    )
    app.state.worker = worker
    app.state.consolidation = consolidation
    app.state.auto_dream = auto_dream
    app.state.proactive_queue = proactive_queue
    app.state.scheduler = scheduler
    app.state.notifications = notifications
    app.state.proactive_engine = proactive_engine
    app.state.approval_checker = approval_checker
    from core.approval_checker import set_approval_checker
    set_approval_checker(approval_checker)

    logger.info(
        "Jarvis démarré",
        env=settings.environment,
        llm_provider=settings.llm_provider,
        memory_dir=str(memory_dir),
        tools=len(tool_registry.schemas()),
        skills=len(skill_registry.active),
        notification_queue_id=id(notifications),
    )
    yield

    scheduler.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    if voice_server:
        await voice_server.aclose()
    if voice_agent_task and not voice_agent_task.done():
        voice_agent_task.cancel()
        try:
            await voice_agent_task
        except asyncio.CancelledError:
            pass
    logger.info("Jarvis arrêté")


# ── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="Jarvis V3",
    description="Assistant personnel intelligent vocal temps réel.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(http_router)
app.include_router(ws_router)
app.include_router(voice_router)
app.include_router(admin_ui_router)
app.include_router(admin_router)
app.include_router(projects_router)
app.include_router(widgets_router)
app.include_router(spotify_router)
app.include_router(globe_router)

# UI statique montée en dernier pour ne pas masquer les routes API
app.mount("/", StaticFiles(directory="ui/static", html=True), name="ui")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        reload_dirs=["api", "agent", "audio", "background", "config", "core",
                     "llm", "memory", "prompts", "skills", "tools", "ui"],
        log_level="warning",
    )
