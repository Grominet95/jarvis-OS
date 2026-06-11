"""
Vérifie si une action nécessite une approbation avant d'être exécutée.
Bloque en mode ASK jusqu'à la réponse de l'utilisateur (timeout 120s).
"""

from __future__ import annotations

import asyncio

from loguru import logger

# Phase F : le singleton vit en `jarvis.kernel.approval` pour permettre aux
# tools plugin de capabilities/ d'y accéder sans violer RÈGLE 2. Ces
# ré-exports gardent les call-sites historiques compatibles.
from jarvis.kernel.approval import get_approval_checker, set_approval_checker  # noqa: F401
from jarvis.kernel.approvals import ApprovalMode, approval_config


class ApprovalChecker:
    def __init__(self, broadcast_event: object) -> None:
        self._broadcast = broadcast_event
        self._pending: dict[str, asyncio.Future] = {}

    async def check(
        self,
        category: str,
        description: str,
        action_id: str,
    ) -> bool:
        """
        Retourne True si l'action est autorisée, False sinon.
        Bloque si mode = ASK jusqu'à réponse utilisateur (120s timeout).
        """
        mode = getattr(approval_config, category, ApprovalMode.ASK)

        if mode == ApprovalMode.ALWAYS:
            logger.debug(f"Approval AUTO: {category}")
            return True

        if mode == ApprovalMode.NEVER:
            logger.info(f"Approval DENIED: {category}")
            return False

        # Mode ASK
        logger.info(f"Approval REQUIRED: {category} — {description[:60]}")

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[action_id] = future

        self._broadcast(
            {
                "type": "approval_request",
                "action_id": action_id,
                "category": category,
                "description": description,
            }
        )

        try:
            result = await asyncio.wait_for(future, timeout=120.0)
            return result
        except TimeoutError:
            logger.warning(f"Approval timeout: {category} ({action_id})")
            self._pending.pop(action_id, None)
            return False

    def resolve(self, action_id: str, approved: bool) -> None:
        """Appelé par le endpoint HTTP quand l'utilisateur répond."""
        future = self._pending.pop(action_id, None)
        if future and not future.done():
            future.set_result(approved)
            logger.info(
                f"Approval resolved: {action_id} → {'approved' if approved else 'rejected'}"
            )
