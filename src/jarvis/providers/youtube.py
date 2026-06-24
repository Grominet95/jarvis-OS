# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""youtube.py — Snapshot YouTube (Data API v3, clé seule) pour le briefing.

Distinct du widget analytics (analytics/widgets/youtube.py) : ce module fournit
les vues de la *dernière vidéo* (que le widget ne récupère pas) et un dataclass
simple consommé par le builder de preset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from loguru import logger

_API = "https://www.googleapis.com/youtube/v3"

# Snapshot quotidien (delta hebdo "+47 cette semaine") : la Data API ne donne pas
# l'évolution. TODO v2 — écrire data/youtube_snapshot.json chaque jour et comparer,
# ou passer par l'API Analytics (OAuth). v1 : abonnés courants + vues dernière vidéo.


@dataclass
class YouTubeSnapshot:
    handle: str
    subscribers: int
    total_views: int
    video_count: int
    last_video_title: str
    last_video_views: int
    last_video_url: str


async def get_youtube_snapshot() -> YouTubeSnapshot | None:
    """Instantané de la chaîne via la YouTube Data API v3.

    Retourne None si non configuré (clé/channel manquants) ou en cas d'erreur —
    le builder de preset omet alors simplement le segment YouTube.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not api_key or not channel_id:
        logger.warning("[briefing] YouTube non configuré (YOUTUBE_API_KEY/CHANNEL_ID)")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            ch = (
                await client.get(
                    f"{_API}/channels",
                    params={
                        "part": "statistics,contentDetails,snippet",
                        "id": channel_id,
                        "key": api_key,
                    },
                )
            ).json()
            item = ch["items"][0]
            stats = item["statistics"]
            snippet = item.get("snippet", {})
            uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
            handle = (snippet.get("customUrl") or snippet.get("title") or "").lstrip("@")

            # Dernière vidéo : playlist "uploads" -> videoId -> stats + titre.
            last_title, last_views, last_url = "", 0, ""
            pl = (
                await client.get(
                    f"{_API}/playlistItems",
                    params={
                        "part": "contentDetails",
                        "playlistId": uploads,
                        "maxResults": 1,
                        "key": api_key,
                    },
                )
            ).json()
            pl_items = pl.get("items", [])
            if pl_items:
                vid = pl_items[0]["contentDetails"]["videoId"]
                last_url = f"https://youtu.be/{vid}"
                vd = (
                    await client.get(
                        f"{_API}/videos",
                        params={"part": "statistics,snippet", "id": vid, "key": api_key},
                    )
                ).json()
                vitems = vd.get("items", [])
                if vitems:
                    last_title = vitems[0]["snippet"]["title"]
                    last_views = int(vitems[0]["statistics"].get("viewCount", 0))

            return YouTubeSnapshot(
                handle=handle,
                subscribers=int(stats.get("subscriberCount", 0)),
                total_views=int(stats.get("viewCount", 0)),
                video_count=int(stats.get("videoCount", 0)),
                last_video_title=last_title,
                last_video_views=last_views,
                last_video_url=last_url,
            )
    except Exception as e:
        logger.warning("[briefing] get_youtube_snapshot: {}", e)
        return None
