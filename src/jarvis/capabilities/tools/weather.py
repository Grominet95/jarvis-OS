from __future__ import annotations

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult


class WeatherTool(Tool):
    """Météo actuelle via wttr.in — aucune clé API requise."""

    name = "get_weather"
    description = (
        "Obtient la météo actuelle pour une ville. "
        "Utilise cet outil quand l'utilisateur demande la météo, la température ou le temps qu'il fait."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "Nom de la ville (français ou anglais)",
            },
        },
        "required": ["city"],
    }

    async def execute(self, city: str, **_: object) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"https://wttr.in/{city}?format=3&lang=fr")
                r.raise_for_status()
                logger.debug("Weather fetched", city=city)
                return ToolResult(content=r.text.strip())
        except httpx.HTTPError as e:
            return ToolResult(content=f"Météo indisponible pour {city}: {e}", is_error=True)
