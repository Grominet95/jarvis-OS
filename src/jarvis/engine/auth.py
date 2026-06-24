# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Garde-fou réseau — authentification Bearer pour l'API Jarvis."""

from __future__ import annotations

import hmac
from collections.abc import Sequence

from fastapi import HTTPException
from loguru import logger
from starlette.requests import HTTPConnection

from jarvis.kernel.settings import settings

# Chemins exemptés de l'authentification Bearer.
# Un préfixe couvre toutes ses sous-routes.
_EXEMPT_EXACT: frozenset[str] = frozenset({
    "/health",
    "/api/health",
    "/",
    "/command",
    "/dashboard",
    "/settings",
    "/capabilities",
    "/admin",
    "/macropad",
    "/mc",
    # OAuth Spotify : seuls le lancement (lien <a href>) et le callback (redirect
    # navigateur) ne peuvent pas porter de header Bearer. On exempte UNIQUEMENT
    # ces 2 routes — surtout PAS tout /api/spotify/ (qui contient /token, /play,
    # /transfer… appelés en fetch avec authHeaders et qui DOIVENT rester protégés).
    "/api/spotify/auth",
    "/api/spotify/callback",
})
_EXEMPT_PREFIXES: Sequence[str] = (
    "/api/channels/",  # webhooks — vérification de signature propre
    "/api/google/",  # OAuth Google — redirect navigateur, header impossible
)


async def verify_api_token(request: HTTPConnection) -> None:
    """Dépendance FastAPI globale — vérification du token Bearer.

    No-op si ``api_auth_enabled=False`` (usage local inchangé).
    Quand activée : exige ``Authorization: Bearer <token>`` sauf pour les
    endpoints exemptés (health, webhooks canaux, OAuth Google) et les
    connexions WebSocket (l'API browser ne supporte pas les headers d'upgrade).

    Périmètre non protégé intentionnellement :
    - Pages HTML de l'UI (``/``, ``/dashboard``, …) — routes FastAPI explicites,
      exemptées ici ; le token API est injecté dans le HTML pour les appels
      ``/api/*`` depuis le navigateur (voir ``interfaces/api/ui.py``)
    - Assets statiques (``StaticFiles`` mount) — sous-app ASGI, hors dépendance
    - Connexions WebSocket (``/ws/*``) — navigateur sans header Authorization
    - Callbacks OAuth (``/api/google/``) — redirect tiers, token impossible
    - Webhooks canaux (``/api/channels/``) — signature propre (HMAC/Token)
    """
    if not settings.api_auth_enabled:
        return

    # WebSocket : le navigateur ne peut pas envoyer Authorization à l'upgrade
    if request.scope.get("type") == "websocket":
        return

    path: str = request.url.path
    if path in _EXEMPT_EXACT:
        return
    for prefix in _EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return

    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "Auth: token manquant",
            path=path,
            client=request.client.host if request.client else "?",
        )
        raise HTTPException(status_code=401, detail="Token Bearer requis.")

    token = auth_header[len("Bearer ") :]
    expected = settings.api_token.get_secret_value()
    if not expected or not hmac.compare_digest(
        token.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        logger.warning(
            "Auth: token invalide",
            path=path,
            client=request.client.host if request.client else "?",
        )
        raise HTTPException(status_code=401, detail="Token invalide.")
