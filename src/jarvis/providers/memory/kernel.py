"""Memory Kernel — couche d'accès SQLite source de vérité unique (CDC §6.1, §6.2).

Une base unique `memory_data/jarvis_memory.db`, quatre tables (events, facts,
fact_observations, fact_relations) + une virtual table FTS5 pour la recherche
textuelle des facts. Pas de sqlite-vec en PHASE 3 (décision : FTS5 seul pour
la pertinence — embeddings de facts reportés à PHASE 3.x si nécessaire).

API synchrone (sqlite3 stdlib) ; les appels asynchrones sont délégués à un
thread par les couches consommatrices (ingest, retrieval).

Invariants :
- On ne supprime JAMAIS un event ni un fact contredit (archive/superseded, jamais delete).
- Un fact actif ≡ status=ACTIVE.
- subject/predicate/category/object sont normalisés en lowercase et trim pour le matching.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from jarvis.providers.memory.schemas import (
    DecayPolicy,
    Event,
    Fact,
    FactObservation,
    FactRelation,
    FactStatus,
    ObservationType,
    RelationType,
)

# ── Schéma SQL ────────────────────────────────────────────────────────────────


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        source TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS facts (
        id TEXT PRIMARY KEY,
        subject TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object TEXT NOT NULL,
        category TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence REAL NOT NULL,
        support_count INTEGER NOT NULL,
        decay_policy TEXT NOT NULL,
        importance REAL NOT NULL DEFAULT 0.5,
        valid_from TEXT,
        valid_to TEXT,
        source_event_id TEXT,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (source_event_id) REFERENCES events(id)
    )
    """,
    # Index combiné (subject, predicate, category) pour le matching de réconciliation.
    """
    CREATE INDEX IF NOT EXISTS idx_facts_match
        ON facts(subject, predicate, category, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status)
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_observations (
        id TEXT PRIMARY KEY,
        fact_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        observation_type TEXT NOT NULL,
        confidence_delta REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (fact_id) REFERENCES facts(id),
        FOREIGN KEY (event_id) REFERENCES events(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_obs_fact ON fact_observations(fact_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_relations (
        id TEXT PRIMARY KEY,
        from_fact_id TEXT NOT NULL,
        to_fact_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (from_fact_id) REFERENCES facts(id),
        FOREIGN KEY (to_fact_id) REFERENCES facts(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rel_from ON fact_relations(from_fact_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rel_to ON fact_relations(to_fact_id)
    """,
    # FTS5 sur le texte concaténé d'un fact pour la pertinence retrieval.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
        fact_id UNINDEXED,
        text,
        tokenize='unicode61 remove_diacritics 1'
    )
    """,
]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def normalize(s: str) -> str:
    """Normalise un terme pour le matching (lowercase, strip)."""
    return s.strip().lower()


# ── Kernel ────────────────────────────────────────────────────────────────────


class MemoryKernel:
    """Couche d'accès SQLite. Source de vérité unique pour la mémoire structurée."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _init_schema(self) -> None:
        with self._conn() as conn:
            for stmt in _SCHEMA:
                conn.execute(stmt)
            conn.commit()
        logger.debug("MemoryKernel schema ready", path=str(self._db_path))

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Phase C §C.1.8 — accès concurrent process API + process voix :
        # - WAL : les lecteurs ne bloquent plus l'écrivain (et inversement).
        # - busy_timeout=5000 : sans ce timeout, WAL sérialise toujours les
        #   écrivains → un write concurrent voix+API échouerait avec
        #   `database is locked` au lieu d'attendre. 5s de marge.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
        finally:
            conn.close()

    # ── Events ────────────────────────────────────────────────────────────────

    def log_event(
        self,
        type: str,  # noqa: A002 — nom imposé par le contrat §6.2
        source: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Insère un event brut. Immuable — jamais supprimé."""
        evt = Event(
            id=_new_id("evt"),
            type=type,
            source=source,
            content=content,
            created_at=datetime.now(),
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events(id, type, source, content, metadata_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    evt.id,
                    evt.type,
                    evt.source,
                    evt.content,
                    evt.metadata_json,
                    evt.created_at.isoformat(),
                ),
            )
            conn.commit()
        return evt

    def get_event(self, event_id: str) -> Event | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def count_events(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    # ── Facts ─────────────────────────────────────────────────────────────────

    def insert_fact(self, fact: Fact) -> None:
        """Insère un nouveau fact. Met aussi à jour l'index FTS5."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO facts(id, subject, predicate, object, category, status, "
                "confidence, support_count, decay_policy, importance, valid_from, valid_to, "
                "source_event_id, created_at, last_seen_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact.id,
                    fact.subject,
                    fact.predicate,
                    fact.object,
                    fact.category,
                    fact.status.value,
                    fact.confidence,
                    fact.support_count,
                    fact.decay_policy.value,
                    fact.importance,
                    fact.valid_from.isoformat() if fact.valid_from else None,
                    fact.valid_to.isoformat() if fact.valid_to else None,
                    fact.source_event_id,
                    fact.created_at.isoformat(),
                    fact.last_seen_at.isoformat(),
                    fact.updated_at.isoformat(),
                ),
            )
            self._fts_upsert(conn, fact)
            conn.commit()

    def update_fact(self, fact: Fact) -> None:
        """Met à jour un fact existant + re-indexe FTS5."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE facts SET status=?, confidence=?, support_count=?, "
                "decay_policy=?, importance=?, valid_from=?, valid_to=?, "
                "last_seen_at=?, updated_at=? WHERE id=?",
                (
                    fact.status.value,
                    fact.confidence,
                    fact.support_count,
                    fact.decay_policy.value,
                    fact.importance,
                    fact.valid_from.isoformat() if fact.valid_from else None,
                    fact.valid_to.isoformat() if fact.valid_to else None,
                    fact.last_seen_at.isoformat(),
                    datetime.now().isoformat(),
                    fact.id,
                ),
            )
            self._fts_upsert(conn, fact)
            conn.commit()

    def get_fact(self, fact_id: str) -> Fact | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return self._row_to_fact(row) if row else None

    def find_active_match(self, subject: str, predicate: str, category: str) -> Fact | None:
        """Cherche un fact ACTIF avec même (subject, predicate, category) normalisés.

        Sert au matching de réconciliation §6.4 étape 4.
        """
        s, p, c = normalize(subject), normalize(predicate), normalize(category)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE subject=? AND predicate=? AND category=? "
                "AND status=? ORDER BY last_seen_at DESC LIMIT 1",
                (s, p, c, FactStatus.ACTIVE.value),
            ).fetchone()
        return self._row_to_fact(row) if row else None

    def list_facts_by_status(self, status: FactStatus, limit: int | None = None) -> list[Fact]:
        sql = "SELECT * FROM facts WHERE status=? ORDER BY last_seen_at DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        with self._conn() as conn:
            rows = conn.execute(sql, (status.value,)).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def list_facts_by_category(
        self, category: str, status: FactStatus = FactStatus.ACTIVE
    ) -> list[Fact]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE category=? AND status=? ORDER BY last_seen_at DESC",
                (normalize(category), status.value),
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def count_facts(self, status: FactStatus | None = None) -> int:
        with self._conn() as conn:
            if status is None:
                return int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM facts WHERE status=?",
                    (status.value,),
                ).fetchone()[0]
            )

    # ── Observations & Relations ──────────────────────────────────────────────

    def record_observation(
        self,
        fact_id: str,
        event_id: str,
        observation_type: ObservationType,
        confidence_delta: float,
    ) -> FactObservation:
        obs = FactObservation(
            id=_new_id("obs"),
            fact_id=fact_id,
            event_id=event_id,
            observation_type=observation_type,
            confidence_delta=confidence_delta,
            created_at=datetime.now(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO fact_observations(id, fact_id, event_id, observation_type, "
                "confidence_delta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    obs.id,
                    obs.fact_id,
                    obs.event_id,
                    obs.observation_type.value,
                    obs.confidence_delta,
                    obs.created_at.isoformat(),
                ),
            )
            conn.commit()
        return obs

    def list_observations(self, fact_id: str) -> list[FactObservation]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM fact_observations WHERE fact_id=? ORDER BY created_at",
                (fact_id,),
            ).fetchall()
        return [
            FactObservation(
                id=r["id"],
                fact_id=r["fact_id"],
                event_id=r["event_id"],
                observation_type=ObservationType(r["observation_type"]),
                confidence_delta=r["confidence_delta"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def link_facts(
        self, from_fact_id: str, to_fact_id: str, relation_type: RelationType
    ) -> FactRelation:
        rel = FactRelation(
            id=_new_id("rel"),
            from_fact_id=from_fact_id,
            to_fact_id=to_fact_id,
            relation_type=relation_type,
            created_at=datetime.now(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO fact_relations(id, from_fact_id, to_fact_id, "
                "relation_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    rel.id,
                    rel.from_fact_id,
                    rel.to_fact_id,
                    rel.relation_type.value,
                    rel.created_at.isoformat(),
                ),
            )
            conn.commit()
        return rel

    def list_relations(self, fact_id: str) -> list[FactRelation]:
        """Toutes les relations dont le fact est source OU cible."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM fact_relations "
                "WHERE from_fact_id=? OR to_fact_id=? ORDER BY created_at",
                (fact_id, fact_id),
            ).fetchall()
        return [
            FactRelation(
                id=r["id"],
                from_fact_id=r["from_fact_id"],
                to_fact_id=r["to_fact_id"],
                relation_type=RelationType(r["relation_type"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ── FTS5 ──────────────────────────────────────────────────────────────────

    def search_facts_fts(self, query: str, k: int = 10) -> list[tuple[Fact, float]]:
        """Recherche FTS5 → liste (fact, bm25_score) ; bm25 plus bas = plus pertinent."""
        if not query.strip():
            return []
        # Sanitize query for FTS5 — guillemets et caractères spéciaux peuvent casser.
        # On enveloppe en phrase pour tolérer les espaces.
        safe = '"' + query.replace('"', " ") + '"'
        with self._conn() as conn:
            try:
                rows = conn.execute(
                    "SELECT facts.*, bm25(facts_fts) AS score FROM facts_fts "
                    "JOIN facts ON facts.id = facts_fts.fact_id "
                    "WHERE facts_fts MATCH ? "
                    "ORDER BY score LIMIT ?",
                    (safe, k),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(self._row_to_fact(r), float(r["score"])) for r in rows]

    @staticmethod
    def _fts_upsert(conn: sqlite3.Connection, fact: Fact) -> None:
        """Réindexe le fact dans FTS5 (delete + insert pour gérer l'update)."""
        conn.execute("DELETE FROM facts_fts WHERE fact_id = ?", (fact.id,))
        text = " ".join(
            [
                fact.subject,
                fact.predicate,
                fact.object,
                fact.category,
            ]
        )
        conn.execute("INSERT INTO facts_fts(fact_id, text) VALUES (?, ?)", (fact.id, text))

    # ── Human correction (§6.7) ───────────────────────────────────────────────

    def apply_correction(
        self,
        target_fact_id: str,
        new_object: str | None = None,
        new_status: FactStatus | None = None,
        new_confidence: float | None = None,
        correction_text: str = "",
        source: str = "user_command",
    ) -> tuple[Event, Fact | None]:
        """Applique une correction humaine. Trace l'event, met à jour le fact.

        Renvoie (event, fact_mis_à_jour). Si target_fact_id introuvable, fact=None
        mais l'event est créé pour traçabilité.
        """
        evt = self.log_event(
            type="human_correction",
            source=source,
            content=correction_text or f"Correction du fact {target_fact_id}",
            metadata={
                "target_fact_id": target_fact_id,
                "new_object": new_object,
                "new_status": new_status.value if new_status else None,
                "new_confidence": new_confidence,
            },
        )
        fact = self.get_fact(target_fact_id)
        if fact is None:
            logger.warning("apply_correction: fact introuvable", fact_id=target_fact_id)
            return evt, None

        if new_object is not None:
            fact.object = normalize(new_object)
        if new_status is not None:
            fact.status = new_status
        if new_confidence is not None:
            fact.confidence = max(0.0, min(1.0, new_confidence))
        fact.last_seen_at = datetime.now()
        fact.updated_at = datetime.now()
        self.update_fact(fact)
        self.record_observation(
            fact_id=fact.id,
            event_id=evt.id,
            observation_type=ObservationType.CORRECT,
            confidence_delta=0.0,
        )
        return evt, fact

    # ── Row mappers ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            type=row["type"],
            source=row["source"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata_json=row["metadata_json"],
        )

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> Fact:
        return Fact(
            id=row["id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object"],
            category=row["category"],
            status=FactStatus(row["status"]),
            confidence=row["confidence"],
            support_count=row["support_count"],
            decay_policy=DecayPolicy(row["decay_policy"]),
            importance=row["importance"],
            valid_from=datetime.fromisoformat(row["valid_from"]) if row["valid_from"] else None,
            valid_to=datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
            source_event_id=row["source_event_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
