"""Modèle utilisateur dialectique inspiré de Honcho (Plastic Labs, MIT).

Maintient un fichier user_model.md qui s'enrichit au fil des échanges.
Mise à jour LLM fire-and-forget après chaque tour de conversation.
Voir notices/memory-recall.md pour l'attribution complète.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from jarvis.providers.llm.base import LLMProvider

_MAX_MODEL_WORDS = 300


class UserModel:
    """Modèle utilisateur dialectique persisté dans un fichier Markdown.

    Capture les préférences, patterns comportementaux et contradictions
    observées au fil des échanges. Mise à jour asynchrone non-bloquante.
    """

    def __init__(self, llm: LLMProvider, model_path: Path) -> None:
        self._llm = llm
        self._path = model_path

    def load(self) -> str:
        """Lit le modèle courant depuis le fichier. Retourne '' si absent."""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8").strip()

    def fire(self, user_message: str, assistant_message: str) -> None:
        """Lance la mise à jour en fire-and-forget. Ne bloque jamais."""
        asyncio.create_task(
            self._update_safe(user_message, assistant_message),
            name="user-model-update",
        )

    async def _update_safe(self, user_message: str, assistant_message: str) -> None:
        try:
            await self._update(user_message, assistant_message)
        except Exception as e:
            logger.error("UserModel update error", error=str(e))

    async def _update(self, user_message: str, assistant_message: str) -> None:
        current = self.load()
        prompt = (
            f"Modèle utilisateur actuel :\n{current or '(vide)'}\n\n"
            f"Nouvel échange :\n"
            f"User: {user_message[:500]}\n"
            f"Jarvis: {assistant_message[:500]}\n\n"
            f"Mets à jour le modèle utilisateur en intégrant les nouvelles observations. "
            f"Note préférences, patterns, contradictions (dialectique : si une observation "
            f"contredit le modèle actuel, note la tension). "
            f"Format : bullets courts. Max {_MAX_MODEL_WORDS} mots. "
            "Renvoie UNIQUEMENT le modèle mis à jour, sans explication :"
        )
        updated = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system="Tu es un agent de modélisation utilisateur. Sois concis et factuel.",
            stream=False,
            context="memory",
        )
        text = str(updated).strip()
        if text:
            self._path.write_text(text, encoding="utf-8")
            logger.debug("UserModel updated", chars=len(text))
