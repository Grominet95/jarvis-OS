"""Router FastAPI pour les webhooks entrants des canaux de messagerie.

Point d'entrée : POST /api/channels/{platform}/webhook
Utilisé par les plateformes qui pushent des événements (WhatsApp, Slack, Signal)
plutôt que de maintenir une connexion polling (Telegram/Discord).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from jarvis.interfaces.channels.base import IncomingMessage, Platform

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.post("/{platform}/webhook")
async def channel_webhook(platform: str, request: Request) -> dict:
    """Reçoit un webhook d'une plateforme externe et le route via MessagingGateway.

    Le corps de la requête est passé en tant que payload brut.
    L'adaptateur correspondant doit être enregistré dans le MessagingGateway.
    """
    try:
        plat = Platform(platform.lower())
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Plateforme inconnue : {platform}") from None

    gateway = getattr(request.app.state, "messaging_gateway", None)
    if gateway is None:
        raise HTTPException(status_code=503, detail="MessagingGateway non démarré.")

    adapter = gateway._adapters.get(plat.value)
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail=f"Aucun adaptateur enregistré pour la plateforme '{platform}'.",
        )

    payload = await request.json()
    logger.info("Webhook reçu", platform=platform, payload_keys=list(payload.keys()))

    # Chaque adaptateur webhook doit implémenter handle_webhook() pour parser
    # son propre format. Les adaptateurs polling (Telegram, Discord) n'en ont
    # pas besoin.
    handle_fn = getattr(adapter, "handle_webhook", None)
    if handle_fn is None:
        raise HTTPException(
            status_code=501,
            detail=f"L'adaptateur '{platform}' ne supporte pas les webhooks.",
        )

    msg: IncomingMessage = await handle_fn(payload)
    await gateway.dispatch(msg)
    return {"status": "ok"}
