"""Gestionnaire des widgets analytics activés."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from jarvis.analytics.widgets.base import WidgetBase, WidgetConfig, WidgetData
from jarvis.analytics.widgets.conso import ConsoWidget
from jarvis.analytics.widgets.discord import DiscordWidget
from jarvis.analytics.widgets.github import GitHubWidget
from jarvis.analytics.widgets.jarvis_stats import JarvisStatsWidget
from jarvis.analytics.widgets.youtube import YouTubeWidget

# Catalogue de tous les widgets disponibles
ALL_WIDGETS: dict[str, type[WidgetBase]] = {
    "jarvis_stats": JarvisStatsWidget,
    "conso": ConsoWidget,
    "youtube": YouTubeWidget,
    "github": GitHubWidget,
    "discord": DiscordWidget,
}

# Widgets actifs par défaut (natifs, sans config requise)
DEFAULT_WIDGETS = ["jarvis_stats", "conso"]

CONFIG_FILE = Path("memory_data/analytics_config.json")


class AnalyticsRegistry:
    _instance = None
    _active: dict[str, WidgetBase] = {}

    @classmethod
    def get_instance(cls) -> AnalyticsRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load()
        return cls._instance

    def load(self) -> None:
        """Charge les widgets depuis la config sauvegardée."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not CONFIG_FILE.exists():
            # Première fois : activer les widgets par défaut
            self._init_defaults()
            return

        config = json.loads(CONFIG_FILE.read_text())
        self._active = {}

        for widget_conf in config.get("active_widgets", []):
            wid = widget_conf["widget_id"]
            if wid in ALL_WIDGETS:
                w_class = ALL_WIDGETS[wid]
                w_config = WidgetConfig(**widget_conf)
                self._active[wid] = w_class(config=w_config)

        logger.info(f"AnalyticsRegistry: {len(self._active)} widget(s) actif(s)")

    def _init_defaults(self) -> None:
        """Active les widgets par défaut et sauvegarde."""
        for i, wid in enumerate(DEFAULT_WIDGETS):
            if wid in ALL_WIDGETS:
                config = WidgetConfig(widget_id=wid, position=i)
                self._active[wid] = ALL_WIDGETS[wid](config=config)
        self._save()

    def _save(self) -> None:
        """Sauvegarde la config active."""
        config = {
            "active_widgets": [
                {
                    "widget_id": wid,
                    "enabled": w.config.enabled,
                    "position": w.config.position,
                    "settings": w.config.settings,
                }
                for wid, w in self._active.items()
            ]
        }
        CONFIG_FILE.write_text(json.dumps(config, indent=2))

    def get_catalog(self) -> list[dict]:
        """Retourne tous les widgets disponibles avec leur statut."""
        catalog = []
        for wid, w_class in ALL_WIDGETS.items():
            w = w_class()
            manifest = w.to_manifest()
            manifest["active"] = wid in self._active
            catalog.append(manifest)
        return catalog

    def get_active(self) -> list[WidgetBase]:
        """Retourne les widgets actifs triés par position."""
        return sorted(self._active.values(), key=lambda w: w.config.position)

    def add(self, widget_id: str, settings: dict = None) -> dict:
        """Active un widget."""
        if widget_id not in ALL_WIDGETS:
            return {"success": False, "message": f"Widget '{widget_id}' inconnu"}
        if widget_id in self._active:
            return {"success": False, "message": f"Widget '{widget_id}' déjà actif"}

        position = max((w.config.position for w in self._active.values()), default=-1) + 1
        config = WidgetConfig(widget_id=widget_id, position=position, settings=settings or {})
        self._active[widget_id] = ALL_WIDGETS[widget_id](config=config)
        self._save()
        logger.info(f"Widget ajouté : {widget_id}")
        return {"success": True, "message": f"Widget '{widget_id}' ajouté"}

    def reorder(self, order: list[str]) -> dict:
        """Réordonne les widgets selon la liste d'IDs fournie."""
        for i, wid in enumerate(order):
            if wid in self._active:
                self._active[wid].config.position = i
        self._save()
        return {"success": True}

    def remove(self, widget_id: str) -> dict:
        """Désactive un widget."""
        if widget_id not in self._active:
            return {"success": False, "message": f"Widget '{widget_id}' non actif"}
        if widget_id in DEFAULT_WIDGETS:
            return {"success": False, "message": "Les widgets natifs ne peuvent pas être retirés"}
        del self._active[widget_id]
        self._save()
        return {"success": True, "message": f"Widget '{widget_id}' retiré"}

    async def fetch_all(self) -> dict[str, WidgetData]:
        """Fetch les données de tous les widgets actifs en parallèle."""
        import asyncio

        tasks = {
            wid: widget.fetch() for wid, widget in self._active.items() if widget.config.enabled
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {
            wid: result
            if not isinstance(result, Exception)
            else WidgetData(success=False, data={}, error=str(result))
            for wid, result in zip(tasks.keys(), results, strict=False)
        }


analytics_registry = AnalyticsRegistry.get_instance()
