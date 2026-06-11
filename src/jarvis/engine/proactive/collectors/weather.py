from __future__ import annotations

from datetime import datetime

import httpx
from loguru import logger

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.connectivity import is_offline_mode
from jarvis.kernel.settings import settings


class WeatherCollector(CollectorBase):
    """Prévisions météo 24h via Open-Meteo (gratuit, sans clé)."""

    name = "weather"

    async def _collect(self) -> list[ContextItem]:
        if is_offline_mode():
            logger.debug("WeatherCollector ignoré — mode local")
            return []

        lat = settings.proactive_lat
        lon = settings.proactive_lon
        city = settings.proactive_city

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=precipitation_probability,temperature_2m,weathercode"
            f"&forecast_days=1"
            f"&timezone=Europe%2FParis"
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"WeatherCollector: HTTP {response.status_code}")
                return []

        data = response.json()
        hourly = data.get("hourly", {})

        times = hourly.get("time", [])
        precip = hourly.get("precipitation_probability", [])
        temps = hourly.get("temperature_2m", [])

        # Heures avec forte probabilité de pluie (> 60%)
        rain_alerts: list[str] = []
        for t, p, temp in zip(times, precip, temps, strict=False):
            if p and p > 60:
                rain_alerts.append(f"{t[-5:]} : {p}% pluie, {temp}°C")

        if not rain_alerts:
            summary = f"Pas de pluie prévue à {city} dans les 24h."
            priority = Priority.LOW
        else:
            summary = f"Pluie probable à {city} : " + ", ".join(rain_alerts[:4])
            priority = Priority.MEDIUM

        return [
            ContextItem(
                type=ItemType.NEWS,
                title=f"Météo {city} — 24h",
                summary=summary,
                raw=summary,
                source="weather",
                timestamp=datetime.now(),
                priority=priority,
                metadata={
                    "rain_hours": rain_alerts,
                    "lat": lat,
                    "lon": lon,
                    "city": city,
                },
            )
        ]
