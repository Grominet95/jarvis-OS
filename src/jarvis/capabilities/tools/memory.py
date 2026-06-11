from __future__ import annotations

from pathlib import Path

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.contracts import FTSIndex, TopicStore, VectorIndex
from jarvis.kernel.settings import settings


def _is_invalid_filename(filename: str) -> bool:
    """Vérifie qu'un nom de fichier topic est sûr (pas de path traversal)."""
    return "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".md")


class MemoryTopicWriteTool(Tool):
    """Écrit ou met à jour un fichier de mémoire thématique existant."""

    name = "memory_write"
    description = (
        "Écrire ou mettre à jour le contenu d'un fichier mémoire thématique (topics). "
        "Utiliser pour sauvegarder des préférences utilisateur, informations personnelles, "
        "contexte projet, etc. La mise à jour REMPLACE le contenu du fichier. "
        "Fichiers disponibles : user_prefs.md, user_profile.md, spotify.md, notion.md, "
        "home_assistant.md, visual_memory.md. "
        "IMPORTANT : lire le fichier d'abord (read_file tool) pour préserver l'existant."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Nom exact du fichier topic (ex: user_prefs.md). Doit exister.",
            },
            "content": {
                "type": "string",
                "description": "Nouveau contenu complet du fichier (Markdown).",
            },
        },
        "required": ["filename", "content"],
    }

    def __init__(
        self,
        topics_dir: Path | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self._dir = topics_dir or (Path(settings.memory_dir) / "topics")
        self._vector_index = vector_index

    async def execute(self, filename: str, content: str) -> ToolResult:
        if _is_invalid_filename(filename):
            return ToolResult(content="Nom de fichier invalide.", is_error=True)
        path = self._dir / filename
        if not path.exists():
            existing = [p.name for p in self._dir.glob("*.md")]
            return ToolResult(
                content=(
                    f"Fichier '{filename}' introuvable."
                    f" Fichiers disponibles : {', '.join(existing)}"
                ),
                is_error=True,
            )
        path.write_text(content, encoding="utf-8")
        if self._vector_index is not None:
            await self._vector_index.add(
                doc_id=f"topic:{filename}",
                text=content,
                metadata={"source": "topic", "filename": filename},
            )
            await self._vector_index.persist()
        return ToolResult(content=f"Mémoire '{filename}' mise à jour ({len(content)} caractères).")


class MemoryLoadTopicTool(Tool):
    """Charge à la demande le contenu d'un fichier thématique mémoire."""

    name = "memory_load_topic"
    description = (
        "Charger le contenu complet d'un fichier mémoire thématique (topics) à la demande. "
        "Les fichiers thématiques ne sont PLUS préchargés dans le prompt — utilise cet outil "
        "lorsque tu as besoin de consulter le détail d'un sujet précis. "
        "Conseil : utilise d'abord `memory_search` pour identifier le bon fichier."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Nom exact du fichier topic à lire (ex: user_prefs.md).",
            },
        },
        "required": ["filename"],
    }

    def __init__(self, topic_store: TopicStore) -> None:
        self._store = topic_store

    async def execute(self, filename: str) -> ToolResult:
        if _is_invalid_filename(filename):
            return ToolResult(content="Nom de fichier invalide.", is_error=True)
        if not self._store.exists(filename):
            existing = ", ".join(self._store.list_all()) or "(aucun)"
            return ToolResult(
                content=f"Fichier '{filename}' introuvable. Fichiers disponibles : {existing}",
                is_error=True,
            )
        content = self._store.load(filename)
        return ToolResult(content=f"# {filename}\n\n{content}")


class MemorySearchTool(Tool):
    """Recherche sémantique dans la mémoire (topics + transcripts) via embeddings."""

    name = "memory_search"
    description = (
        "Recherche sémantique dans toute la mémoire (fichiers thématiques + transcripts). "
        "Renvoie les passages les plus pertinents pour la requête, avec leur source. "
        "Utiliser pour retrouver une information mémorisée avant éventuellement d'appeler "
        "`memory_load_topic` pour le détail complet d'un fichier."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Question ou mots-clés en langage naturel.",
            },
            "k": {
                "type": "integer",
                "description": "Nombre de résultats à renvoyer (défaut : 5).",
            },
        },
        "required": ["query"],
    }

    def __init__(self, vector_index: VectorIndex) -> None:
        self._index = vector_index

    async def execute(self, query: str, k: int = 5) -> ToolResult:
        if not query.strip():
            return ToolResult(content="Requête vide.", is_error=True)
        try:
            k_int = max(1, min(20, int(k)))
        except (TypeError, ValueError):
            k_int = 5
        results = await self._index.search(query=query, k=k_int)
        if not results:
            return ToolResult(content="Aucun résultat pertinent trouvé en mémoire.")
        lines: list[str] = []
        for i, r in enumerate(results, start=1):
            meta = r.get("metadata", {})
            source = meta.get("filename") or meta.get("source") or r.get("doc_id", "?")
            score = r.get("score", 0.0)
            text = r.get("text", "").strip()
            lines.append(f"[{i}] {source} (score={score:.3f})\n{text}")
        return ToolResult(content="\n\n---\n\n".join(lines))


class CrossSessionRecallTool(Tool):
    """Recherche dans les sessions passées par FTS5 + vectoriel.

    Permet à l'agent de rappeler explicitement des échanges antérieurs
    en combinant recherche plein texte exacte et recherche sémantique.
    """

    name = "session_recall"
    description = (
        "Recherche dans les sessions de conversation passées (FTS5 + sémantique). "
        "Retourne les extraits les plus pertinents des échanges précédents. "
        "Utilise pour retrouver ce qui a été dit lors de sessions antérieures, "
        "comme des décisions, préférences ou contexte de projets passés."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Question ou mots-clés à rechercher dans les sessions.",
            },
            "k": {
                "type": "integer",
                "description": "Nombre de résultats (défaut : 6).",
            },
        },
        "required": ["query"],
    }

    def __init__(self, fts_index: FTSIndex, vector_index: VectorIndex) -> None:
        self._fts = fts_index
        self._vector = vector_index

    async def execute(self, query: str, k: int = 6) -> ToolResult:  # type: ignore[override]
        import asyncio

        if not query.strip():
            return ToolResult(content="Requête vide.", is_error=True)
        k_int = max(1, min(20, int(k)))

        fts_results, vec_results = await asyncio.gather(
            self._fts.search(query, k=k_int),
            self._vector.search(query, k=k_int),
        )

        seen: set[str] = set()
        lines: list[str] = []
        for r in fts_results + vec_results:
            doc_id = r["doc_id"]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            text = r["text"][:400].strip()
            score = r.get("score", 0.0)
            lines.append(f"[{doc_id}] (score={score:.3f})\n{text}")
            if len(lines) >= k_int:
                break

        if not lines:
            return ToolResult(content="Aucun résultat trouvé dans les sessions passées.")
        return ToolResult(content="\n\n---\n\n".join(lines))
