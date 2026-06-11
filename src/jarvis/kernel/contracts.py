"""Protocols — contrats structurels entre couches (CDC §A.1.3).

Ce module est LE document d'architecture du projet : il déclare les
interfaces que doivent respecter les providers, capabilities et le bus
de canaux. Aucune logique métier ici, uniquement des signatures.

Chaque Protocol est **calqué fidèlement sur l'implémentation existante**
(§A.1.3 — "ne rien inventer") :
- LLMProvider       ← llm/base.py
- MemoryStore       ← memory/kernel.py
- SessionStore      ← memory/sessions.py
- TopicStore        ← memory/topics.py
- MemoryIndex       ← memory/index.py
- ToolRegistry      ← tools/registry.py
- Tool              ← tools/base.py
- SkillRegistry     ← skills/registry.py
- Skill             ← skills/base.py
- Channel           ← channels/base.py (ChannelAdapter)
- NotificationSink  ← background/notifications.py (NotificationQueue + ProactiveQueue)
- Collector         ← proactive/collectors/base.py (CollectorBase)

Décoration @runtime_checkable activée pour la GATE F.1bis-b (asserts
isinstance au boot, dans bootstrap.build()).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from jarvis.kernel.schemas import (
    ContextItem,
    Event,
    Fact,
    FactObservation,
    FactRelation,
    FactStatus,
    UsageEntry,
)

# ════════════════════════════════════════════════════════════════════════════
# L1 — Providers
# ════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class LLMProvider(Protocol):
    """Interface commune à tous les providers LLM (cf. llm/base.py)."""

    supports_tools: bool

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        """Retourne la réponse complète ou un itérateur de chunks si stream=True."""
        ...

    async def tool_loop(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Awaitable[str]],
        context: str = "",
    ) -> str:
        """Exécute la boucle tool use et retourne le texte final."""
        ...

    async def health_check(self) -> bool:
        """Vérifie que le provider est joignable."""
        ...


@runtime_checkable
class MemoryStore(Protocol):
    """Couche d'accès SQLite source de vérité unique (cf. memory/kernel.py)."""

    # Events
    def log_event(
        self,
        type: str,  # noqa: A002 — nom imposé par le contrat memory §6.2
        source: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event: ...

    def get_event(self, event_id: str) -> Event | None: ...
    def count_events(self) -> int: ...

    # Facts
    def insert_fact(self, fact: Fact) -> None: ...
    def update_fact(self, fact: Fact) -> None: ...
    def get_fact(self, fact_id: str) -> Fact | None: ...

    def find_active_match(
        self,
        subject: str,
        predicate: str,
        category: str,
    ) -> Fact | None: ...

    def list_facts_by_status(self, status: FactStatus, limit: int | None = None) -> list[Fact]: ...

    def list_facts_by_category(self, category: str, limit: int | None = None) -> list[Fact]: ...

    def count_facts(self, status: FactStatus | None = None) -> int: ...

    # Observations & relations
    def record_observation(
        self,
        fact_id: str,
        event_id: str,
        observation_type: Any,  # noqa: ANN401 — ObservationType (kernel.schemas) ou str selon l'appelant
        confidence_delta: float,
    ) -> FactObservation: ...

    def list_observations(self, fact_id: str) -> list[FactObservation]: ...

    def link_facts(
        self,
        from_fact_id: str,
        to_fact_id: str,
        relation_type: Any,  # noqa: ANN401 — RelationType (kernel.schemas) ou str selon l'appelant
    ) -> FactRelation: ...

    def list_relations(self, fact_id: str) -> list[FactRelation]: ...

    # Recherche & correction
    def search_facts_fts(self, query: str, k: int = 10) -> list[tuple[Fact, float]]: ...
    def apply_correction(self, fact_id: str, new_object: str, event_id: str) -> Fact | None: ...


@runtime_checkable
class SessionStore(Protocol):
    """Stockage append-only des transcripts en JSONL (cf. memory/sessions.py)."""

    def load(self, session_id: str) -> list[dict]: ...
    def append(self, session_id: str, role: str, content: str) -> None: ...
    def list_recent(self, n: int = 20) -> list[Path]: ...
    def list_all(self) -> list[Path]: ...


@runtime_checkable
class TopicStore(Protocol):
    """Lecture/écriture des fichiers thématiques Markdown (cf. memory/topics.py)."""

    def list_all(self) -> list[str]: ...
    def load(self, filename: str) -> str: ...
    def load_all(self) -> dict[str, str]: ...
    def write(self, filename: str, content: str) -> None: ...
    def exists(self, filename: str) -> bool: ...


@runtime_checkable
class MemoryIndex(Protocol):
    """Lecture/écriture de MEMORY.md (cf. memory/index.py)."""

    def read(self) -> str: ...
    def add_pointer(self, section: str, key: str, filepath: str, description: str) -> None: ...


@runtime_checkable
class FTSIndex(Protocol):
    """Index full-text SQLite des sessions (cf. memory/search.py)."""

    async def add(self, doc_id: str, text: str) -> None: ...
    async def remove(self, doc_id: str) -> None: ...
    async def search(self, query: str, k: int = 5) -> list[dict]: ...
    async def count(self) -> int: ...
    async def is_empty(self) -> bool: ...


@runtime_checkable
class VectorIndex(Protocol):
    """Index vectoriel multilingue des topics + transcripts (cf. memory/search.py)."""

    async def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None: ...
    async def search(self, query: str, k: int = 5) -> list[dict]: ...
    async def persist(self) -> None: ...
    def is_empty(self) -> bool: ...


@runtime_checkable
class VisualMemory(Protocol):
    """Stockage + recherche des souvenirs visuels (cf. memory/visual_memory.py).

    Le module historique expose des fonctions au niveau module (`search`,
    `store`) ; le Protocol structural les expose comme attributs callables
    pour permettre l'injection du module (vu comme un namespace) dans
    les capabilities sans import direct.
    """

    async def search(self, query: str) -> list[str]: ...
    async def store(
        self, description: str, source: str, context: str = "", tags: list[str] | None = None
    ) -> None: ...


@runtime_checkable
class TTSEngine(Protocol):
    """Moteur de synthèse vocale (cf. providers/audio/tts.py)."""

    async def synthesize(self, text: str) -> bytes: ...


@runtime_checkable
class ApprovalChecker(Protocol):
    """Garde-fou approval gating (cf. engine/approval_checker.py).

    Phase F : utilisé par les tools `capabilities/tools/{subagent, fusion,
    printer}` qui doivent demander confirmation à l'utilisateur avant une
    action sensible (écriture de code, action externe, etc.). Le Protocol
    leur évite d'importer concrètement `engine.approval_checker`.
    """

    async def check(self, category: str, description: str, action_id: str) -> bool: ...


@runtime_checkable
class CapabilityEngine(Protocol):
    """Moteur de proposition de capacités manquantes (cf. engine/mission/
    capability_engine.py).

    Phase F : utilisé par `capabilities/tools/capability.py
    ReportMissingCapabilityTool` pour notifier le LLM qu'une capacité
    n'existe pas et déclencher une éventuelle proposition de skill.
    """

    async def detect_and_propose(
        self,
        description: str,
        example_input: str | None = None,
    ) -> Any: ...  # noqa: ANN401 — type ResolutionResult défini en engine/mission


# ════════════════════════════════════════════════════════════════════════════
# L1 — Capabilities (tools, skills)
# ════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class Tool(Protocol):
    """Interface des outils Jarvis (cf. tools/base.py)."""

    name: str
    description: str
    input_schema: dict

    def to_claude_schema(self) -> dict: ...
    # ToolResult est défini dans tools/base.py (couche L1) — ne remonte pas en kernel.
    async def execute(self, **kwargs: object) -> Any: ...  # noqa: ANN401 — ToolResult local à tools/


@runtime_checkable
class ToolRegistry(Protocol):
    """Registre central des outils (cf. tools/registry.py)."""

    def register(self, *tools: Tool) -> None: ...
    def replace_skill_tools(self, *tools: Tool) -> None: ...
    def has_tools(self) -> bool: ...
    def schemas(self) -> list[dict]: ...
    def core_schemas(self) -> list[dict]: ...
    async def call(self, name: str, inputs: dict) -> Any: ...  # noqa: ANN401 — ToolResult local
    async def call_str(self, name: str, inputs: dict) -> str: ...


@runtime_checkable
class Skill(Protocol):
    """Interface d'un skill installé (cf. skills/base.py SkillBase)."""

    SYSTEM_PROMPT: str
    name: str
    label: str
    version: str
    author: str
    description: str
    tags: list[str]
    metadata: dict

    def get_system_prompt(self) -> str: ...
    def get_tools(self) -> list[Tool]: ...
    def is_active(self) -> bool: ...
    def is_preset(self) -> bool: ...


@runtime_checkable
class SkillRegistry(Protocol):
    """Registre central des skills (cf. skills/registry.py)."""

    def load_all(self) -> None: ...
    def reload(self) -> None: ...
    def get(self, name: str) -> Skill | None: ...
    def list_installed(self) -> list[dict]: ...
    def get_all(self) -> dict[str, Skill]: ...
    def get_all_tools(self) -> list[Tool]: ...
    def get_presets(self) -> dict[str, Skill]: ...
    def get_preset(self, name: str) -> Skill | None: ...
    def find_preset_by_trigger(self, text: str) -> Skill | None: ...
    def get_combined_system_prompt(self) -> str: ...


# ════════════════════════════════════════════════════════════════════════════
# L1 — Channels, notifications, collectors
# ════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class Channel(Protocol):
    """Interface des canaux de messagerie (cf. channels/base.py ChannelAdapter)."""

    @property
    def platform(self) -> Any: ...  # noqa: ANN401 — Platform (StrEnum) local à channels/

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, reply: str, target: Any) -> None: ...  # noqa: ANN401 — MessageTarget local
    # IncomingMessage est local à channels/ — kernel ne le voit pas typé.
    def set_dispatch(self, callback: Callable[[Any], Awaitable[None]]) -> None: ...


@runtime_checkable
class NotificationSink(Protocol):
    """Réceptacle de notifications côté UI/clients (cf. background/notifications.py).

    Calqué sur ProactiveQueue : interface de broadcast aux abonnés WebSocket.
    """

    def subscribe(self) -> asyncio.Queue[str | dict]: ...
    def unsubscribe(self, q: asyncio.Queue[str | dict]) -> None: ...
    def broadcast(self, content: str) -> None: ...
    def broadcast_event(self, event: dict) -> None: ...


@runtime_checkable
class Collector(Protocol):
    """Collecteur d'éléments de contexte (cf. proactive/collectors/base.py)."""

    name: str

    async def collect(self) -> list[ContextItem]: ...


@runtime_checkable
class UsageTracker(Protocol):
    """Tracker de consommation API/TTS (cf. engine/tracking.py).

    Contract minimal utilisé par les providers L1 (LLM + audio) pour pousser
    les coûts vers le moteur de tracking sans dépendre concrètement de
    `engine.tracking.UsageTracker` (CYCLE 1 — providers→engine = 0).
    """

    def track(self, entry: UsageEntry) -> None: ...


# ════════════════════════════════════════════════════════════════════════════
# L1 — Memory operations (Phase D — CYCLE 4 / engine ne dépend que de kernel)
# ════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class CrossSessionRecall(Protocol):
    """Rappel transversal de sessions (cf. providers/memory/consolidation.py).

    Utilisé par `engine/gateway.py` au premier message d'une session pour
    injecter un résumé des échanges passés pertinents.
    """

    async def recall(self, query: str, k: int = 8) -> str | None: ...


@runtime_checkable
class MemoryIngest(Protocol):
    """Ingestion d'événements/faits dans la mémoire (cf. providers/memory/ingest.py).

    Utilisé par `engine/mission/reflexion.py` après une mission pour écrire
    les leçons apprises sous forme d'événement + facts extraits.
    """

    async def ingest(
        self,
        content: str,
        source: str = ...,
        event_type: str = ...,
        metadata: dict[str, Any] | None = ...,
    ) -> Any: ...  # noqa: ANN401 — IngestResult défini en providers/memory/ingest.py


@runtime_checkable
class AutoDreamer(Protocol):
    """Analyse nocturne en profondeur (cf. providers/memory/auto_dream.py).

    Utilisé par `engine/background/scheduler.py` pour planifier la passe
    AutoDream deep à 3h du matin.
    """

    async def deep_analyze(self) -> None: ...


# ════════════════════════════════════════════════════════════════════════════
# L1 — Skills lifecycle (Phase D — proactive/curator+command_center)
# ════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class SkillLifecycle(Protocol):
    """Cycle de vie des skills candidats (cf. capabilities/skills/lifecycle.py).

    Utilisé par `engine/proactive/curator.py` et `command_center.py` pour
    consulter le statut des candidates (sandbox, promotion, archivage).
    """

    def list_all(self) -> list[Any]: ...  # noqa: ANN401 — SkillRecord (kernel.schemas)
    def list_by_status(self, status: Any) -> list[Any]: ...  # noqa: ANN401 — SkillStatus enum
    def get(self, name: str) -> Any | None: ...  # noqa: ANN401 — SkillRecord (kernel.schemas)


# ════════════════════════════════════════════════════════════════════════════
# L1 — Tools spécifiques injectés cross-couche (cf. background/scheduler.py)
# ════════════════════════════════════════════════════════════════════════════
#
# Le Tool Protocol générique (au-dessus) ne convient pas pour les call-sites
# qui ont besoin d'arguments précis (days_ahead, etc.). Plutôt qu'imposer
# de typer `tool: object` côté engine, on déclare ici les contrats minimaux.


@runtime_checkable
class CalendarReadTool(Protocol):
    """Lecture d'agenda (cf. capabilities/tools/calendar.py CalendarListTool).

    Utilisé par `engine/background/scheduler.py` pour les rappels J/J+1.
    """

    async def execute(self, days_ahead: int = ..., **kwargs: object) -> Any: ...  # noqa: ANN401


@runtime_checkable
class NotionReadTool(Protocol):
    """Lecture des tâches Notion (cf. capabilities/tools/notion.py NotionTasksTool).

    Utilisé par `engine/background/scheduler.py` pour le briefing matinal.
    """

    async def execute(self, **kwargs: object) -> Any: ...  # noqa: ANN401


@runtime_checkable
class SkillLab(Protocol):
    """Sandbox d'essai des skills candidats (cf. capabilities/skills/lab.py).

    Utilisé par `engine/mission/capability_engine.py` pour générer puis
    sandboxer une candidate quand le LLM signale une capacité manquante,
    et par `engine/background/scheduler.py` pour les passes nocturnes.
    """

    async def scan_kernel(self) -> Any: ...  # noqa: ANN401 — LabScanResult (capabilities/skills/lab.py)
    async def propose_from_trajectory(
        self, trajectory: dict, source_event_id: str | None = ...
    ) -> Any | None: ...  # noqa: ANN401 — SkillRecord (capabilities/skills/lifecycle.py)
