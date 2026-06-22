# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from pathlib import Path

from jarvis.kernel.paths import (
    FACES_DIR,
    MEMORY_DATA_DIR,
    SKILLS_CANDIDATES_DIR,
    SKILLS_INSTALLED_DIR,
    WORKSPACE_DIR,
)

_RUNTIME_DIRS: tuple[Path, ...] = (
    MEMORY_DATA_DIR / "sessions",
    MEMORY_DATA_DIR / "topics",
    MEMORY_DATA_DIR / "conso",
    MEMORY_DATA_DIR / "initiatives",
    MEMORY_DATA_DIR / "curator_reports",
    FACES_DIR,
    SKILLS_INSTALLED_DIR,
    SKILLS_CANDIDATES_DIR,
    WORKSPACE_DIR / "projects",
)


def ensure_runtime_layout() -> list[str]:
    created: list[str] = []
    for path in _RUNTIME_DIRS:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
    return created


def read_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def is_setup_complete(env_path: Path | None = None) -> bool:
    path = env_path or Path(".env")
    env = read_env_file(path)
    if not env.get("USER_FIRSTNAME", "").strip():
        return False
    # Le LLM est facultatif : si le wizard a été validé explicitement
    # (flag SETUP_COMPLETE), le setup est terminé même sans clé.
    if env.get("SETUP_COMPLETE", "").strip().lower() == "true":
        return True
    # Sinon (rétro-compat / inférence) : prénom + clé du backend choisi.
    key_for_backend = {
        "openai": "OPENAI_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    backend = env.get("API_BACKEND", "anthropic")
    return bool(env.get(key_for_backend.get(backend, "ANTHROPIC_API_KEY"), "").strip())
