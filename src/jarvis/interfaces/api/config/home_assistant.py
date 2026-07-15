# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from fastapi import APIRouter
from pydantic import BaseModel
import os

router = APIRouter(prefix="/config/home_assistant", tags=["config"])

class HAConfig(BaseModel):
    url: str
    token: str

@router.post("/save")
async def save_ha_config(config: HAConfig):
    os.environ["HA_URL"] = config.url.rstrip("/")
    os.environ["HA_TOKEN"] = config.token
    return {"status": "success", "message": "Configuration Home Assistant sauvegardée"}

@router.get("/status")
async def ha_status():
    return {
        "configured": bool(os.getenv("HA_TOKEN")),
        "url": os.getenv("HA_URL", "non configuré")
    }
