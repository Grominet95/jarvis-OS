from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from memory.topics import TopicStore

_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_CHUNK_TOKENS = 500
_CHUNK_OVERLAP = 80


def _chunk_text(
    text: str,
    chunk_size: int = _CHUNK_TOKENS,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """Découpe un texte en chunks ~chunk_size tokens avec chevauchement.

    Approximation simple : un token ≈ un mot pour le français. C'est suffisant
    pour le chunking ; les embeddings se chargent de la sémantique précise.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [text]
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks


class VectorIndex:
    """Index vectoriel persistant pour la recherche sémantique en mémoire.

    Utilise fastembed (ONNX, offline, multilingue) pour les embeddings.
    Persistance simple : un .npy pour les vecteurs et un manifest JSON pour
    les métadonnées. Pas de service externe.
    """

    def __init__(
        self,
        index_dir: Path,
        model_name: str = _DEFAULT_MODEL,
    ) -> None:
        self._dir = index_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._model_name = model_name
        self._model: Any = None  # fastembed.TextEmbedding (lazy)
        self._lock = asyncio.Lock()
        self._vectors: np.ndarray | None = None  # shape (N, D)
        self._manifest: list[dict] = []  # liste de {doc_id, text, metadata}
        self._vectors_path = self._dir / "vectors.npy"
        self._manifest_path = self._dir / "manifest.json"
        self.load()

    # ── chargement modèle ────────────────────────────────────
    def _ensure_model(self) -> None:
        """Instancie le modèle d'embedding au premier usage (synchrone)."""
        if self._model is not None:
            return
        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover — dépendance déclarée
            raise RuntimeError(
                "fastembed n'est pas installé. Ajoute 'fastembed' à pyproject.toml."
            ) from e
        logger.info("VectorIndex: chargement du modèle", model=self._model_name)
        self._model = TextEmbedding(model_name=self._model_name)

    def _embed_sync(self, texts: list[str]) -> np.ndarray:
        """Encode une liste de textes en vecteurs normalisés (synchrone)."""
        self._ensure_model()
        embeddings = list(self._model.embed(texts))
        arr = np.asarray(embeddings, dtype=np.float32)
        # Normalisation L2 pour permettre la similarité cosinus via produit scalaire
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return arr / norms

    async def _embed(self, texts: list[str]) -> np.ndarray:
        """Wrapper async — délègue l'embedding lourd à un thread."""
        return await asyncio.to_thread(self._embed_sync, texts)

    # ── API publique ─────────────────────────────────────────
    async def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Ajoute (ou remplace) un document dans l'index.

        Le document est chunké si nécessaire. Les chunks existants pour
        ce doc_id sont supprimés avant insertion.
        """
        meta = dict(metadata or {})
        text = text.strip()
        if not text:
            return
        chunks = _chunk_text(text)
        if not chunks:
            return
        async with self._lock:
            self._remove_doc_locked(doc_id)
            vectors = await self._embed(chunks)
            entries = [
                {
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "text": chunk,
                    "metadata": meta,
                }
                for i, chunk in enumerate(chunks)
            ]
            self._manifest.extend(entries)
            self._vectors = (
                vectors if self._vectors is None else np.vstack([self._vectors, vectors])
            )
        logger.debug("VectorIndex.add", doc_id=doc_id, chunks=len(chunks))

    async def search(self, query: str, k: int = 5) -> list[dict]:
        """Recherche les k chunks les plus pertinents par similarité cosinus."""
        if not query.strip() or self._vectors is None or len(self._manifest) == 0:
            return []
        qv = await self._embed([query])
        scores = (self._vectors @ qv[0]).astype(float)
        k = min(k, len(scores))
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        results: list[dict] = []
        for i in top_idx:
            entry = self._manifest[int(i)]
            results.append(
                {
                    "doc_id": entry["doc_id"],
                    "text": entry["text"],
                    "metadata": entry.get("metadata", {}),
                    "score": float(scores[int(i)]),
                }
            )
        return results

    async def persist(self) -> None:
        """Sauvegarde vecteurs (.npy) et manifest (JSON) sur disque."""
        async with self._lock:
            self._persist_locked()

    def _persist_locked(self) -> None:
        if self._vectors is None or len(self._manifest) == 0:
            # Index vide → on supprime les fichiers existants pour cohérence
            self._vectors_path.unlink(missing_ok=True)
            self._manifest_path.unlink(missing_ok=True)
            return
        np.save(self._vectors_path, self._vectors)
        self._manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("VectorIndex persisted", entries=len(self._manifest), dir=str(self._dir))

    def load(self) -> None:
        """Charge l'index depuis disque s'il existe. Sinon laisse l'index vide."""
        if not (self._vectors_path.exists() and self._manifest_path.exists()):
            self._vectors = None
            self._manifest = []
            return
        try:
            self._vectors = np.load(self._vectors_path)
            self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            logger.info("VectorIndex loaded", entries=len(self._manifest), dir=str(self._dir))
        except (OSError, ValueError, json.JSONDecodeError) as e:
            logger.error("VectorIndex.load failed", error=str(e))
            self._vectors = None
            self._manifest = []

    async def reindex(
        self,
        topic_store: TopicStore,
        transcripts_dir: Path | None = None,
    ) -> int:
        """Reconstruit l'index depuis tous les topics + transcripts JSONL.

        Retourne le nombre de documents indexés (avant chunking).
        """
        async with self._lock:
            self._vectors = None
            self._manifest = []

        count = 0
        for name in topic_store.list_all():
            content = topic_store.load(name)
            if not content.strip():
                continue
            await self.add(
                doc_id=f"topic:{name}",
                text=content,
                metadata={"source": "topic", "filename": name},
            )
            count += 1

        if transcripts_dir is not None and transcripts_dir.exists():
            for jsonl in sorted(transcripts_dir.glob("*.jsonl")):
                text = VectorIndex.transcript_to_text(jsonl)
                if not text.strip():
                    continue
                await self.add(
                    doc_id=f"transcript:{jsonl.name}",
                    text=text,
                    metadata={"source": "transcript", "filename": jsonl.name},
                )
                count += 1

        await self.persist()
        logger.info("VectorIndex reindex done", docs=count)
        return count

    def is_empty(self) -> bool:
        return self._vectors is None or len(self._manifest) == 0

    # ── utils internes ───────────────────────────────────────
    def _remove_doc_locked(self, doc_id: str) -> None:
        """Supprime tous les chunks d'un doc_id existant (suppose lock détenu)."""
        if self._vectors is None or not self._manifest:
            return
        keep_idx = [i for i, entry in enumerate(self._manifest) if entry["doc_id"] != doc_id]
        if len(keep_idx) == len(self._manifest):
            return
        if not keep_idx:
            self._vectors = None
            self._manifest = []
            return
        self._manifest = [self._manifest[i] for i in keep_idx]
        self._vectors = self._vectors[keep_idx]

    @staticmethod
    def transcript_to_text(path: Path) -> str:
        """Concatène les messages d'un transcript JSONL en un seul texte."""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        parts: list[str] = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = obj.get("role", "")
            content = obj.get("content", "")
            if isinstance(content, str) and content.strip():
                parts.append(f"{role}: {content}")
        return "\n".join(parts)


class FTSIndex:
    """Index full-text FTS5 pour la recherche sur les sessions JSONL.

    Complémentaire au VectorIndex : FTS5 capture les correspondances exactes
    (noms propres, termes techniques, dates) que le vectoriel peut rater.
    Tokenizer unicode61 avec suppression des diacritiques pour le français.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS sessions USING fts5("
                "doc_id UNINDEXED, text, "
                "tokenize='unicode61 remove_diacritics 1'"
                ")"
            )
            conn.commit()

    # ── sync helpers (run in thread) ─────────────────────────
    def _add_sync(self, doc_id: str, text: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE doc_id = ?", (doc_id,))
            conn.execute("INSERT INTO sessions(doc_id, text) VALUES (?, ?)", (doc_id, text))
            conn.commit()

    def _remove_sync(self, doc_id: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE doc_id = ?", (doc_id,))
            conn.commit()

    def _search_sync(self, query: str, k: int) -> list[dict]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT doc_id, text, bm25(sessions) FROM sessions "
                    "WHERE sessions MATCH ? ORDER BY bm25(sessions) LIMIT ?",
                    (query, k),
                ).fetchall()
        except sqlite3.OperationalError:
            # Requête FTS5 malformée (guillemets non fermés, etc.)
            return []
        return [{"doc_id": row[0], "text": row[1], "score": float(row[2])} for row in rows]

    def _count_sync(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def _rebuild_sync(self, sessions_dir: Path) -> int:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()
        count = 0
        for jsonl in sorted(sessions_dir.glob("*.jsonl")):
            text = VectorIndex.transcript_to_text(jsonl)
            if not text.strip():
                continue
            self._add_sync(jsonl.name, text)
            count += 1
        return count

    # ── public async API ──────────────────────────────────────
    async def add(self, doc_id: str, text: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._add_sync, doc_id, text)
        logger.debug("FTSIndex.add", doc_id=doc_id)

    async def remove(self, doc_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._remove_sync, doc_id)
        logger.debug("FTSIndex.remove", doc_id=doc_id)

    async def search(self, query: str, k: int = 5) -> list[dict]:
        if not query.strip():
            return []
        return await asyncio.to_thread(self._search_sync, query, k)

    async def count(self) -> int:
        return await asyncio.to_thread(self._count_sync)

    async def is_empty(self) -> bool:
        return await self.count() == 0

    async def rebuild(self, sessions_dir: Path) -> int:
        async with self._lock:
            n = await asyncio.to_thread(self._rebuild_sync, sessions_dir)
        logger.info("FTSIndex rebuilt", docs=n, dir=str(sessions_dir))
        return n
