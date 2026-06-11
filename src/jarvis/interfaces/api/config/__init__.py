"""Config API — agrégat des 4 sous-modules (Phase E §E.1.3).

Le monolithe `interfaces/api/http_config.py` (936 l.) est scindé ici :
  - `settings.py`    : /api/settings/* (env-status, GET, update, voices, test-key)
  - `devices.py`     : /api/settings/devices + /api/settings/connectors
  - `llm.py`         : /api/config/llm-status + /api/ollama/{models,pull}
  - `permissions.py` : /api/permissions/* + /api/approvals/*
  - `_env.py`        : helpers .env partagés (privé)

Aucun fichier > 600 lignes (gate E3). Routes identiques par construction
— les chemins absolus dans @router restent intacts (gate E2b).

Le router exporté ici est le ré-aggréga des 4 sous-routers ; il prend la
place de `http_config.router` partout où le bootstrap monte l'API.
"""

from __future__ import annotations

from fastapi import APIRouter

from jarvis.interfaces.api.config.devices import router as _devices_router
from jarvis.interfaces.api.config.llm import router as _llm_router
from jarvis.interfaces.api.config.permissions import router as _permissions_router
from jarvis.interfaces.api.config.settings import router as _settings_router

router = APIRouter()
router.include_router(_settings_router)
router.include_router(_devices_router)
router.include_router(_llm_router)
router.include_router(_permissions_router)
