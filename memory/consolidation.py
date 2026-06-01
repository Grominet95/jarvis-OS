from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from llm.base import LLMProvider
from memory.index import MemoryIndex
from memory.topics import TopicStore

if TYPE_CHECKING:
    from memory.search import FTSIndex, VectorIndex

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "consolidation.md"
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class ConsolidationAgent:
    """Extrait les faits durables d'un échange et les persiste dans les fichiers thématiques.

    Tourne toujours en arrière-plan — ne bloque jamais le chemin vocal.
    """

    def __init__(
        self,
        llm: LLMProvider,
        memory_index: MemoryIndex,
        topic_store: TopicStore,
    ) -> None:
        self._llm = llm
        self._memory_index = memory_index
        self._topic_store = topic_store
        self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    def fire(self, user_message: str, assistant_message: str) -> None:
        """Lance la consolidation en fire-and-forget. Ne bloque jamais."""
        asyncio.create_task(self._run_safe(user_message, assistant_message))

    async def _run_safe(self, user_message: str, assistant_message: str) -> None:
        try:
            await self._run(user_message, assistant_message)
        except Exception as e:
            logger.error("Consolidation error", error=str(e))

    async def _run(self, user_message: str, assistant_message: str) -> None:
        topics = self._topic_store.load_all()
        existing_str = (
            "\n\n---\n\n".join(f"### {name}\n{content}" for name, content in topics.items())
            or "Aucun fichier thématique existant."
        )

        prompt = (
            self._prompt_template.replace("{existing_topics}", existing_str)
            .replace("{user_message}", user_message)
            .replace("{assistant_message}", assistant_message)
        )

        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system="Tu es un agent de mémorisation. Réponds uniquement en JSON valide.",
            stream=False,
            context="memory",
        )

        self._apply(str(response))

    def _apply(self, raw: str) -> None:
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = _CODE_FENCE_RE.search(raw)
        candidate = fence_match.group(1) if fence_match else raw

        match = _JSON_RE.search(candidate)
        if not match:
            logger.debug("Consolidation: no JSON in response", preview=raw[:120])
            return

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            logger.error("Consolidation: JSON parse error", error=str(e), preview=raw[:120])
            return

        updates: list[dict] = data.get("updates", [])
        if not updates:
            logger.debug("Consolidation: nothing to memorize")
            return

        for update in updates:
            file_path: str = update.get("file", "")
            content: str = update.get("content", "")
            if not file_path or not content:
                continue

            filename = Path(file_path).name
            self._topic_store.write(filename, content)

            section: str = update.get("section", "Divers")
            key: str = update.get("key", filename.replace(".md", ""))
            pointer: str = update.get("pointer", filename)
            self._memory_index.add_pointer(
                section=section,
                key=key,
                filepath=f"topics/{filename}",
                description=pointer,
            )
            logger.info("Consolidated", file=filename, key=key)


class CrossSessionRecall:
    """Rappel cross-session : FTS5 + recherche vectorielle → résumé LLM.

    Inspiré de Hermes session_search + recall (NousResearch, MIT).
    Voir notices/memory-recall.md pour l'attribution complète.
    """

    MAX_CONTEXT_CHARS = 3000

    def __init__(
        self,
        llm: LLMProvider,
        fts_index: FTSIndex,
        vector_index: VectorIndex,
    ) -> None:
        self._llm = llm
        self._fts = fts_index
        self._vector = vector_index

    async def recall(self, query: str, k: int = 8) -> str | None:
        """Recherche dans les sessions passées et retourne un résumé LLM.

        Retourne None si les index sont vides ou aucun résultat pertinent.
        """
        if not query.strip():
            return None

        fts_results, vec_results = await asyncio.gather(
            self._fts.search(query, k=k),
            self._vector.search(query, k=k),
        )

        # Déduplique par doc_id — FTS5 en priorité (correspondances exactes)
        seen: set[str] = set()
        excerpts: list[str] = []
        for r in fts_results + vec_results:
            doc_id = r["doc_id"]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            text = r["text"][:600].strip()
            if text:
                excerpts.append(f"[{doc_id}]\n{text}")
            if len(excerpts) >= k:
                break

        if not excerpts:
            return None

        context = "\n\n---\n\n".join(excerpts)[: self.MAX_CONTEXT_CHARS]
        prompt = (
            f"Résume les informations utiles de ces échanges passés pour la question : "
            f"'{query}'\n\nEXTRAITS :\n{context}\n\n"
            "Synthèse concise (2-4 phrases), uniquement les faits pertinents :"
        )

        try:
            summary = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system="Tu es un agent de rappel de mémoire. Sois concis et factuel.",
                stream=False,
                context="memory",
            )
            return str(summary).strip() or None
        except Exception as e:
            logger.warning("CrossSessionRecall LLM failed", error=str(e))
            return None
