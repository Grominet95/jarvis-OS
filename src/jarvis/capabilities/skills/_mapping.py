# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from loguru import logger

# Mapping des noms d'outils OpenClaw → équivalents Jarvis
TOOL_MAP: dict[str, str] = {
    "exec": "run_script",
    "cli": "run_script",
    "web_search": "browser",
    "browser": "browser",
    "llm_task": "background",
    "apply_patch": "run_script",
    "read_file": "filesystem",
    "write_file": "run_script",
    "calendar": "calendar_list",
    "notion": "notion_tasks",
    "spotify": "spotify",
    "weather": "weather",
}

# Outils OpenClaw non encore supportés — warning au chargement
UNSUPPORTED = {
    "image_generation",
    "music_generation",
    "video_generation",
    "voice_generation",
    "docker",
}


def resolve_tool(openclaw_tool: str) -> str | None:
    """Retourne le nom Jarvis correspondant à un outil OpenClaw, ou None si non supporté."""
    if openclaw_tool in UNSUPPORTED:
        logger.warning("Outil OpenClaw non supporté", tool=openclaw_tool)
        return None
    mapped = TOOL_MAP.get(openclaw_tool)
    if mapped is None:
        logger.debug("Outil OpenClaw inconnu — pas de mapping", tool=openclaw_tool)
    return mapped
