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

from kernel.schemas import (
    ContextItem,
    Event,
    Fact,
    FactObservation,
    FactRelation,
    FactStatus,
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

    def list_facts_by_status(
        self, status: FactStatus, limit: int | None = None
    ) -> list[Fact]: ...

    def list_facts_by_category(
        self, category: str, limit: int | None = None
    ) -> list[Fact]: ...

    def count_facts(self, status: FactStatus | None = None) -> int: ...

    # Observations & relations
    def record_observation(
        self,
        fact_id: str,
        event_id: str,
        observation_type: Any,
        confidence_delta: float,
    ) -> FactObservation: ...

    def list_observations(self, fact_id: str) -> list[FactObservation]: ...

    def link_facts(
        self,
        from_fact_id: str,
        to_fact_id: str,
        relation_type: Any,
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
    async def execute(self, **kwargs: object) -> Any: ...  # ToolResult — type local à tools/


@runtime_checkable
class ToolRegistry(Protocol):
    """Registre central des outils (cf. tools/registry.py)."""

    def register(self, *tools: Tool) -> None: ...
    def replace_skill_tools(self, *tools: Tool) -> None: ...
    def has_tools(self) -> bool: ...
    def schemas(self) -> list[dict]: ...
    def core_schemas(self) -> list[dict]: ...
    async def call(self, name: str, inputs: dict) -> Any: ...  # ToolResult
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
    def platform(self) -> Any: ...  # Platform StrEnum — type local à channels/

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, reply: str, target: Any) -> None: ...  # MessageTarget
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
