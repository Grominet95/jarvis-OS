from bridges.python.src.sdk.memory import Memory
from typing import TypedDict, NotRequired


class Session(TypedDict):
    question: str
    progression: float
    step: int
    session: str
    signature: str
    lang: str
    theme: str
    sid: int
    cm: bool


session_memory = Memory({
    'name': 'session',
    'default_memory': None
})


def upsert_session(session: Session) -> None:
    """Save progress/info about the session"""

    session_memory.write(session)


def get_session() -> Session:
    """Get current session progress data"""

    return session_memory.read()
