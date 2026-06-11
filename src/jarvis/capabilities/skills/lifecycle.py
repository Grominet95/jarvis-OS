"""Cycle de vie d'une skill (CDC §7.2) — persisté SQLite dans jarvis_memory.db.

Analogue mémoire procédurale aux facts de la PHASE 3 : status + confidence +
support_count + last_used_at. Une skill non utilisée passe `stale` puis
`archived` (le passage `stale → archived` sera décidé par le Curator PHASE 6 ;
ici on expose les transitions).

Source de vérité unique : table `skills` dans `memory_data/jarvis_memory.db`
(la même DB que le MemoryKernel — cohérent pour le Curator qui requêtera facts
+ skills + audit dans la même base).

Important : ce module gère le LIFECYCLE persistant. Le chargement des
instances Python depuis `skills/installed/{name}/skill.py` reste la
responsabilité de [skills/registry.py:SkillRegistry] — pas de mélange.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from loguru import logger

# Initialisation paresseuse — confidence initiale d'une skill juste promue.
# SkillStatus et SkillRecord ont été descendus en kernel.schemas en Phase D
# pour permettre à `engine/` de les référencer sans importer depuis
# `capabilities/` (RÈGLE 3). Re-export ici pour compat des call-sites.
from jarvis.kernel.schemas import (
    CONFIDENCE_INITIAL,
    SkillRecord,
    SkillStatus,
)

_TERMINAL_STATUSES: frozenset[SkillStatus] = frozenset(
    {SkillStatus.ARCHIVED, SkillStatus.REJECTED, SkillStatus.SANDBOXED_FAIL}
)


# ── Schéma SQL ────────────────────────────────────────────────────────────────


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS skills (
        name TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.6,
        support_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT,
        source_event_id TEXT,
        sandbox_notes TEXT,
        created_at TEXT NOT NULL,
        promoted_at TEXT,
        archived_at TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status)",
    "CREATE INDEX IF NOT EXISTS idx_skills_source_evt ON skills(source_event_id)",
]


class SkillLifecycle:
    """Couche d'accès au cycle de vie skill, SQLite, partagée avec le Kernel.

    Si `db_path` pointe vers la même DB que MemoryKernel, on partage la base —
    aucune table de conflit (les noms `skills`/`events`/`facts` sont distincts).
    """

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
        logger.debug("SkillLifecycle schema ready", path=str(self._db_path))

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ── Création & lookup ─────────────────────────────────────────────────────

    def create_candidate(
        self,
        name: str,
        source_event_id: str | None = None,
    ) -> SkillRecord:
        """Insère une skill en statut CANDIDATE. Idempotent : si la skill existe
        déjà, renvoie l'enregistrement existant sans le modifier (le caller doit
        check l'existence avant de re-générer pour éviter d'écraser un travail
        antérieur)."""
        existing = self.get(name)
        if existing is not None:
            return existing
        now = datetime.now()
        record = SkillRecord(
            name=name,
            status=SkillStatus.CANDIDATE,
            source_event_id=source_event_id,
            created_at=now,
            updated_at=now,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO skills(name, status, confidence, support_count, "
                "source_event_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.name,
                    record.status.value,
                    record.confidence,
                    record.support_count,
                    record.source_event_id,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            conn.commit()
        return record

    def get(self, name: str) -> SkillRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM skills WHERE name = ?", (name,)).fetchone()
        return self._row_to_record(row) if row else None

    def list_by_status(self, status: SkillStatus) -> list[SkillRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status = ? ORDER BY updated_at DESC",
                (status.value,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_all(self) -> list[SkillRecord]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM skills ORDER BY updated_at DESC").fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_by_status(self, status: SkillStatus) -> int:
        with self._conn() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM skills WHERE status = ?", (status.value,)
                ).fetchone()[0]
            )

    def has_been_proposed_for_event(self, source_event_id: str) -> bool:
        """Une skill (candidate ou promue) a-t-elle déjà été proposée pour cet event ?

        Sert à rendre le polling idempotent : on ne re-génère pas pour un event
        déjà traité.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM skills WHERE source_event_id = ? LIMIT 1",
                (source_event_id,),
            ).fetchone()
        return row is not None

    # ── Transitions de status ─────────────────────────────────────────────────

    def mark_sandbox_result(
        self,
        name: str,
        passed: bool,
        notes: str,
    ) -> SkillRecord | None:
        """Après le test sandbox : SANDBOXED_PASS (test vert, attend humain) OU
        SANDBOXED_FAIL (test rouge, rejet auto, audit conservé)."""
        new_status = SkillStatus.SANDBOXED_PASS if passed else SkillStatus.SANDBOXED_FAIL
        return self._update_status(name, new_status, sandbox_notes=notes[:1000])

    def promote(self, name: str) -> SkillRecord | None:
        """Validation humaine accordée → ACTIVE + promoted_at timestamp."""
        now = datetime.now()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE skills SET status = ?, promoted_at = ?, updated_at = ? WHERE name = ?",
                (
                    SkillStatus.ACTIVE.value,
                    now.isoformat(),
                    now.isoformat(),
                    name,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        logger.info("Skill promoted to ACTIVE", name=name)
        return self.get(name)

    def reject(self, name: str, reason: str = "") -> SkillRecord | None:
        """Validation humaine refusée → REJECTED. La candidate sur disque reste
        pour audit (le caller décide si elle supprime le dossier candidates/)."""
        notes = (reason or "rejected by user")[:1000]
        return self._update_status(name, SkillStatus.REJECTED, sandbox_notes=notes)

    def mark_used(self, name: str) -> SkillRecord | None:
        """À appeler quand la skill est consommée : support_count++, last_used_at = now.

        Si la skill était STALE, elle revient à ACTIVE (signal de réactivation).
        Confidence += 0.05 cap 0.99 (analogue du CONFIRM_DELTA du Kernel).
        """
        now = datetime.now()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE skills SET "
                "support_count = support_count + 1, "
                "last_used_at = ?, "
                "confidence = MIN(0.99, confidence + 0.05), "
                "status = CASE WHEN status = ? THEN ? ELSE status END, "
                "updated_at = ? "
                "WHERE name = ?",
                (
                    now.isoformat(),
                    SkillStatus.STALE.value,
                    SkillStatus.ACTIVE.value,
                    now.isoformat(),
                    name,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get(name)

    def mark_stale(self, name: str) -> SkillRecord | None:
        """Curator (PHASE 6) : skill ACTIVE non utilisée X jours → STALE."""
        return self._update_status(name, SkillStatus.STALE)

    def archive(self, name: str) -> SkillRecord | None:
        """Curator (PHASE 6) : skill STALE depuis trop longtemps → ARCHIVED."""
        now = datetime.now()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE skills SET status = ?, archived_at = ?, updated_at = ? WHERE name = ?",
                (
                    SkillStatus.ARCHIVED.value,
                    now.isoformat(),
                    now.isoformat(),
                    name,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        logger.info("Skill archived", name=name)
        return self.get(name)

    def _update_status(
        self,
        name: str,
        new_status: SkillStatus,
        sandbox_notes: str | None = None,
    ) -> SkillRecord | None:
        now = datetime.now()
        with self._conn() as conn:
            if sandbox_notes is not None:
                cur = conn.execute(
                    "UPDATE skills SET status = ?, sandbox_notes = ?, "
                    "updated_at = ? WHERE name = ?",
                    (new_status.value, sandbox_notes, now.isoformat(), name),
                )
            else:
                cur = conn.execute(
                    "UPDATE skills SET status = ?, updated_at = ? WHERE name = ?",
                    (new_status.value, now.isoformat(), name),
                )
            conn.commit()
            if cur.rowcount == 0:
                return None
        logger.debug("Skill status changed", name=name, status=new_status.value)
        return self.get(name)

    # ── Mappers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SkillRecord:
        return SkillRecord(
            name=row["name"],
            status=SkillStatus(row["status"]),
            confidence=row["confidence"],
            support_count=row["support_count"],
            last_used_at=datetime.fromisoformat(row["last_used_at"])
            if row["last_used_at"]
            else None,
            source_event_id=row["source_event_id"],
            sandbox_notes=row["sandbox_notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            promoted_at=datetime.fromisoformat(row["promoted_at"]) if row["promoted_at"] else None,
            archived_at=datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


__all__ = [
    "CONFIDENCE_INITIAL",
    "SkillLifecycle",
    "SkillRecord",
    "SkillStatus",
    "_TERMINAL_STATUSES",
]
