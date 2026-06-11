"""Globe data API — flights (OpenSky), weather (Open-Meteo), config."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

import httpx
from fastapi import APIRouter
from loguru import logger

from jarvis.kernel.connectivity import is_offline_mode
from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/globe", tags=["globe"])

# ── Cache ──────────────────────────────────────────────────────
_FLIGHTS_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_WEATHER_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}

FLIGHTS_TTL = 60
WEATHER_TTL = 300

# ── Cities for weather ─────────────────────────────────────────
CITIES = {
    "paris": {"name": "Paris", "lat": 48.85, "lon": 2.35},
    "nyc": {"name": "New York", "lat": 40.71, "lon": -74.01},
    "tokyo": {"name": "Tokyo", "lat": 35.69, "lon": 139.69},
    "dubai": {"name": "Dubai", "lat": 25.20, "lon": 55.27},
}

WMO: dict[int, str] = {
    0: "Clair",
    1: "Dégagé",
    2: "Nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Verglas",
    51: "Bruine légère",
    53: "Bruine",
    55: "Bruine forte",
    61: "Pluie légère",
    63: "Pluie",
    65: "Pluie forte",
    71: "Neige légère",
    73: "Neige",
    75: "Neige forte",
    77: "Grains de neige",
    80: "Averses",
    81: "Averses mod.",
    82: "Averses fortes",
    85: "Averses neige",
    86: "Averses neige fortes",
    95: "Orage",
    96: "Orage+grêle",
    99: "Orage+grêle forte",
}

MAX_FLIGHTS = 2000


def _region(lat: float, lon: float) -> str:
    if lat > 15 and -140 < lon < -50:
        return "NA"
    if lat <= 20 and -85 < lon < -30:
        return "SA"
    if lat > 35 and -15 < lon < 45:
        return "EU"
    if -35 < lat <= 35 and -20 < lon < 55:
        return "AF"
    if lat > 10 and 45 < lon < 150:
        return "AS"
    if lat <= 15 and 95 < lon < 180:
        return "OC"
    return "OT"


# ── Flights — OpenSky Network (free, no auth) ──────────────────
@router.get("/flights")
async def get_flights() -> dict[str, Any]:
    now = time.time()
    if _FLIGHTS_CACHE["data"] and now - _FLIGHTS_CACHE["ts"] < FLIGHTS_TTL:
        return _FLIGHTS_CACHE["data"]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://opensky-network.org/api/states/all")
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        if is_offline_mode():
            logger.debug(f"OpenSky ignoré — mode local ({type(exc).__name__})")
        else:
            logger.warning(f"OpenSky fetch failed: {exc}")
        return _FLIGHTS_CACHE["data"] or {"flights": [], "total": 0}

    states = data.get("states") or []
    flights = []
    for s in states:
        if s[5] is None or s[6] is None or s[8]:
            continue
        callsign = (s[1] or "").strip() or s[0] or "???"
        alt_m = round(s[7] or 0)
        speed_kh = round((s[9] or 0) * 3.6)
        heading = round(s[10] or 0) if s[10] is not None else 0
        flights.append(
            {
                "callsign": callsign,
                "lat": round(s[6], 4),
                "lon": round(s[5], 4),
                "alt": alt_m,
                "speed": speed_kh,
                "heading": heading,
                "country": s[2] or "—",
            }
        )

    import random as _rnd

    # Air France (AFR): inclus sans filtre d'altitude (suivi possible décollage/approche)
    af_flights = [f for f in flights if f["callsign"].startswith("AFR")]
    # Autres vols : seulement en croisière pour éviter le bruit au sol
    other_flights = [f for f in flights if not f["callsign"].startswith("AFR") and f["alt"] > 3000]

    # Fill remaining slots with round-robin geographic spread
    buckets: dict[str, list] = defaultdict(list)
    for f in other_flights:
        buckets[_region(f["lat"], f["lon"])].append(f)
    for v in buckets.values():
        _rnd.shuffle(v)

    remaining = MAX_FLIGHTS - len(af_flights)
    geo_flights: list = []
    pools = [v for v in buckets.values() if v]
    i = 0
    while len(geo_flights) < remaining and pools:
        idx = i % len(pools)
        if pools[idx]:
            geo_flights.append(pools[idx].pop())
        else:
            pools.pop(idx)
            i = max(0, i - 1)
        i += 1

    _rnd.shuffle(geo_flights)
    result_flights = af_flights + geo_flights
    result = {"flights": result_flights, "total": len(flights)}
    _FLIGHTS_CACHE.update({"data": result, "ts": now})
    logger.info(
        "OpenSky: %d vols, %d affichés (%d Air France + %d autres)",
        len(flights),
        len(result_flights),
        len(af_flights),
        len(geo_flights),
    )
    return result


# ── Weather — Open-Meteo (free, no auth) ───────────────────────
@router.get("/weather")
async def get_weather() -> dict[str, Any]:
    now = time.time()
    if _WEATHER_CACHE["data"] and now - _WEATHER_CACHE["ts"] < WEATHER_TTL:
        return _WEATHER_CACHE["data"]

    async def _fetch_city(
        key: str, city: dict[str, Any], client: httpx.AsyncClient
    ) -> tuple[str, dict]:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={city['lat']}&longitude={city['lon']}"
            "&current=temperature_2m,weathercode&timezone=auto"
        )
        try:
            r = await client.get(url)
            r.raise_for_status()
            cur = r.json()["current"]
            return key, {
                "name": city["name"],
                "lat": city["lat"],
                "lon": city["lon"],
                "temp": round(cur["temperature_2m"]),
                "code": cur["weathercode"],
                "desc": WMO.get(cur["weathercode"], "—"),
            }
        except Exception:
            return key, {
                "name": city["name"],
                "lat": city["lat"],
                "lon": city["lon"],
                "temp": None,
                "code": 0,
                "desc": "—",
            }

    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [_fetch_city(k, v, client) for k, v in CITIES.items()]
        pairs = await asyncio.gather(*tasks)

    cities = dict(pairs)
    result = {"cities": cities}
    _WEATHER_CACHE.update({"data": result, "ts": now})
    return result


# ── Config — expose public keys to frontend ────────────────────
@router.get("/config")
async def get_config() -> dict[str, Any]:
    return {
        "aisstream_key": settings.aisstream_key or "",
        "maptiler_key": settings.maptiler_key or "",
        "mapbox_token": settings.mapbox_token or "",
    }
