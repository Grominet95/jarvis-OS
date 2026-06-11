"""L2 — Engine : orchestration métier (RÈGLE 3 — n'importe que kernel).

Sous-packages :
- background/ — NotificationQueue, ProactiveQueue, BackgroundWorker, Scheduler.
- mission/    — ProjectOrchestrator, WorkerAgent, Reflexion, Verifier.
- proactive/  — ProactiveEngine, InitiativeStore, Curator, CommandCenter.

Modules :
- agent.py     — Agent (prompt + stream LLM).
- gateway.py   — Gateway (point d'entrée chat).
- budget.py    — BudgetGuard.
- tracking.py  — UsageTracker.
- session.py   — SessionManager.

L'API publique de chaque module/sous-package est explicite via `__all__`
là où c'est consommé. Le sous-graphe est typiquement câblé par
`bootstrap.build()` ; les call-sites externes vont chercher les types
via leurs Protocols kernel.contracts.
"""

from __future__ import annotations

__all__: list[str] = []
