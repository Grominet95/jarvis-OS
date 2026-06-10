"""Widget Discord — membres et activité du serveur Le Labo."""

import os

import httpx

from jarvis.analytics.widgets.base import WidgetBase, WidgetData


class DiscordWidget(WidgetBase):
    id = "discord"
    label = "Discord Le Labo"
    description = "Membres actifs et activité du serveur Le Labo."
    icon = "D"
    requires_env = ["DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID"]
    size = "small"

    async def fetch(self) -> WidgetData:
        if not self.is_configured():
            return WidgetData(success=False, data={}, error="Config manquante")

        token = os.getenv("DISCORD_BOT_TOKEN")
        guild_id = os.getenv("DISCORD_GUILD_ID")

        try:
            async with httpx.AsyncClient(
                timeout=10, headers={"Authorization": f"Bot {token}"}
            ) as client:
                r = await client.get(
                    f"https://discord.com/api/v10/guilds/{guild_id}", params={"with_counts": "true"}
                )
                data = r.json()

                return WidgetData(
                    success=True,
                    data={
                        "members_total": data.get("member_count", 0),
                        "members_online": data.get("approximate_presence_count", 0),
                        "name": data.get("name", ""),
                    },
                )
        except Exception as e:
            return WidgetData(success=False, data={}, error=str(e))
