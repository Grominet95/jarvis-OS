from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from loguru import logger

from background.notifications import NotificationQueue
from background.worker import BackgroundWorker
from core.agent import Agent
from core.router import RouteEnum, SpeedRouter
from core.session import Session, SessionManager

if TYPE_CHECKING:
    from memory.consolidation import CrossSessionRecall

# Import paresseux de l'orchestrateur — évite les imports circulaires
def _get_orchestrator(app_state):  # type: ignore[return]
    return getattr(app_state, "orchestrator", None)


# ── Singleton tool registry (pour les presets) ───────────────────────────────
_tool_registry_instance = None


def set_tool_registry(registry) -> None:
    global _tool_registry_instance
    _tool_registry_instance = registry


def get_tool_registry():
    return _tool_registry_instance

_FALLBACK = "Désolé chef, j'ai eu un souci — je regarde."


class Gateway:
    """Point d'entrée unique. Gère session, notifications, routing et agent.

    Flux double-passe pour les outils (CF) :
    1. Premier appel LLM streamé : détection du tag + ack text + capture tool_use.
    2. Exécution parallèle des outils (overlap avec TTS de l'ack).
    3. Second appel LLM (synthesize) : résultats injectés dans le contexte,
       LLM produit une réponse naturelle — pas de dump brut.
    L'utilisateur reçoit : ack streamé → synthèse streamée dans la même bulle.
    [BG] : le worker est soumis par le WebSocket après "done".
    """

    def __init__(
        self,
        session_manager: SessionManager,
        agent: Agent,
        notifications: NotificationQueue,
        worker: BackgroundWorker,
        recall: CrossSessionRecall | None = None,
    ) -> None:
        self._sessions = session_manager
        self._agent = agent
        self._notifications = notifications
        self._worker = worker
        self._recall = recall

    async def handle(
        self,
        message: str,
        session_id: str | None = None,
        stream: bool = True,
    ) -> tuple[Session, RouteEnum, str | AsyncIterator[str]]:
        session = self._sessions.get_or_create(session_id)
        logger.info("Gateway handle", session_id=str(session.id))

        pending = self._notifications.drain()
        notif_texts = [n.content for n in pending] if pending else None
        if notif_texts:
            logger.info("Injecting notifications", count=len(notif_texts))

        # Rappel cross-session uniquement au premier message de la session
        recall_summary: str | None = None
        if self._recall is not None and not session.messages:
            try:
                recall_summary = await self._recall.recall(message)
                if recall_summary:
                    logger.debug("CrossSessionRecall injected", chars=len(recall_summary))
            except Exception as e:
                logger.warning("CrossSessionRecall failed", error=str(e))

        try:
            raw_stream, tool_capture = self._agent.start_routing_stream(
                session=session,
                user_message=message,
                notifications=notif_texts,
                recall_summary=recall_summary,
            )

            route, text_stream = await SpeedRouter.extract_route(raw_stream)
            logger.debug("Route detected", route=route.value)

            agent = self._agent
            notifications = self._notifications

            async def _pipe() -> AsyncIterator[str]:
                tool_task: asyncio.Task | None = None
                ack_text = ""  # Accumule le texte streamé avant les outils

                async for chunk in text_stream:
                    ack_text += chunk
                    yield chunk
                    # Dès que _stream_capturing peuple capture (content_block_stop tool_use),
                    # on démarre la task outil — elle tourne pendant que la voice WS fait du TTS.
                    if tool_task is None and tool_capture is not None and tool_capture.calls:
                        tool_task = asyncio.create_task(
                            agent.execute_captured_tools(tool_capture),
                            name="cf-tools",
                        )

                # Fallback : LLM sans préambule texte
                if tool_task is None and tool_capture is not None and tool_capture.calls:
                    tool_task = asyncio.create_task(
                        agent.execute_captured_tools(tool_capture),
                        name="cf-tools",
                    )

                # Second appel LLM pour synthétiser les résultats — avant "done"
                if tool_task is not None:
                    try:
                        results = await tool_task
                        logger.debug("CF tools done", names=[n for _, n, _ in tool_capture.calls])
                        if ack_text.strip():
                            yield " "
                        synth_stream = agent.synthesize(session, ack_text, tool_capture, results)
                        _, clean_synth = await SpeedRouter.extract_route(synth_stream)
                        async for chunk in clean_synth:
                            yield chunk
                    except Exception as e:
                        logger.error("CF tool error", error=str(e))
                        notifications.add(f"Outil échoué : {e}")

            return await self._finalize(session, route, _pipe(), stream)

        except Exception as e:
            logger.opt(exception=True).error(
                "Gateway error", error=type(e).__name__, detail=str(e), session_id=str(session.id)
            )
            return session, RouteEnum.INSTANT, _FALLBACK

    async def _finalize(
        self,
        session: Session,
        route: RouteEnum,
        response: str | AsyncIterator[str],
        stream: bool,
    ) -> tuple[Session, RouteEnum, str | AsyncIterator[str]]:
        """Si stream=False : draine la réponse, ajoute l'assistant en session."""
        if stream:
            return session, route, response
        if isinstance(response, str):
            text = response
        else:
            text = "".join([chunk async for chunk in response])
        session.add_message("assistant", text)
        return session, route, text
