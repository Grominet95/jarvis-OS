"""kernel — L0 de l'architecture jarvis-OS.

Cette couche ne dépend de RIEN du projet (stdlib + pydantic uniquement).
Toutes les autres couches dépendent de kernel par contrat.

Voir :
- CDC §2.1 (arborescence cible)
- CDC §2.2 (règles d'or)

Sous-modules :
- errors    — hiérarchie d'exceptions Jarvis
- vocab     — vocabulaires fermés (prédicats, catégories, niveaux d'accès et d'autonomie)
- schemas   — modèles de données partagés inter-couches
- contracts — Protocols (LLMProvider, MemoryStore, ToolRegistry, …)
- events    — bus d'événements asyncio pub/sub
- settings  — pydantic-settings (Settings du projet)

API publique (`__all__`) — pour `from jarvis.kernel import X` :
  Settings + settings (settings.py)
  EventBus + bus (events.py)
  Protocols (contracts.py)
"""

from __future__ import annotations

from jarvis.kernel.contracts import (
    AutoDreamer,
    CalendarReadTool,
    Channel,
    Collector,
    CrossSessionRecall,
    LLMProvider,
    MemoryIndex,
    MemoryIngest,
    MemoryStore,
    NotificationSink,
    NotionReadTool,
    SessionStore,
    Skill,
    SkillLab,
    SkillLifecycle,
    SkillRegistry,
    Tool,
    ToolRegistry,
    TopicStore,
    UsageTracker,
)
from jarvis.kernel.events import EventBus, bus
from jarvis.kernel.settings import Settings, settings

__all__ = [
    "AutoDreamer",
    "CalendarReadTool",
    "Channel",
    "Collector",
    "CrossSessionRecall",
    "EventBus",
    "LLMProvider",
    "MemoryIndex",
    "MemoryIngest",
    "MemoryStore",
    "NotificationSink",
    "NotionReadTool",
    "SessionStore",
    "Settings",
    "Skill",
    "SkillLab",
    "SkillLifecycle",
    "SkillRegistry",
    "Tool",
    "ToolRegistry",
    "TopicStore",
    "UsageTracker",
    "bus",
    "settings",
]
