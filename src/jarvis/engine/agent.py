from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from loguru import logger

from jarvis.engine.session import Session
from jarvis.kernel.contracts import (
    LLMProvider,
    MemoryIndex,
    SkillRegistry,
    ToolRegistry,
    TopicStore,
)
from jarvis.kernel.paths import PROMPTS_DIR
from jarvis.kernel.schemas import ToolCapture
from jarvis.kernel.settings import Settings

_STATIC_PROMPT_PATH = PROMPTS_DIR / "system_static.md"


class Agent:
    """Construit le prompt (static + dynamic), appelle le LLM, retourne le stream.

    Phase C : `settings` injecté au constructeur (auparavant
    `from config.settings import settings as _s` en local dans
    `_build_system()`). Les autres dépendances (llm, memory_index,
    topic_store, tool_registry, skill_registry, user_prefs_path,
    user_model_path) étaient déjà injectées en Phase pré-C.

    Note CYCLE 1 (CDC §C.1.3) : `from jarvis.providers.llm.api import
    ToolCapture` au top-level franchit la couche engine → providers.
    Cette dépendance sera résolue dans un commit dédié post-gateway
    en faisant remonter `ToolCapture` (et `UsageEntry`, `calculate_cost`)
    dans `kernel/`. Hors-périmètre du commit présent.
    """

    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        memory_index: MemoryIndex | None = None,
        topic_store: TopicStore | None = None,
        tool_registry: ToolRegistry | None = None,
        user_prefs_path: Path | None = None,
        skill_registry: SkillRegistry | None = None,
        user_model_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._memory_index = memory_index
        self._topic_store = topic_store
        self._tool_registry = tool_registry
        self._user_prefs_path = user_prefs_path
        self._skill_registry = skill_registry
        self._user_model_path = user_model_path

    def _build_system(
        self,
        notifications: list[str] | None = None,
        recall_summary: str | None = None,
    ) -> str:
        """Assemble le prompt système : partie statique + contexte dynamique."""
        _s = self._settings

        static_system = _STATIC_PROMPT_PATH.read_text(encoding="utf-8")
        if _s.quebec_mode:
            static_system += (
                "\n\n## Mode Québécois (ACTIF)\n"
                "Tu parles avec un accent et du dialecte québécois authentique. "
                "Utilise : 'ostie', 'câlice', 'tabarnak' (avec parcimonie),"
                " 'c'est le boutte', 'en masse', 'pantoute', 'tantôt', 'maudit', 'icitte',"
                " 'chu' (je suis), 'ben' (bien), 'toé', 'moé', 'faque', 't'sé',"
                " 'un char' (voiture), 'magasiner' (shopping). "
                "Garde la personnalité Jarvis (direct, efficace, ironie)"
                " avec la couleur québécoise."
            )
        dynamic_parts: list[str] = ["=== CONTEXTE DYNAMIQUE ==="]

        # Identité LLM — indispensable pour les modèles locaux qui ne savent pas ce qu'ils sont
        if _s.llm_provider == "local":
            llm_id = f"Ollama / {_s.ollama_model}"
        else:
            _model_map = {
                "anthropic": _s.anthropic_model,
                "mistral": _s.mistral_model,
                "openai": _s.openai_model,
            }
            llm_id = _model_map.get(_s.api_backend, _s.anthropic_model)
        dynamic_parts.append(f"## Moteur LLM actif\n\nTu tournes sur **{llm_id}**.")

        # Date/heure toujours injectée — utile pour le calendrier et les calculs temporels
        now = datetime.now()
        dynamic_parts.append(f"## Date et heure\n\n{now.strftime('%Y-%m-%d %H:%M')}")

        if recall_summary:
            dynamic_parts.append(f"## Rappel de sessions précédentes\n\n{recall_summary}")

        if self._user_model_path is not None and self._user_model_path.exists():
            model_text = self._user_model_path.read_text(encoding="utf-8").strip()
            if model_text:
                dynamic_parts.append(f"## Modèle utilisateur\n\n{model_text}")

        if self._user_prefs_path is not None and self._user_prefs_path.exists():
            prefs = self._user_prefs_path.read_text(encoding="utf-8").strip()
            if prefs:
                dynamic_parts.append(f"## Préférences Barth\n\n{prefs}")

        if self._memory_index is not None:
            index_content = self._memory_index.read()
            dynamic_parts.append(f"## Mémoire index\n\n{index_content}")

        if self._topic_store is not None:
            topic_names = self._topic_store.list_all()
            if topic_names:
                names_list = "\n".join(f"- `{name}`" for name in topic_names)
                dynamic_parts.append(
                    "## Fichiers thématiques disponibles\n\n"
                    "Ces fichiers ne sont PAS préchargés. Pour les consulter, utilise "
                    "`memory_search` (recherche sémantique) puis `memory_load_topic(filename=...)` "
                    "pour lire un fichier complet si nécessaire (routing [CF]).\n\n"
                    f"{names_list}"
                )

        if self._tool_registry is not None and self._tool_registry.has_tools():
            tool_lines = "\n".join(
                f"- `{s['name']}` : {s['description']}" for s in self._tool_registry.schemas()
            )
            dynamic_parts.append(
                f"## Outils disponibles (router [CF] pour les utiliser)\n\n{tool_lines}"
            )

        if self._skill_registry is not None:
            skills_prompt = self._skill_registry.get_combined_system_prompt()
            if skills_prompt:
                dynamic_parts.append("# SKILLS ACTIFS\n\n" + skills_prompt)

        if notifications:
            notif_content = "\n".join(f"- {n}" for n in notifications)
            dynamic_parts.append(
                f"## Notifications en attente — À GLISSER EN FIN DE RÉPONSE\n\n{notif_content}"
            )

        return static_system + "\n\n" + "\n\n".join(dynamic_parts)

    def has_tools(self) -> bool:
        return (
            self._tool_registry is not None
            and self._tool_registry.has_tools()
            and self._llm.supports_tools
        )

    async def respond(
        self,
        session: Session,
        user_message: str,
        stream: bool = True,
        notifications: list[str] | None = None,
    ) -> str | AsyncIterator[str]:
        """Routing-only pass : ajoute le message, appelle le LLM SANS outils (streaming).

        Le gateway lit le tag [I/CF/BG] depuis le stream et décide ensuite si un
        tool_loop est nécessaire (uniquement pour CF). Pour BG, le worker fait le vrai travail.
        """
        session.add_message("user", user_message)
        system = self._build_system(notifications=notifications)
        logger.debug("Agent responding", session_id=str(session.id), stream=stream)

        result = await self._llm.complete(
            messages=session.messages,
            system=system,
            stream=True,  # toujours streaming pour la détection du tag
        )
        if not stream:
            # collecte le stream pour les appelants non-streaming (tests, consolidation…)
            chunks: list[str] = []
            async for chunk in result:  # type: ignore[union-attr]
                chunks.append(chunk)
            text = "".join(chunks)
            session.add_message("assistant", text)
            return text
        return result

    async def respond_tools(
        self,
        session: Session,
        notifications: list[str] | None = None,
    ) -> str:
        """Tool loop sur les messages existants (user déjà ajouté par respond()).

        Conservé pour rétrocompatibilité (tests). Le gateway utilise désormais
        start_routing_stream() + finalize_tool_capture().
        """
        system = self._build_system(notifications=notifications)
        return await self._llm.tool_loop(
            messages=session.messages,
            system=system,
            tools=self._tool_registry.schemas(),  # type: ignore[union-attr]
            tool_executor=self._tool_registry.call_str,  # type: ignore[union-attr]
        )

    def start_routing_stream(
        self,
        session: Session,
        user_message: str,
        notifications: list[str] | None = None,
        recall_summary: str | None = None,
    ) -> tuple[AsyncIterator[str], ToolCapture | None]:
        """Un seul appel LLM streamé, avec outils si disponibles.

        Ajoute user_message à la session, lance le stream et retourne
        (stream, capture). Le ToolCapture est populé dès que le stream
        est entièrement consommé ; None si le provider ne supporte pas les outils.
        """
        session.add_message("user", user_message)
        system = self._build_system(notifications=notifications, recall_summary=recall_summary)
        logger.debug("Agent routing stream", session_id=str(session.id))

        if self.has_tools() and hasattr(self._llm, "stream_with_capture"):
            stream, capture = self._llm.stream_with_capture(  # type: ignore[union-attr]
                messages=session.messages,
                system=system,
                tools=self._tool_registry.schemas(),  # type: ignore[union-attr]
            )
            return stream, capture

        # Provider sans outil (Ollama, Mistral) — wrapper async pour await complete()
        messages_snap = list(session.messages)

        async def _simple_stream() -> AsyncIterator[str]:
            result = await self._llm.complete(messages=messages_snap, system=system, stream=True)
            async for chunk in result:  # type: ignore[union-attr]
                yield chunk

        return _simple_stream(), None

    async def execute_captured_tools(self, capture: ToolCapture) -> list[str]:
        """Exécute en parallèle les tool_use capturés et retourne les résultats bruts."""
        results = await asyncio.gather(
            *(self._tool_registry.call_str(name, inp) for _, name, inp in capture.calls)  # type: ignore[union-attr]
        )
        logger.debug("Tools executed", names=[n for _, n, _ in capture.calls])
        return list(results)

    async def synthesize(
        self,
        session: Session,
        ack_text: str,
        capture: ToolCapture,
        results: list[str],
    ) -> AsyncIterator[str]:
        """Second appel LLM pour synthétiser les résultats d'outils en réponse naturelle.

        Construit le format Anthropic tool_use/tool_result et streame la synthèse.
        """
        # Bloc assistant avec le texte d'ack + les tool_use calls
        assistant_content: list[dict] = []
        if ack_text.strip():
            assistant_content.append({"type": "text", "text": ack_text})
        for tool_id, tool_name, tool_input in capture.calls:
            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input,
                }
            )

        # Bloc user avec les tool_result
        tool_result_blocks = [
            {"type": "tool_result", "tool_use_id": tid, "content": r}
            for (tid, _, _), r in zip(capture.calls, results, strict=True)
        ]

        messages = list(session.messages) + [
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": tool_result_blocks},
        ]

        system = self._build_system()
        logger.debug("Agent synthesizing tool results", tools=[n for _, n, _ in capture.calls])

        # Pas de tools ici : le LLM se concentre sur la synthèse, pas de chainage
        stream = await self._llm.complete(messages=messages, system=system, stream=True)
        async for chunk in stream:  # type: ignore[union-attr]
            yield chunk
