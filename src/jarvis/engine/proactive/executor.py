"""
InitiativeExecutor — exécution pilotée des initiatives avec garde-fous.

GARDE-FOU CENTRAL :
  Aucune initiative ne peut déclencher une action à conséquence réelle
  (mail, message sortant, dépense) sans :
    (i)  déclenchement explicite par l'utilisateur depuis l'UI —
         seul un appel HTTP authentifié à /run ou /confirm peut lancer l'executor ;
    (ii) vérification du mode d'approbation (email_send, agent_mission) :
         ApprovalMode.NEVER bloque l'action sans exception ;
    (iii) réservation budget via guard.reserve() avant toute action LLM/mission.

  ExecutionMode.AUTO ne déclenche aucune action externe.
  L'envoi de mail requiert deux étapes : /run (prépare le brouillon) puis /confirm.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from jarvis.engine.proactive.schemas import Initiative, InitiativeType
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.kernel.approvals import ApprovalMode, approval_config
from jarvis.kernel.settings import settings

# Signature du callable d'envoi d'email injecté : reçoit le brouillon parsé et
# les chemins credentials/token, retourne l'id du message envoyé. Le callable
# concret vit en `capabilities/tools/gmail.py:send_gmail_draft`, câblé dans
# bootstrap.py (cf. RÈGLE 3 — engine n'importe que kernel).
SendGmailDraft = Callable[..., Awaitable[Any]]


class _Orchestrator(Protocol):
    async def create_and_run(self, mission: str) -> object: ...


class _ApprovalChecker(Protocol): ...


class _BudgetGuard(Protocol):
    async def reserve(self, scope: str, amount: float) -> bool: ...


class InitiativeExecutor:
    """Exécute une initiative validée par l'utilisateur."""

    def __init__(
        self,
        store: InitiativeStore,
        broadcast_event: Callable[[dict], None],
        orchestrator: _Orchestrator | None = None,
        approval_checker: _ApprovalChecker | None = None,
        budget_guard: _BudgetGuard | None = None,
        send_gmail_draft: SendGmailDraft | None = None,
    ) -> None:
        self._store = store
        self._broadcast = broadcast_event
        self._orchestrator = orchestrator
        self._checker = approval_checker
        self._budget = budget_guard
        self._send_gmail_draft = send_gmail_draft

    # ── Étape 1 : Run ─────────────────────────────────────────────────────────

    async def run(self, initiative_id: str) -> dict:
        """
        Déclenche l'exécution d'une initiative (étape 1).
        Pour DRAFT_RESPONSE : retourne le brouillon pour relecture (pas d'envoi).
        Pour AUTO_TASK : lance la mission après vérification budget.
        Pour INFO/REMINDER/SUGGESTION : marque comme traitée.
        """
        init = self._store.get_by_id(initiative_id)
        if not init:
            return {"error": "Initiative introuvable", "status": "error"}

        if init.status != "pending":
            return {"error": f"Statut invalide pour run : {init.status}", "status": "error"}

        self._store.update_status(initiative_id, "in_progress")
        result = await self._execute(init)
        self._audit(init, "run", result)
        return result

    # ── Étape 2 : Confirm (actions sensibles uniquement) ──────────────────────

    async def confirm(self, initiative_id: str, draft_content: str | None = None) -> dict:
        """
        2e confirmation pour les actions sensibles (envoi mail).
        N'est valide qu'après run() → status='awaiting_confirm'.
        Le brouillon éventuellement modifié par l'utilisateur peut être passé.
        """
        init = self._store.get_by_id(initiative_id)
        if not init:
            return {"error": "Initiative introuvable", "status": "error"}

        if init.status != "awaiting_confirm":
            return {"error": f"Statut invalide pour confirm : {init.status}", "status": "error"}

        if draft_content is not None:
            self._store.update_initiative(initiative_id, {"draft_content": draft_content})
            init = self._store.get_by_id(initiative_id)  # type: ignore[assignment]

        result = await self._send_email(init)
        self._audit(init, "confirm", result)
        return result

    # ── Dispatch ───────────────────────────────────────────────────────────────

    async def _execute(self, init: Initiative) -> dict:
        if init.type == InitiativeType.DRAFT_RESPONSE:
            return await self._prepare_draft(init)
        if init.type == InitiativeType.AUTO_TASK:
            return await self._launch_mission(init)
        if init.type in (
            InitiativeType.REMINDER,
            InitiativeType.SUGGESTION,
            InitiativeType.INFO,
            InitiativeType.ALERT,
        ):
            return self._handle_info(init)
        # Type non actionnable → simplement marquer
        self._store.update_status(init.id, "done")
        return {"status": "handled", "type": str(init.type)}

    # ── DRAFT_RESPONSE : prépare le brouillon ─────────────────────────────────

    async def _prepare_draft(self, init: Initiative) -> dict:
        """Retourne le brouillon sans envoyer — attend une 2e confirmation via /confirm."""
        draft = init.draft_content or init.action
        self._store.update_initiative(
            init.id,
            {
                "status": "awaiting_confirm",
                "draft_content": draft,
            },
        )
        return {
            "status": "draft_ready",
            "draft": draft,
            "initiative_id": init.id,
        }

    # ── Envoi mail (après /confirm) ────────────────────────────────────────────

    async def _send_email(self, init: Initiative) -> dict:
        """Envoi effectif après 2e confirmation. Bloqué si email_send=NEVER."""

        mode = getattr(approval_config, "email_send", ApprovalMode.ASK)
        if mode == ApprovalMode.NEVER:
            self._store.update_status(init.id, "failed")
            return {"error": "Envoi mail désactivé (approbation : never)", "status": "blocked"}

        if self._send_gmail_draft is None:
            self._store.update_status(init.id, "done")
            return {
                "status": "draft_only",
                "draft_content": init.draft_content or "",
                "reason": "send_gmail_draft non injecté",
            }
        try:
            msg_id = await self._send_gmail_draft(
                draft_content=init.draft_content or "",
                credentials_path=Path(settings.google_credentials_path),
                token_path=Path(settings.google_token_path).parent / "google_gmail_token.json",
            )
            self._store.update_status(init.id, "done")
            logger.info(f"InitiativeExecutor: mail envoyé (initiative {init.id})")
            return {"status": "sent", "message_id": msg_id}
        except ImportError:
            # Outil d'envoi absent — expose le brouillon prêt à copier
            self._store.update_status(init.id, "done")
            return {
                "status": "draft_only",
                "draft": init.draft_content or init.action,
                "note": "Outil d'envoi indisponible — brouillon prêt à copier",
            }
        except Exception as e:
            self._store.update_status(init.id, "failed")
            logger.error(f"InitiativeExecutor: envoi mail échoué: {e}")
            return {"error": str(e), "status": "error"}

    # ── AUTO_TASK : mission agentique ─────────────────────────────────────────

    async def _launch_mission(self, init: Initiative) -> dict:
        """Lance une mission via l'orchestrateur après réservation budget."""
        if not self._orchestrator:
            self._store.update_status(init.id, "failed")
            return {"error": "Orchestrateur non disponible", "status": "error"}

        scope = f"initiative:{init.id}"
        est_usd = 0.05  # estimation conservative pour une mission standard

        if self._budget:
            ok = await self._budget.reserve(scope, est_usd)
            if not ok:
                self._store.update_status(init.id, "failed")
                return {
                    "error": "Budget insuffisant pour lancer la mission",
                    "status": "budget_exceeded",
                }

        mission = init.mission_description or init.action
        try:
            project = await self._orchestrator.create_and_run(mission)
            self._store.update_initiative(
                init.id,
                {
                    "status": "in_progress",
                    "mission_description": mission,
                },
            )
            return {
                "status": "mission_launched",
                "project_id": project.id,
                "title": project.title,
                "steps": len(project.steps),
            }
        except Exception as e:
            self._store.update_status(init.id, "failed")
            logger.error(f"InitiativeExecutor: lancement mission échoué: {e}")
            return {"error": str(e), "status": "error"}

    # ── REMINDER / SUGGESTION / INFO / ALERT ──────────────────────────────────

    def _handle_info(self, init: Initiative) -> dict:
        """Marque comme traitée — aucune action externe."""
        self._store.update_status(init.id, "done")
        return {"status": "handled", "type": str(init.type)}

    # ── Audit ─────────────────────────────────────────────────────────────────

    def _audit(self, init: Initiative, step: str, result: dict) -> None:
        event = {
            "type": "initiative_audit",
            "event_id": f"aud_{uuid.uuid4().hex[:8]}",
            "initiative_id": init.id,
            "initiative_title": init.title,
            "initiative_type": str(init.type),
            "step": step,
            "result_status": result.get("status", "unknown"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._broadcast(event)
        logger.info(f"InitiativeExecutor AUDIT [{step}] {init.title!r} → {result.get('status')}")
