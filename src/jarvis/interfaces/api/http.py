from __future__ import annotations

from fastapi import APIRouter

from jarvis.interfaces.api.analytics import router as _analytics_router
from jarvis.interfaces.api.chat import router as _chat_router
from jarvis.interfaces.api.config import router as _config_router

# _log_sink est défini dans http_logs et réexporté ici pour main.py.
from jarvis.interfaces.api.logs import _log_sink  # noqa: F401
from jarvis.interfaces.api.logs import router as _logs_router
from jarvis.interfaces.api.memory import router as _memory_router
from jarvis.interfaces.api.proactive import router as _proactive_router
from jarvis.interfaces.api.sessions import router as _sessions_router
from jarvis.interfaces.api.skills import router as _skills_router
from jarvis.interfaces.api.system import router as _system_router
from jarvis.interfaces.api.ui import router as _ui_router
from jarvis.interfaces.api.vision import router as _vision_router

router = APIRouter()
router.include_router(_ui_router)
router.include_router(_logs_router)
router.include_router(_system_router)
router.include_router(_sessions_router)
router.include_router(_memory_router)
router.include_router(_skills_router)
router.include_router(_config_router)
router.include_router(_proactive_router)
router.include_router(_vision_router)
router.include_router(_chat_router)
router.include_router(_analytics_router)
