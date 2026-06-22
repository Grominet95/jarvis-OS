# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from uuid import UUID

from jarvis.kernel.contracts import SessionStore
from jarvis.kernel.schemas import Session

# Re-export pour compat des call-sites historiques (`from jarvis.engine
# .session import Session`). Phase F : la dataclass est descendue en
# kernel.schemas pour permettre à capabilities/ de l'instancier sans
# violer RÈGLE 2 (capabilities n'importe que kernel).
__all__ = ["Session", "SessionManager"]


class SessionManager:
    """Registre en mémoire des sessions actives, avec restauration depuis JSONL.

    Phase C : `store` est typé sur le Protocol `jarvis.kernel.contracts
    .SessionStore` (CDC §A.1.3), pas sur l'implémentation concrète
    `jarvis.providers.memory.sessions.SessionStore`. Le manager dépend
    du CONTRAT, pas du fournisseur — c'est la règle d'or n°3 du CDC
    (engine ne dépend que du kernel ; reçoit ses providers par injection).

    Conséquences :
    - Plus aucun `from jarvis.providers.memory.sessions import SessionStore`
      en local dans `_try_restore` / `_attach_store` (les anciens imports
      différés masquaient un cycle engine ↔ providers).
    - Plus de `isinstance(self._store, SessionStore)` runtime check — le
      type est garanti par la signature.
    - Le manager fonctionne avec toute implémentation conforme au Protocol
      (utile pour les tests : un FakeSessionStore suffit).
    """

    def __init__(self, store: SessionStore | None = None) -> None:
        self._sessions: dict[str, Session] = {}
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
        """Tente de restaurer une session depuis le store. Retourne None si introuvable."""
        if self._store is None:
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
        if self._store is None:
            return
        store = self._store  # capture pour la closure (mypy/typing)
        session.set_persist(lambda role, content: store.append(sid, role, content))

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())
