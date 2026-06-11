"""Composition root — CDC §C.1.

UNIQUE point d'instanciation du graphe d'objets de Jarvis. AUCUNE logique
métier ici : juste de la construction et du câblage.

Ordre strict de construction (CDC §C.1) :

    settings → bus → providers → capabilities → engine

Phase C — Étape 1 (Construction) : `build()` construit le graphe COMPLET
(~30 objets). app.py reste sur l'ancien câblage à cette étape — habitable,
zéro comportement changé. L'étape 2 (Bascule) basculera app.py et le
process voix sur ce Container, supprimant les 3 singletons en bloc.

`build()` est SYNCHRONE et ne LANCE PAS d'async tasks (reindex FTS,
vector_index, worker loop, scheduler, proactive_engine, etc.). Les
tasks sont lancées par les callers (app.py ou voice/agent.py) après
`build()`.

GATE C6 : `build()` construit le graphe SANS RÉSEAU (aucun appel HTTP
sortant pendant la construction — les LLM clients sont instanciés mais
ne contactent pas leur API tant qu'on n'appelle pas `.complete()`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jarvis.capabilities.skills.lab import SkillLab
from jarvis.capabilities.skills.lifecycle import SkillLifecycle
from jarvis.capabilities.skills.registry import skill_registry
from jarvis.capabilities.skills.synthesizer import SkillSynthesizer
from jarvis.capabilities.tools.browser import BrowserTool
from jarvis.capabilities.tools.calendar import CalendarCreateTool, CalendarListTool
from jarvis.capabilities.tools.capability import ReportMissingCapabilityTool
from jarvis.capabilities.tools.cli import CLIRunnerTool, ExecuteCLITool
from jarvis.capabilities.tools.filesystem import FindFilesTool, ReadFileTool
from jarvis.capabilities.tools.gmail import GmailListTool, send_gmail_draft
from jarvis.capabilities.tools.memory import (
    CrossSessionRecallTool,
    MemoryLoadTopicTool,
    MemorySearchTool,
    MemoryTopicWriteTool,
)
from jarvis.capabilities.tools.notion import NotionTasksTool
from jarvis.capabilities.tools.preset import ExecutePresetTool
from jarvis.capabilities.tools.registry import ToolRegistry
from jarvis.capabilities.tools.show_view import ShowViewTool
from jarvis.capabilities.tools.skills import SkillCreateTool, SkillImproveTool, SkillListTool
from jarvis.capabilities.tools.spotify import SpotifyTool
from jarvis.capabilities.tools.subagent import ScriptRPCTool, SpawnSubagentTool
from jarvis.capabilities.tools.vision import VisionTool
from jarvis.capabilities.tools.weather import WeatherTool
from jarvis.engine.agent import Agent
from jarvis.engine.approval_checker import ApprovalChecker
from jarvis.engine.background.notifications import NotificationQueue, ProactiveQueue
from jarvis.engine.background.scheduler import Scheduler
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.budget import BudgetGuard
from jarvis.engine.gateway import Gateway
from jarvis.engine.mission.capability_engine import CapabilityEngine, Whitelist
from jarvis.engine.mission.orchestrator import ProjectOrchestrator
from jarvis.engine.mission.project_manager import ProjectManager
from jarvis.engine.mission.project_store import ProjectStore
from jarvis.engine.mission.reflexion import Reflexion
from jarvis.engine.proactive.command_center import CommandCenter
from jarvis.engine.proactive.context_builder import ContextBuilder
from jarvis.engine.proactive.curator import Curator
from jarvis.engine.proactive.engine import ProactiveEngine
from jarvis.engine.proactive.executor import InitiativeExecutor
from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.engine.session import SessionManager
from jarvis.engine.tracking import UsageEntry, UsageTracker
from jarvis.kernel.events import (
    BudgetThresholdReached,
    EventBus,
    MemoryIngested,
    MissionCompleted,
    NotificationRequested,
)
from jarvis.kernel.paths import CONFIG_DIR
from jarvis.kernel.settings import Settings
from jarvis.kernel.settings import settings as _default_settings
from jarvis.providers.audio.tts import tts_engine
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.llm.factory import create_background_llm, get_llm_provider
from jarvis.providers.memory import visual_memory as _visual_memory
from jarvis.providers.memory.auto_dream import AutoDream
from jarvis.providers.memory.consolidation import ConsolidationAgent, CrossSessionRecall
from jarvis.providers.memory.index import MemoryIndex
from jarvis.providers.memory.ingest import MemoryIngest
from jarvis.providers.memory.kernel import MemoryKernel
from jarvis.providers.memory.mirror import MemoryMirror
from jarvis.providers.memory.search import FTSIndex, VectorIndex
from jarvis.providers.memory.sessions import SessionStore
from jarvis.providers.memory.topics import TopicStore
from jarvis.providers.memory.user_model import UserModel


@dataclass
class Container:
    """Graphe d'objets construit par `build()` — CDC §C.1.

    Contient TOUS les objets engine/providers/capabilities du process
    courant (API ou voix). Les channels (Telegram/Discord), routines,
    routers FastAPI restent gérés par app.py (interfaces L3).
    """

    # ── Settings + bus ─────────────────────────────────────────────────────
    settings: Settings
    bus: EventBus

    # ── Providers L1 — Memory ──────────────────────────────────────────────
    session_store: SessionStore
    memory_index: MemoryIndex
    topic_store: TopicStore
    vector_index: VectorIndex
    fts_index: FTSIndex
    memory_kernel: MemoryKernel
    memory_ingest: MemoryIngest
    memory_mirror: MemoryMirror
    user_model: UserModel

    # ── Providers L1 — LLM ─────────────────────────────────────────────────
    llm: LLMProvider
    voice_llm: LLMProvider
    background_llm: LLMProvider

    # ── Providers L1 — autres ──────────────────────────────────────────────
    cross_recall: CrossSessionRecall
    consolidation: ConsolidationAgent
    auto_dream: AutoDream

    # ── Capabilities L1 ────────────────────────────────────────────────────
    calendar_list_tool: CalendarListTool
    tool_registry: ToolRegistry
    skill_synthesizer: SkillSynthesizer
    skill_lifecycle: SkillLifecycle
    skill_lab: SkillLab
    # skill_registry n'est PAS dans le Container : c'est un singleton module
    # historique (jarvis.capabilities.skills.registry.skill_registry).
    # Sa suppression viendra dans la session « éliminer skill_registry
    # singleton » — hors-périmètre étape 1.

    # ── Engine L2 — tracking & budget (déjà injectés) ──────────────────────
    tracker: UsageTracker
    budget: BudgetGuard

    # ── Engine L2 — session ────────────────────────────────────────────────
    session_manager: SessionManager

    # ── Engine L2 — agents ─────────────────────────────────────────────────
    agent: Agent
    voice_agent: Agent

    # ── Engine L2 — gateway ────────────────────────────────────────────────
    gateway: Gateway
    voice_gateway: Gateway

    # ── Engine L2 — background ─────────────────────────────────────────────
    notifications: NotificationQueue
    proactive_queue: ProactiveQueue
    approval_checker: ApprovalChecker
    worker: BackgroundWorker
    scheduler: Scheduler

    # ── Engine L2 — mission ────────────────────────────────────────────────
    capability_engine: CapabilityEngine
    reflexion: Reflexion
    orchestrator: ProjectOrchestrator

    # ── Engine L2 — proactive ──────────────────────────────────────────────
    initiative_store: InitiativeStore
    initiative_executor: InitiativeExecutor
    proactive_engine: ProactiveEngine
    curator: Curator
    command_center: CommandCenter


def build(
    settings: Settings | None = None,
    llm_override: LLMProvider | None = None,
) -> Container:
    """Construit le graphe d'objets dans l'ordre strict (CDC §C.1).

    Synchrone, sans réseau (GATE C6). Les async tasks (reindex FTS,
    vector_index, worker loop, scheduler, proactive_engine) sont
    lancées par les callers après build().

    `llm_override` : si fourni, remplace les trois providers LLM
    (`llm`, `background_llm`, `voice_llm`) par cette unique instance.
    Utilisé par `scripts/validation/smoke_runtime.py --fake-llm` pour
    injecter un `FakeLLMProvider` déterministe sans toucher au .env
    ni au factory. Démontre que l'injection LLM passe par le VRAI
    chemin du graphe — un override cassé fait planter `assert
    isinstance(llm, LLMProvider)` plus bas.
    """
    # ── 1. Settings ────────────────────────────────────────────────────────
    if settings is None:
        settings = _default_settings

    # ── 2. Bus ─────────────────────────────────────────────────────────────
    bus = EventBus()

    # ── 3. Providers L1 — Memory ───────────────────────────────────────────

    memory_dir = Path(settings.memory_dir)
    session_store = SessionStore(memory_dir / "sessions")
    memory_index = MemoryIndex(memory_dir)
    topic_store = TopicStore(memory_dir / "topics")
    user_prefs_path = memory_dir / "user_prefs.md"
    user_model_path = memory_dir / "user_model.md"
    vector_index = VectorIndex(index_dir=memory_dir / "vector_index")
    fts_index = FTSIndex(db_path=memory_dir / "fts_index.db")
    memory_kernel = MemoryKernel(memory_dir / "jarvis_memory.db")
    memory_mirror = MemoryMirror(memory_kernel, memory_dir / "mirror")

    # ── 4. Engine L2 — UsageTracker (créé tôt pour injection dans les providers) ─

    tracker = UsageTracker(on_usage_callback=None)

    # ── 4bis. Providers L1 — LLM ───────────────────────────────────────────

    if llm_override is not None:
        llm = llm_override
        background_llm = llm_override
        voice_llm: LLMProvider = llm_override
    else:
        llm = get_llm_provider(tracker=tracker)
        background_llm = create_background_llm(tracker=tracker)
        voice_llm = (
            get_llm_provider(tracker=tracker)
            if settings.llm_provider == "local"
            else AnthropicProvider(
                model=settings.voice_anthropic_model, max_tokens=1024, tracker=tracker
            )
        )

    # ── 4ter. Providers L1 — TTS (singleton module-level — set_tracker post-construction) ─

    tts_engine.set_tracker(tracker)

    memory_ingest = MemoryIngest(kernel=memory_kernel, llm=background_llm, bus=bus)
    user_model = UserModel(llm=background_llm, model_path=user_model_path)
    cross_recall = CrossSessionRecall(
        llm=background_llm, fts_index=fts_index, vector_index=vector_index
    )
    consolidation = ConsolidationAgent(
        llm=background_llm,
        memory_index=memory_index,
        topic_store=topic_store,
        memory_ingest=None,  # JAMAIS branché — choix d'archi (CDC §3 AutoDream micro).
    )
    _deep_ingest = memory_ingest if settings.ingest_deep_enabled else None

    auto_dream = AutoDream(
        llm=background_llm,
        prefs_path=user_prefs_path,
        sessions_dir=memory_dir / "sessions",
        memory_ingest=_deep_ingest,
        mirror=memory_mirror,
    )

    # ── 5. Capabilities L1 — Skill registry + Tools ─────────────────────────

    skill_registry.reload()

    _root = CONFIG_DIR.parent  # PROJECT_ROOT
    _google_creds = (_root / settings.google_credentials_path).resolve()
    _gmail_token = (_root / "config/google_gmail_token.json").resolve()
    _calendar_token = (_root / settings.google_token_path).resolve()
    allowed_roots = [Path(r).expanduser().resolve() for r in settings.file_search_roots]

    calendar_list_tool = CalendarListTool(
        credentials_path=_google_creds, token_path=_calendar_token
    )
    notion_tasks_tool = NotionTasksTool()

    tool_registry = ToolRegistry()
    tool_registry.register(
        WeatherTool(),
        BrowserTool(),
        VisionTool(visual_memory=_visual_memory),
        ReadFileTool(allowed_roots=allowed_roots),
        FindFilesTool(allowed_roots=allowed_roots),
        CLIRunnerTool(whitelist_path=Path(settings.cli_whitelist_path)),
        ExecuteCLITool(),
        calendar_list_tool,
        CalendarCreateTool(credentials_path=_google_creds, token_path=_calendar_token),
        notion_tasks_tool,
        MemoryTopicWriteTool(vector_index=vector_index),
        MemoryLoadTopicTool(topic_store=topic_store),
        MemorySearchTool(vector_index=vector_index),
        SpotifyTool(),
        GmailListTool(credentials_path=_google_creds, token_path=_gmail_token),
        ExecutePresetTool(tool_registry=tool_registry, tts_engine=tts_engine),
        CrossSessionRecallTool(fts_index=fts_index, vector_index=vector_index),
    )
    tool_registry.replace_skill_tools(*skill_registry.get_all_tools())

    # ── 6. Engine L2 — budget (tracker créé en section 4 ; two-phase setup) ─

    notifications = NotificationQueue()
    proactive_queue = ProactiveQueue()

    # ShowViewTool dépend de proactive_queue, donc enregistré après.
    tool_registry.register(ShowViewTool(broadcast_event=proactive_queue.broadcast_event))

    budget = BudgetGuard(
        settings=settings,
        tracker=tracker,
        bus=bus,
    )
    tracker.set_on_usage_callback(_make_budget_callback(budget))

    # ── 7. Engine L2 — session ─────────────────────────────────────────────

    session_manager = SessionManager(store=session_store)

    # ── 8. Engine L2 — Skills (Lab + Lifecycle + Synth) ────────────────────

    skill_synthesizer = SkillSynthesizer(llm=llm)
    skill_lifecycle = SkillLifecycle(db_path=memory_dir / "jarvis_memory.db")
    skill_lab = SkillLab(
        kernel=memory_kernel,
        lifecycle=skill_lifecycle,
        synthesizer=skill_synthesizer,
        registry_reload=skill_registry.reload,
    )
    tool_registry.register(
        SkillCreateTool(lab=skill_lab),
        SkillImproveTool(synthesizer=skill_synthesizer),
        SkillListTool(),
    )

    # ── 9. Engine L2 — Capability Engine ───────────────────────────────────

    _whitelist = Whitelist.load(CONFIG_DIR / "permissions.yaml")
    capability_engine = CapabilityEngine(
        kernel=memory_kernel,
        lab=skill_lab,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        whitelist=_whitelist,
        auto_install_enabled=settings.auto_install_whitelisted_enabled,
    )
    tool_registry.register(ReportMissingCapabilityTool(engine=capability_engine))

    # ── 10. Engine L2 — Agents ─────────────────────────────────────────────

    agent = Agent(
        settings=settings,
        llm=llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
        user_model_path=user_model_path,
    )
    voice_agent = Agent(
        settings=settings,
        llm=voice_llm,
        memory_index=memory_index,
        topic_store=topic_store,
        tool_registry=tool_registry,
        user_prefs_path=user_prefs_path,
        skill_registry=skill_registry,
        user_model_path=user_model_path,
    )

    # SpawnSubagentTool référence agent → enregistré après création.

    tool_registry.register(
        SpawnSubagentTool(agent=agent),
        ScriptRPCTool(
            tool_registry=tool_registry,
            workspace_path=str(memory_dir / "rpc_workspace"),
        ),
    )

    # ── 11. Engine L2 — Background ─────────────────────────────────────────

    approval_checker = ApprovalChecker(broadcast_event=proactive_queue.broadcast_event)
    worker = BackgroundWorker(
        llm=llm,
        notifications=notifications,
        tool_registry=tool_registry,
        bus=bus,
    )

    # ── 12. Engine L2 — Mission (orchestrator + reflexion) ─────────────────

    reflexion = Reflexion(llm=background_llm, kernel=memory_kernel, memory_ingest=memory_ingest)
    orchestrator = ProjectOrchestrator(
        broadcast_event=proactive_queue.broadcast_event,
        store=ProjectStore(),
        manager=ProjectManager(llm=voice_llm),
        worker_llm=voice_llm,
        budget_guard=budget,
        reflexion=reflexion,
        bus=bus,
    )

    # ── 13. Engine L2 — Gateway ────────────────────────────────────────────

    gateway = Gateway(
        session_manager=session_manager,
        agent=agent,
        notifications=notifications,
        worker=worker,
        recall=cross_recall,
    )
    voice_gateway = Gateway(
        session_manager=session_manager,
        agent=voice_agent,
        notifications=notifications,
        worker=worker,
        recall=cross_recall,
    )

    # ── 14. Engine L2 — Proactive (initiatives + curator + command center) ─

    initiative_store = InitiativeStore()
    initiative_executor = InitiativeExecutor(
        store=initiative_store,
        broadcast_event=proactive_queue.broadcast_event,
        orchestrator=orchestrator,
        approval_checker=approval_checker,
        budget_guard=budget,
        send_gmail_draft=send_gmail_draft,
    )
    curator = Curator(
        kernel=memory_kernel,
        skill_lifecycle=skill_lifecycle,
        initiative_store=initiative_store,
        budget_guard=budget,
        reports_dir=memory_dir / "curator_reports",
    )
    command_center = CommandCenter(
        initiative_store=initiative_store,
        project_store=orchestrator._store,
        budget_guard=budget,
        skill_lifecycle=skill_lifecycle,
    )
    proactive_engine = ProactiveEngine(
        notification_queue=notifications,
        broadcast_event=proactive_queue.broadcast_event,
        builder=ContextBuilder(
            calendar_tool=calendar_list_tool,
            notion_tool=notion_tasks_tool,
        ),
        generator=InitiativeGenerator(llm=background_llm),
        store=initiative_store,
        interval_minutes=30,
    )

    # ── 15. Engine L2 — Scheduler ──────────────────────────────────────────

    scheduler = Scheduler(
        proactive=proactive_queue,
        auto_dream=auto_dream,
        calendar_tool=calendar_list_tool,
        settings=settings,
        notion_tool=notion_tasks_tool,
        skill_lab=skill_lab,
        curator=curator,
    )

    # ── 16. Câblage des événements (Phase D — kernel.events.bus) ───────────
    # Les abonnements sont EXPLICITES ici (pas d'auto-découverte). Chaque
    # paire (Event → handler) est documentée dans docs/architecture/events.md.
    _wire_events(
        bus=bus,
        proactive_queue=proactive_queue,
        notifications=notifications,
        reflexion=reflexion,
        project_store=orchestrator._store,
    )

    # ── 17. Conformité runtime des Protocols (GATE F1bis-b) ─────────────────
    # Vérifie au boot que les implémentations exposent bien les méthodes
    # déclarées par les Protocols `@runtime_checkable`. Les signatures
    # restent vérifiées par mypy (cf. tests/unit/kernel/test_contracts_conformance.py).
    from jarvis.kernel import contracts as _contracts

    assert isinstance(llm, _contracts.LLMProvider), "llm: LLMProvider Protocol non respecté"
    assert isinstance(background_llm, _contracts.LLMProvider), (
        "background_llm: LLMProvider Protocol non respecté"
    )
    assert isinstance(voice_llm, _contracts.LLMProvider), (
        "voice_llm: LLMProvider Protocol non respecté"
    )
    assert isinstance(tracker, _contracts.UsageTracker), (
        "tracker: UsageTracker Protocol non respecté"
    )

    return Container(
        settings=settings,
        bus=bus,
        # Providers L1 — Memory
        session_store=session_store,
        memory_index=memory_index,
        topic_store=topic_store,
        vector_index=vector_index,
        fts_index=fts_index,
        memory_kernel=memory_kernel,
        memory_ingest=memory_ingest,
        memory_mirror=memory_mirror,
        user_model=user_model,
        # Providers L1 — LLM
        llm=llm,
        voice_llm=voice_llm,
        background_llm=background_llm,
        # Providers L1 — autres
        cross_recall=cross_recall,
        consolidation=consolidation,
        auto_dream=auto_dream,
        # Capabilities L1
        calendar_list_tool=calendar_list_tool,
        tool_registry=tool_registry,
        skill_synthesizer=skill_synthesizer,
        skill_lifecycle=skill_lifecycle,
        skill_lab=skill_lab,
        # Engine L2 — tracking & budget
        tracker=tracker,
        budget=budget,
        # Engine L2 — session
        session_manager=session_manager,
        # Engine L2 — agents
        agent=agent,
        voice_agent=voice_agent,
        # Engine L2 — gateway
        gateway=gateway,
        voice_gateway=voice_gateway,
        # Engine L2 — background
        notifications=notifications,
        proactive_queue=proactive_queue,
        approval_checker=approval_checker,
        worker=worker,
        scheduler=scheduler,
        # Engine L2 — mission
        capability_engine=capability_engine,
        reflexion=reflexion,
        orchestrator=orchestrator,
        # Engine L2 — proactive
        initiative_store=initiative_store,
        initiative_executor=initiative_executor,
        proactive_engine=proactive_engine,
        curator=curator,
        command_center=command_center,
    )


def _make_budget_callback(budget: BudgetGuard) -> Callable[[UsageEntry], None]:
    """Câble UsageTracker.track() → BudgetGuard.record() pour les coûts mission.

    Le câblage vit hors des deux modules engine.tracking et engine.budget,
    pour casser le cycle implicite intra-engine (cf. commit Phase C
    « Injecter on_usage_callback dans UsageTracker »).
    """

    def callback(entry: UsageEntry) -> None:
        if entry.cost_usd > 0 and entry.context and entry.context.startswith("mission:"):
            project_id = entry.context.split(":", 1)[1]
            budget.record(f"project:{project_id}", entry.cost_usd)

    return callback


# ════════════════════════════════════════════════════════════════════════════
# Câblage des événements — bus pub/sub kernel.events (CDC §6 D.1 point 2)
# ════════════════════════════════════════════════════════════════════════════
#
# Pour chaque type d'événement défini dans kernel/events.py, on enregistre ici
# le ou les handlers EXPLICITEMENT — pas d'auto-découverte. La table complète
# des paires (Émetteur → Event → Abonné) vit dans docs/architecture/events.md
# et doit y être tenue à jour à chaque ajout (gate D2).


def _wire_events(
    *,
    bus: EventBus,
    proactive_queue: ProactiveQueue,
    notifications: NotificationQueue,
    reflexion: Reflexion,
    project_store: ProjectStore,
) -> None:
    """Enregistre les handlers des 4 événements Phase D sur le bus.

    Émetteurs :
      - BudgetGuard.reserve()    → BudgetThresholdReached
      - WorkerAgent (fin de mission) → MissionCompleted
      - MemoryIngest.ingest()    → MemoryIngested
      - (toute couche basse)     → NotificationRequested

    Abonnés :
      - BudgetThresholdReached   → broadcast UI + notification user
      - MissionCompleted         → Reflexion.reflect(project)
      - MemoryIngested           → broadcast UI (compteur facts)
      - NotificationRequested    → broadcast UI ou queue notifications
    """

    async def _on_budget_threshold(event: BudgetThresholdReached) -> None:
        """Budget approche ou dépasse un seuil → broadcast UI + notif."""
        is_hard_stop = event.ratio >= 1.0
        proactive_queue.broadcast_event(
            {
                "type": "budget_hard_stop" if is_hard_stop else "budget_warning",
                "scope": event.scope,
                "ratio": event.ratio,
                "provider": event.provider,
            }
        )
        if is_hard_stop:
            notifications.add(f"Budget {event.scope} atteint — arrêt automatique.")

    async def _on_mission_completed(event: MissionCompleted) -> None:
        """Mission terminée → Reflexion produit une leçon depuis le project_store."""
        project = project_store.load_project(event.mission_id)
        if project is None:
            return
        try:
            await reflexion.reflect(project)
        except Exception as exc:  # noqa: BLE001 — la mission est close, on dégrade
            from loguru import logger as _lg

            _lg.warning("Reflexion handler échec", error=str(exc))

    async def _on_memory_ingested(event: MemoryIngested) -> None:
        """Fact ingéré → broadcast UI (compteur, surface mémoire)."""
        proactive_queue.broadcast_event(
            {
                "type": "memory_ingested",
                "event_id": event.event_id,
                "fact_count": event.fact_count,
                "source": event.source,
            }
        )

    async def _on_notification_requested(event: NotificationRequested) -> None:
        """Couche basse demande notification UI/canal.

        Channels reconnus :
          - "user" (défaut texte) : push dans NotificationQueue — sera
            injecté dans le prochain prompt système ou parlé.
          - "websocket" : forward le payload tel quel pour le dashboard.
        """
        if event.channel == "websocket":
            proactive_queue.broadcast_event(event.payload)
            return
        content = event.payload.get("content", "")
        if content:
            notifications.add(content)

    bus.subscribe(BudgetThresholdReached, _on_budget_threshold)
    bus.subscribe(MissionCompleted, _on_mission_completed)
    bus.subscribe(MemoryIngested, _on_memory_ingested)
    bus.subscribe(NotificationRequested, _on_notification_requested)
