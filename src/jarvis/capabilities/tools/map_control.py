# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from collections.abc import Callable

import httpx

from jarvis.capabilities.tools.base import Tool, ToolResult

CITY_COORDS: dict[str, tuple[float, float]] = {
    "paris": (48.8566, 2.3522),
    "lyon": (45.7640, 4.8357),
    "marseille": (43.2965, 5.3698),
    "bordeaux": (44.8378, -0.5792),
    "nice": (43.7102, 7.2620),
    "toulouse": (43.6047, 1.4442),
    "strasbourg": (48.5734, 7.7521),
    "nantes": (47.2184, -1.5536),
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "tokyo": (35.6762, 139.6503),
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "london": (51.5074, -0.1278),
    "berlin": (52.5200, 13.4050),
    "madrid": (40.4168, -3.7038),
    "rome": (41.9028, 12.4964),
    "amsterdam": (52.3676, 4.9041),
    "dubai": (25.2048, 55.2708),
    "singapour": (1.3521, 103.8198),
    "mumbai": (19.0760, 72.8777),
    "sydney": (-33.8688, 151.2093),
    "sao paulo": (-23.5505, -46.6333),
    "buenos aires": (-34.6037, -58.3816),
    "moscou": (55.7558, 37.6176),
    "le caire": (30.0444, 31.2357),
    "lagos": (6.5244, 3.3792),
}


class MapControlTool(Tool):
    name = "map_control"
    description = (
        "Contrôle la carte/globe Jarvis.\n\n"
        "Utilise cet outil quand l'utilisateur demande :\n"
        '- "Montre-moi [ville]" / "Va à Tokyo" → action: fly_to, location: "ville"\n'
        '- "Zoome sur [lieu]" → action: fly_to\n'
        '- "Dézoom" / "Vue monde" → action: zoom_out\n'
        '- "Retour au globe" → action: globe_view\n'
        '- "Masque les panneaux" / "Plein écran" → action: toggle_panels\n'
        '- "Zoom avant" → action: zoom_in'
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["fly_to", "zoom_out", "zoom_in", "globe_view", "toggle_panels"],
                "description": "Action à effectuer sur la carte.",
            },
            "location": {
                "type": "string",
                "description": "Nom de la ville ou du lieu (requis pour fly_to).",
            },
            "zoom": {
                "type": "integer",
                "description": "Niveau de zoom MapLibre (2-18). Défaut : 10.",
                "default": 10,
            },
        },
        "required": ["action"],
    }

    def __init__(self, broadcast_event: Callable[[dict], None]) -> None:
        self._broadcast = broadcast_event

    async def execute(  # type: ignore[override]
        self,
        action: str,
        location: str | None = None,
        zoom: int = 10,
        **_: object,
    ) -> ToolResult:
        if action == "fly_to":
            if not location:
                return ToolResult(content="Paramètre location requis pour fly_to.", is_error=True)
            coords = await self._geocode(location)
            if not coords:
                return ToolResult(content=f"Lieu introuvable : {location}", is_error=True)
            lat, lon = coords
            self._broadcast(
                {
                    "type": "map_fly_to",
                    "lat": lat,
                    "lon": lon,
                    "zoom": max(2, min(18, zoom)),
                    "location_name": location,
                }
            )
            return ToolResult(content=f"Navigation vers {location}.")

        if action == "zoom_out":
            self._broadcast({"type": "map_zoom_out"})
            return ToolResult(content="Vue dézoomée.")

        if action == "zoom_in":
            self._broadcast({"type": "map_zoom_in"})
            return ToolResult(content="Zoom avant.")

        if action == "globe_view":
            self._broadcast({"type": "map_globe_view"})
            return ToolResult(content="Retour vue globe.")

        if action == "toggle_panels":
            self._broadcast({"type": "toggle_panels"})
            return ToolResult(content="Panneaux basculés.")

        return ToolResult(content=f"Action inconnue : {action}", is_error=True)

    async def _geocode(self, location: str) -> tuple[float, float] | None:
        key = location.lower().strip()
        if key in CITY_COORDS:
            return CITY_COORDS[key]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": location, "format": "json", "limit": 1},
                    headers={"User-Agent": "Jarvis/3.0"},
                )
                results = r.json()
                if results:
                    return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass
        return None
