from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import json


@dataclass
class UsageEntry:
    timestamp: str
    provider: str          # "anthropic", "elevenlabs", "openai", "deepgram"
    model: str             # "claude-sonnet-4-6", "eleven_turbo_v2_5", etc.
    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0    # Pour TTS
    audio_minutes: float = 0  # Pour STT
    images: int = 0        # Pour Vision
    cost_usd: float = 0.0
    context: str = ""      # "conversation", "memory", "proactive", "mission:<id>"


# Tarifs au 2026-05 (à mettre à jour selon les changements de pricing)
PRICING: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-sonnet-4-6":       {"input_per_1m": 3.00,  "output_per_1m": 15.00},
        "claude-sonnet-4-5":       {"input_per_1m": 3.00,  "output_per_1m": 15.00},
        "claude-haiku-4-5-20251001": {"input_per_1m": 0.25, "output_per_1m": 1.25},
        "claude-haiku-4-5":        {"input_per_1m": 0.25,  "output_per_1m": 1.25},
        "claude-opus-4-7":         {"input_per_1m": 15.00, "output_per_1m": 75.00},
        "claude-opus-4-5":         {"input_per_1m": 15.00, "output_per_1m": 75.00},
    },
    "elevenlabs": {
        "eleven_turbo_v2_5":       {"per_1k_chars": 0.18},
        "eleven_flash_v2_5":       {"per_1k_chars": 0.18},
        "eleven_multilingual_v2":  {"per_1k_chars": 0.30},
    },
    "openai": {
        "gpt-4o":       {"input_per_1m": 2.50,  "output_per_1m": 10.00, "per_image": 0.002},
        "gpt-4o-mini":  {"input_per_1m": 0.15,  "output_per_1m": 0.60},
    },
    "deepgram": {
        "nova-2": {"per_minute": 0.0059},
        "nova-3": {"per_minute": 0.0059},
    },
}


def calculate_cost(provider: str, model: str, **kwargs: float) -> float:
    """Calcule le coût en USD pour un usage donné."""
    pricing = PRICING.get(provider, {})
    p = pricing.get(model)
    if p is None:
        for key in pricing:
            if model.startswith(key) or key.startswith(model):
                p = pricing[key]
                break
    if p is None:
        return 0.0

    cost = 0.0
    if "input_tokens" in kwargs and "input_per_1m" in p:
        cost += kwargs["input_tokens"] / 1_000_000 * p["input_per_1m"]
    if "output_tokens" in kwargs and "output_per_1m" in p:
        cost += kwargs["output_tokens"] / 1_000_000 * p["output_per_1m"]
    if "characters" in kwargs and "per_1k_chars" in p:
        cost += kwargs["characters"] / 1000 * p["per_1k_chars"]
    if "audio_minutes" in kwargs and "per_minute" in p:
        cost += kwargs["audio_minutes"] * p["per_minute"]
    if "images" in kwargs and "per_image" in p:
        cost += kwargs["images"] * p["per_image"]
    return round(cost, 6)


class UsageTracker:
    CONSO_DIR = Path("memory_data/conso")

    def __init__(self) -> None:
        self.CONSO_DIR.mkdir(parents=True, exist_ok=True)

    def track(self, entry: UsageEntry) -> None:
        """Enregistre une entrée de consommation dans le fichier JSONL du jour."""
        today = date.today().isoformat()
        log_file = self.CONSO_DIR / f"{today}.jsonl"
        with log_file.open("a") as f:
            f.write(json.dumps(entry.__dict__) + "\n")

    def _read_day(self, d: date) -> list[dict]:
        log_file = self.CONSO_DIR / f"{d.isoformat()}.jsonl"
        if not log_file.exists():
            return []
        entries: list[dict] = []
        with log_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries

    def get_session_summary(self) -> dict:
        """Résumé de la session courante (depuis minuit)."""
        entries = self._read_day(date.today())
        providers: dict = {}
        total_tokens = 0
        total_calls = 0
        total_cost = 0.0

        total_tts_chars = 0
        for e in entries:
            provider = e.get("provider", "unknown")
            model = e.get("model", "unknown")

            if provider not in providers:
                providers[provider] = {"models": {}, "total_cost": 0.0, "calls": 0}

            prov = providers[provider]
            if model not in prov["models"]:
                prov["models"][model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "characters": 0,
                    "audio_minutes": 0.0,
                    "images": 0,
                    "calls": 0,
                    "cost": 0.0,
                }

            m = prov["models"][model]
            m["input_tokens"]  += e.get("input_tokens", 0)
            m["output_tokens"] += e.get("output_tokens", 0)
            m["characters"]    += e.get("characters", 0)
            m["audio_minutes"] += e.get("audio_minutes", 0.0)
            m["images"]        += e.get("images", 0)
            m["calls"]         += 1
            m["cost"]          += e.get("cost_usd", 0.0)

            prov["calls"]      += 1
            prov["total_cost"] += e.get("cost_usd", 0.0)

            total_tokens += e.get("input_tokens", 0) + e.get("output_tokens", 0)
            total_calls  += 1
            total_cost   += e.get("cost_usd", 0.0)
            total_tts_chars += e.get("characters", 0)

        return {
            "total_tokens":    total_tokens,
            "total_api_calls": total_calls,
            "total_cost_usd":  round(total_cost, 4),
            "total_tts_chars": total_tts_chars,
            "providers":       providers,
        }

    def get_monthly_totals(self) -> dict:
        """Totaux depuis le début du mois courant."""
        today = date.today()
        first_day = today.replace(day=1)
        total_cost = 0.0
        total_tokens = 0
        total_tts_chars = 0
        total_calls = 0

        d = first_day
        while d <= today:
            entries = self._read_day(d)
            for e in entries:
                total_cost += e.get("cost_usd", 0.0)
                total_tokens += e.get("input_tokens", 0) + e.get("output_tokens", 0)
                total_tts_chars += e.get("characters", 0)
                total_calls += 1
            d = d + timedelta(days=1)

        return {
            "total_cost_usd":  round(total_cost, 4),
            "total_tokens":    total_tokens,
            "total_tts_chars": total_tts_chars,
            "total_api_calls": total_calls,
            "month":           today.strftime("%B %Y"),
        }

    def get_daily_totals(self, days: int = 7) -> list[dict]:
        """Totaux par jour sur les N derniers jours."""
        today = date.today()
        result = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            entries = self._read_day(d)
            day_cost = sum(e.get("cost_usd", 0.0) for e in entries)
            result.append({
                "date":     d.isoformat(),
                "day":      d.strftime("%a")[:3].upper(),
                "cost_usd": round(day_cost, 4),
            })
        return result

    def get_recent_calls(self, limit: int = 200) -> list[dict]:
        """Entrées brutes de la session courante, les plus récentes en premier."""
        entries = self._read_day(date.today())
        return list(reversed(entries[-limit:]))

    def get_daily_by_provider(self, days: int = 7) -> list[dict]:
        """Tokens LLM par provider par jour sur les N derniers jours."""
        today = date.today()
        result = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            entries = self._read_day(d)
            row: dict = {
                "date":      d.isoformat(),
                "day":       d.strftime("%a")[:3].upper(),
                "anthropic": 0,
                "openai":    0,
                "elevenlabs": 0,
                "deepgram":  0,
            }
            for e in entries:
                p = e.get("provider", "")
                if p in row:
                    row[p] += e.get("input_tokens", 0) + e.get("output_tokens", 0)
            result.append(row)
        return result


tracker = UsageTracker()
