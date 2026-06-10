"""Widget YouTube Analytics — nécessite YOUTUBE_API_KEY."""

import os

import httpx

from jarvis.analytics.widgets.base import WidgetBase, WidgetData


class YouTubeWidget(WidgetBase):
    id = "youtube"
    label = "YouTube Analytics"
    description = "Vues, abonnés et performances via YouTube Data API v3."
    icon = "Y"
    requires_env = ["YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID"]
    size = "large"

    async def fetch(self) -> WidgetData:
        if not self.is_configured():
            return WidgetData(
                success=False, data={}, error="YOUTUBE_API_KEY ou YOUTUBE_CHANNEL_ID manquant"
            )

        api_key = os.getenv("YOUTUBE_API_KEY")
        channel_id = os.getenv("YOUTUBE_CHANNEL_ID")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Stats de la chaîne
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "statistics,snippet", "id": channel_id, "key": api_key},
                )
                channel_data = r.json()
                stats = channel_data["items"][0]["statistics"]

                # Dernières vidéos
                r2 = await client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "channelId": channel_id,
                        "order": "date",
                        "maxResults": 5,
                        "type": "video",
                        "key": api_key,
                    },
                )
                videos_data = r2.json()

                return WidgetData(
                    success=True,
                    data={
                        "subscribers": int(stats.get("subscriberCount", 0)),
                        "total_views": int(stats.get("viewCount", 0)),
                        "video_count": int(stats.get("videoCount", 0)),
                        "recent_videos": [
                            {
                                "title": v["snippet"]["title"],
                                "published": v["snippet"]["publishedAt"][:10],
                                "video_id": v["id"]["videoId"],
                            }
                            for v in videos_data.get("items", [])
                        ],
                    },
                )
        except Exception as e:
            return WidgetData(success=False, data={}, error=str(e))
