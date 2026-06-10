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
"""

from __future__ import annotations
