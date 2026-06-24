# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""briefing.py — Preset de briefing post-wakeup : ouverture Safari + récap data.

Backend = builder (résout YouTube/Notion en segments) + action (ouverture Safari).
Aucune orchestration temporelle ici : le timing/séquencement vit dans le runner
frontend (briefing.js). Les presets sont déclaratifs (registre _PRESETS).
"""

from __future__ import annotations

import asyncio
import os
import sys

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel

from jarvis.kernel.settings import settings
from jarvis.providers.youtube import get_youtube_snapshot

router = APIRouter()


def _briefing_enabled() -> bool:
    # Lu à l'exécution, PAS au niveau module : briefing.py est importé par app.py
    # avant son load_dotenv(), donc un flag figé à l'import serait toujours false.
    return os.getenv("BRIEFING_ENABLED", "false").lower() == "true"


# ── Action desktop : ouvrir une fenêtre Safari positionnée ───────────────────
# L'URL et les bounds sont passés en ARGV à osascript (on run argv), jamais
# interpolés dans la source AppleScript -> aucune injection possible.
_SAFARI_SCRIPT = """
on run argv
    set theURL to item 1 of argv
    tell application "Safari"
        activate
        make new document with properties {URL:theURL}
    end tell
    if (count of argv) is 5 then
        delay 0.35
        set x to (item 2 of argv) as integer
        set y to (item 3 of argv) as integer
        set w to (item 4 of argv) as integer
        set h to (item 5 of argv) as integer
        tell application "System Events" to tell application process "Safari"
            set position of front window to {x, y}
            set size of front window to {w, h}
        end tell
    end if
end run
"""


async def open_safari_window(url: str, bounds: list[int] | None) -> bool:
    """Ouvre une fenêtre Safari sur `url`, positionnée selon `bounds` [x,y,w,h].

    No-op + warning hors macOS (le backend doit tourner en local sur le Mac filmé).
    Le positionnement exige les permissions Automatisation + Accessibilité.
    """
    if sys.platform != "darwin":
        logger.warning("[briefing] open-url ignoré (non macOS) : {}", url)
        return False
    if not url.startswith(("https://", "http://")):
        logger.warning("[briefing] URL refusée (schéma) : {}", url)
        return False

    args = ["osascript", "-e", _SAFARI_SCRIPT, url]
    if bounds and len(bounds) == 4:
        args += [str(int(b)) for b in bounds]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("[briefing] osascript err: {}", err.decode()[:200])
            return False
        return True
    except Exception as e:
        logger.warning("[briefing] open_safari_window: {}", e)
        return False


# ── Builder de preset ─────────────────────────────────────────────────────────


def _youtube_line(yt: object) -> str:
    if yt is None:
        return ""
    name = yt.handle or "ta chaîne"  # type: ignore[attr-defined]
    line = f"Ta chaîne {name} : {yt.subscribers} abonnés."  # type: ignore[attr-defined]
    if yt.last_video_title:  # type: ignore[attr-defined]
        line += (
            f" Dernière vidéo, « {yt.last_video_title} », "  # type: ignore[attr-defined]
            f"à {yt.last_video_views} vues."  # type: ignore[attr-defined]
        )
    return line


async def _tasks_line(request: Request) -> str:
    """Narration des tâches Notion non cochées — réutilise le tool notion_tasks."""
    content = ""
    try:
        result = await request.app.state.tool_registry.call("notion_tasks", {})
        if result and not result.is_error:
            content = result.content
    except Exception as e:
        logger.warning("[briefing] notion tasks: {}", e)

    tasks = [ln[2:].strip() for ln in content.splitlines() if ln.startswith("- ")]
    if not tasks:
        return "Aucune tâche au programme aujourd'hui."
    n = len(tasks)
    head = {1: "Une tâche", 2: "Deux tâches", 3: "Trois tâches"}.get(n, f"{n} tâches")
    return f"{head} aujourd'hui : {', '.join(tasks[:3])}."


async def _build_morning(request: Request) -> list[dict]:
    """Preset matinal : intro, YouTube Studio + récap chaîne, Notion + tâches, météo."""
    yt = await get_youtube_snapshot()
    tasks_line = await _tasks_line(request)

    channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "")
    studio_url = (
        f"https://studio.youtube.com/channel/{channel_id}/analytics"
        if channel_id
        else "https://studio.youtube.com"
    )
    notion_url = os.getenv("NOTION_TASKS_URL", "")
    name = settings.display_name

    segments: list[dict] = [
        {"type": "say", "text": f"Bonjour {name}. Voici ton récapitulatif du matin."},
        {"type": "open_url", "url": studio_url, "bounds": [40, 60, 920, 980]},
    ]
    yt_line = _youtube_line(yt)
    if yt_line:
        segments.append({"type": "say", "text": yt_line})
    segments.append({"type": "wait", "ms": 400})
    if notion_url:
        segments.append(
            {"type": "open_url", "url": notion_url, "bounds": [980, 60, 900, 980]}
        )
    segments.append({"type": "say", "text": tasks_line})
    segments.append({"type": "view", "view": "weather", "params": {}, "dwell_ms": 4000})
    segments.append({"type": "say", "text": "Voilà pour la météo. Bonne journée."})
    return segments


# Registre déclaratif : ajouter un preset = ajouter une entrée (pas de if/else).
_PRESETS = {
    "morning": _build_morning,
}


async def build_preset(preset_id: str, request: Request) -> list[dict]:
    builder = _PRESETS.get(preset_id) or _PRESETS["morning"]
    return await builder(request)


# ── Routes ────────────────────────────────────────────────────────────────────


class OpenUrlBody(BaseModel):
    url: str
    bounds: list[int] | None = None


@router.post("/api/briefing/open-url")
async def briefing_open_url(body: OpenUrlBody) -> dict:
    ok = await open_safari_window(body.url, body.bounds)
    return {"ok": ok}


@router.get("/api/briefing/preset/{preset_id}")
async def briefing_preset(preset_id: str, request: Request) -> dict:
    # Si désactivé : on NE construit pas (évite les appels YouTube/Notion). Le
    # runner frontend no-op sur enabled=false.
    enabled = _briefing_enabled()
    segments = await build_preset(preset_id, request) if enabled else []
    return {"id": preset_id, "enabled": enabled, "segments": segments}
