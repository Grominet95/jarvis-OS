"""Classe de base pour tous les widgets analytics Jarvis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WidgetConfig:
    """Configuration d'un widget activé."""

    widget_id: str  # ex: "youtube", "jarvis_stats"
    enabled: bool = True
    settings: dict = field(default_factory=dict)  # config spécifique au widget
    position: int = 0  # ordre d'affichage dans la grille


@dataclass
class WidgetData:
    """Données retournées par un widget pour affichage."""

    success: bool
    data: dict  # données brutes
    error: str = ""  # message d'erreur si success=False
    cached: bool = False  # True si données depuis cache


class WidgetBase(ABC):
    """
    Classe de base pour un widget analytics.

    Chaque widget déclare :
    - son identifiant unique (id)
    - son label affiché à l'utilisateur (label)
    - ses variables .env requises (requires_env)
    - sa taille dans la grille (size: "small" | "medium" | "large" | "full")
    - sa méthode fetch() qui retourne les données
    """

    id: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""  # emoji ou lettre pour l'avatar du widget
    requires_env: list[str] = []
    size: str = "medium"  # small=1col, medium=2col, large=3col, full=4col

    def __init__(self, config: WidgetConfig = None) -> None:
        self.config = config or WidgetConfig(widget_id=self.id)

    @abstractmethod
    async def fetch(self) -> WidgetData:
        """Fetch les données du widget. Appelé toutes les N minutes."""
        pass

    def is_configured(self) -> bool:
        """Vérifie que toutes les requires_env sont renseignées."""
        import os

        return all(bool(os.getenv(key, "").strip()) for key in self.requires_env)

    def get_env_status(self) -> dict[str, bool]:
        """Retourne le statut de chaque variable requise."""
        import os

        return {key: bool(os.getenv(key, "").strip()) for key in self.requires_env}

    def to_manifest(self) -> dict:
        """Metadata du widget pour l'UI (catalogue + setup flow)."""
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "requires_env": self.requires_env,
            "size": self.size,
            "configured": self.is_configured(),
            "env_status": self.get_env_status(),
        }
