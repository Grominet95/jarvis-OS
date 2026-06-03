from __future__ import annotations

from collections.abc import Callable

import httpx

from tools.base import Tool, ToolResult

CITY_COORDS: dict[str, tuple[float, float]] = {
    # Villes françaises
    "paris": (48.8566, 2.3522),
    "lyon": (45.7640, 4.8357),
    "marseille": (43.2965, 5.3698),
    "bordeaux": (44.8378, -0.5792),
    "nice": (43.7102, 7.2620),
    "toulouse": (43.6047, 1.4442),
    "strasbourg": (48.5734, 7.7521),
    "nantes": (47.2184, -1.5536),
    "saint-lunaire": (48.6340, -2.1270),
    "rennes": (48.1173, -1.6778),
    "lille": (50.6292, 3.0573),
    # Monuments / lieux précis
    "tour eiffel": (48.8584, 2.2945),
    "eiffel tower": (48.8584, 2.2945),
    "arc de triomphe": (48.8738, 2.2950),
    "notre-dame": (48.8530, 2.3499),
    "sacré-cœur": (48.8867, 2.3431),
    "louvre": (48.8606, 2.3376),
    "notre dame": (48.8530, 2.3499),
    "colosseum": (41.8902, 12.4922),
    "colisée": (41.8902, 12.4922),
    "statue of liberty": (40.6892, -74.0445),
    "burj khalifa": (25.1972, 55.2744),
    "eiffel": (48.8584, 2.2945),
    # Villes internationales
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "tokyo": (35.6762, 139.6503),
    "beijing": (39.9042, 116.4074),
    "london": (51.5074, -0.1278),
    "londres": (51.5074, -0.1278),
    "berlin": (52.5200, 13.4050),
    "madrid": (40.4168, -3.7038),
    "rome": (41.9028, 12.4964),
    "dubai": (25.2048, 55.2708),
    "sydney": (-33.8688, 151.2093),
    "moscou": (55.7558, 37.6176),
    "moscow": (55.7558, 37.6176),
    "pékin": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "singapour": (1.3521, 103.8198),
    "singapore": (1.3521, 103.8198),
    "seoul": (37.5665, 126.9780),
    "séoul": (37.5665, 126.9780),
    "toronto": (43.6532, -79.3832),
    "montréal": (45.5017, -73.5673),
    "montreal": (45.5017, -73.5673),
    "mexico": (19.4326, -99.1332),
    "bangkok": (13.7563, 100.5018),
    "amsterdam": (52.3676, 4.9041),
    "vienne": (48.2082, 16.3738),
    "vienna": (48.2082, 16.3738),
    "prague": (50.0755, 14.4378),
    "istanbul": (41.0082, 28.9784),
    "le caire": (30.0444, 31.2357),
    "cairo": (30.0444, 31.2357),
    "johannesburg": (-26.2041, 28.0473),
    "nairobi": (-1.2921, 36.8219),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
}


class ShowViewTool(Tool):
    name = "show_view"
    description = (
        "Affiche ou contrôle une vue visuelle sur l'écran principal de Jarvis.\n\n"
        "Utilise cet outil quand l'utilisateur demande :\n"
        '- Afficher une vue par son ID → action: show, view_id: "<id>"\n'
        '  Le SYSTEM_PROMPT de chaque vue installée indique son view_id exact.\n'
        '- Masquer une vue → action: hide, view_id: "<id>"\n'
        "- Cite un lieu, une ville, un monument → action: fly_to, location: ...\n"
        '  Exemples: "montre Lyon", "va à Tokyo", "montre la tour Eiffel"\n'
        "  Zoom recommandé: ville=10, monument/quartier=16, pays/continent=5\n"
        "  IMPORTANT: si un lieu est mentionné, toujours utiliser fly_to, pas show.\n"
        '- "Vue globale" / "dézoom total" → action: globe_view\n'
        '- "Zoom avant" / "plus proche" → action: zoom_in\n'
        '- "Dézoom" / "recule" → action: zoom_out\n\n'
        "Pour fly_to, le globe s'affiche automatiquement avant la navigation."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["show", "hide", "fly_to", "zoom_out", "zoom_in", "globe_view"],
                "description": "Action à effectuer.",
            },
            "view_id": {
                "type": "string",
                "description": "ID de la vue (défaut: globe).",
                "default": "globe",
            },
            "location": {
                "type": "string",
                "description": "Nom du lieu à afficher (requis pour fly_to).",
            },
            "zoom": {
                "type": "integer",
                "description": (
                    "Niveau de zoom (2–18)."
                    " Villes: 10, monuments/quartiers: 15–16, pays: 5, continent: 3."
                ),
                "default": 10,
            },
        },
        "required": ["action"],
    }

    def __init__(self, broadcast_event: Callable[[dict], None]) -> None:
        self._broadcast = broadcast_event

    async def execute(
        self,
        action: str,
        view_id: str = "globe",
        location: str | None = None,
        zoom: int = 10,
        **_: object,
    ) -> ToolResult:
        if action == "show":
            self._broadcast({"type": "show_view", "view_id": view_id})
            return ToolResult(content=f"Vue {view_id} affichée.")

        if action == "hide":
            self._broadcast({"type": "hide_view", "view_id": view_id})
            return ToolResult(content=f"Vue {view_id} masquée.")

        if action == "fly_to":
            if not location:
                return ToolResult(content="Paramètre location requis pour fly_to.", is_error=True)
            coords = await self._geocode(location)
            if not coords:
                return ToolResult(content=f"Lieu introuvable : {location}", is_error=True)
            lat, lon = coords
            self._broadcast({"type": "show_view", "view_id": "globe"})
            self._broadcast(
                {
                    "type": "view_command",
                    "view_id": "globe",
                    "command": "fly_to",
                    "params": {
                        "lat": lat,
                        "lon": lon,
                        "zoom": max(2, min(18, zoom)),
                        "location_name": location,
                    },
                }
            )
            return ToolResult(content=f"Navigation vers {location}.")

        if action == "zoom_out":
            self._broadcast(
                {"type": "view_command", "view_id": "globe", "command": "zoom_out", "params": {}}
            )
            return ToolResult(content="Vue dézoomée.")

        if action == "zoom_in":
            self._broadcast(
                {"type": "view_command", "view_id": "globe", "command": "zoom_in", "params": {}}
            )
            return ToolResult(content="Zoom avant.")

        if action == "globe_view":
            self._broadcast({"type": "show_view", "view_id": "globe"})
            self._broadcast(
                {"type": "view_command", "view_id": "globe", "command": "globe_view", "params": {}}
            )
            return ToolResult(content="Vue globe globale.")

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
