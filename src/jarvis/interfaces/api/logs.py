from __future__ import annotations

from collections import deque

from fastapi import APIRouter

# ── Anneau de logs en mémoire (sink branché dans main.py) ────────────────────
_log_buffer: deque[str] = deque(maxlen=120)


def _log_sink(message: object) -> None:  # loguru message object
    _log_buffer.append(str(message).strip())


router = APIRouter()


@router.get("/api/system/logs")
async def system_logs() -> list[str]:
    """Retourne les derniers logs Jarvis (ring buffer 120 entrées)."""
    return list(_log_buffer)
