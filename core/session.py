from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass
class Session:
    """Une conversation thématique : UUID + historique + persist callback."""

    id: UUID = field(default_factory=uuid4)
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Callback appelé à chaque add_message pour la persistance JSONL.
    # init=False : non inclus dans __init__, positionné par SessionManager.
    _persist: Callable[[str, str], None] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def set_persist(self, callback: Callable[[str, str], None]) -> None:
        self._persist = callback

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        if self._persist:
            self._persist(role, content)


class SessionManager:
    """Registre en mémoire des sessions actives, avec restauration depuis JSONL."""

    def __init__(self, store: object | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        # store est un SessionStore — on accepte object pour éviter l'import circulaire
        self._store = store

    def get_or_create(self, session_id: str | None = None) -> Session:
        """Retourne la session existante (mémoire ou JSONL) ou en crée une nouvelle."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        if session_id and self._store is not None:
            session = self._try_restore(session_id)
            if session:
                return session

        return self._new_session()

    def _try_restore(self, session_id: str) -> Session | None:
        """Tente de restaurer une session depuis le JSONL. Retourne None si introuvable."""
        from jarvis.providers.memory.sessions import SessionStore  # import local pour éviter le cycle

        if not isinstance(self._store, SessionStore):
            return None

        messages = self._store.load(session_id)
        if not messages:
            return None

        try:
            session = Session(id=UUID(session_id))
        except ValueError:
            return None

        session.messages = messages
        sid = str(session.id)
        self._attach_store(session, sid)
        self._sessions[sid] = session
        return session

    def _new_session(self) -> Session:
        session = Session()
        sid = str(session.id)
        self._attach_store(session, sid)
        self._sessions[sid] = session
        return session

    def _attach_store(self, session: Session, sid: str) -> None:
        if self._store is not None:
            from jarvis.providers.memory.sessions import SessionStore

            if isinstance(self._store, SessionStore):
                session.set_persist(lambda role, content: self._store.append(sid, role, content))  # type: ignore[union-attr]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())
