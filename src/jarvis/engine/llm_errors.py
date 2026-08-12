# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import anthropic
from openai import APIConnectionError as OpenAIConnectionError
from openai import APIStatusError as OpenAIStatusError
from openai import AuthenticationError as OpenAIAuthenticationError
from openai import RateLimitError as OpenAIRateLimitError

from jarvis.kernel.settings import Settings, settings


def llm_config_error(cfg: Settings | None = None) -> str | None:
    """Return a user-facing message when the LLM backend is not configured."""
    cfg = cfg or settings
    if cfg.llm_provider == "local":
        return None
    backend = cfg.api_backend
    key_field = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "mistral": "mistral_api_key",
        "gemini": "google_api_key",
    }.get(backend)
    env_name = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }.get(backend, "API_KEY")
    if key_field is None:
        return None
    key = getattr(cfg, key_field).get_secret_value().strip()
    if not key or "..." in key or len(key) < 20:
        name = cfg.display_name
        return (
            f"Désolé {name}, {env_name} est vide ou invalide dans .env. "
            f"Jarvis ne peut pas joindre {backend}."
        )
    return None


def friendly_llm_error(exc: BaseException, cfg: Settings | None = None) -> str:
    """Map provider exceptions to a short French message for the user."""
    cfg = cfg or settings
    name = cfg.display_name

    if isinstance(exc, anthropic.AuthenticationError):
        return (
            f"Désolé {name}, Anthropic refuse ma clé API. "
            "Vérifie ANTHROPIC_API_KEY dans .env."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return f"Désolé {name}, Anthropic limite le débit. Réessaie dans quelques secondes."
    if isinstance(exc, anthropic.APIConnectionError):
        return f"Désolé {name}, impossible de joindre l'API Anthropic (réseau)."
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code in (529, 503):
            return f"Désolé {name}, les serveurs Anthropic sont surchargés. Réessaie."
        if exc.status_code == 401:
            return (
                f"Désolé {name}, Anthropic refuse ma clé API. "
                "Vérifie ANTHROPIC_API_KEY dans .env."
            )
        if exc.status_code == 403:
            return f"Désolé {name}, accès Anthropic refusé (403). Vérifie ton compte et ta clé."
        if exc.status_code == 400:
            detail = str(exc).lower()
            if any(k in detail for k in ("context", "token", "too long", "maximum")):
                return (
                    f"Désolé {name}, le contexte est trop long pour Claude. "
                    "Démarre une nouvelle session."
                )

    if isinstance(exc, OpenAIAuthenticationError):
        return f"Désolé {name}, la clé OpenAI est refusée. Vérifie OPENAI_API_KEY dans .env."
    if isinstance(exc, OpenAIRateLimitError):
        return f"Désolé {name}, quota ou débit API atteint. Réessaie dans quelques secondes."
    if isinstance(exc, OpenAIConnectionError):
        return f"Désolé {name}, impossible de joindre l'API LLM (réseau)."
    if isinstance(exc, OpenAIStatusError):
        if exc.status_code in (529, 503):
            return f"Désolé {name}, le fournisseur LLM est surchargé. Réessaie."
        if exc.status_code == 401:
            return f"Désolé {name}, clé API refusée. Vérifie .env."

    detail = str(exc).lower()
    if any(k in detail for k in ("credit", "billing", "balance", "payment")):
        return f"Désolé {name}, le compte LLM n'a plus de crédits."
    if any(k in detail for k in ("context", "too long", "maximum context", "token limit")):
        return (
            f"Désolé {name}, le contexte est trop long pour ce modèle. "
            "Démarre une nouvelle session."
        )

    return f"Désolé {name}, j'ai eu un souci, je regarde."
