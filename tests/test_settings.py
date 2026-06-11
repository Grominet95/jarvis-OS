from __future__ import annotations

import pytest

from jarvis.kernel.settings import Settings


def test_settings_load() -> None:
    """Vérifie que les settings se chargent sans erreur (avec .env du dev)."""
    s = Settings()
    assert s.llm_provider in ("api", "local")
    assert s.port > 0
    assert s.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie les défauts déclarés DANS LE CODE, isolés du .env du dev.

    Sans isolation, Settings() lit `.env` (qui définit HOST=0.0.0.0 pour
    l'usage Tailscale) et l'environnement shell, et écrase les défauts —
    le test deviendrait dépendant du dev qui le lance.
    """
    for var in ("HOST", "PORT", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.anthropic_model == "claude-sonnet-4-6"
