# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Gestion des jeux/apps lançables par Jarvis (Réglages → Jeux).

Stockage dans un fichier YAML dédié (settings.games_path), séparé de
config/tools.yaml (scripts CLI avancés). CLIRunnerTool (capabilities/tools/cli.py)
relit ce fichier à chaque appel, donc un jeu ajouté ici est utilisable
immédiatement, sans redémarrer Jarvis.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from jarvis.kernel.http_errors import raise_api_error
from jarvis.kernel.paths import PROJECT_ROOT
from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api/games")

_BROWSE_SCRIPT = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$f = New-Object System.Windows.Forms.OpenFileDialog; "
    "$f.Filter = 'Executable (*.exe)|*.exe'; "
    "$f.Title = \"Choisis l'exécutable du jeu\"; "
    "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"
)


def _pick_file_sync() -> str:
    result = subprocess.run(  # noqa: S602,S603,S607 — commande fixe, pas d'entrée utilisateur
        ["powershell", "-NoProfile", "-STA", "-Command", _BROWSE_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


def _games_path() -> Path:
    return PROJECT_ROOT / settings.games_path


def load_games() -> dict[str, dict]:
    path = _games_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _save_games(games: dict[str, dict]) -> None:
    path = _games_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Jeux/apps ajoutés depuis Réglages → Jeux.\n"
        "# Géré par l'API (src/jarvis/interfaces/api/games.py) — édition manuelle possible\n"
        "# mais l'UI écrasera ce fichier au prochain ajout/suppression.\n"
    )
    path.write_text(
        header + yaml.safe_dump(games, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().replace("'", "")).strip("_")
    return slug or "jeu"


def _unique_alias(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


# Exécutables présents dans quasi tout dossier de jeu mais qui ne sont jamais
# le jeu lui-même (désinstalleur, redistribuables, launchers d'anti-cheat…).
_EXE_EXCLUDE_RE = re.compile(
    r"unins|uninstall|redist|prereqsetup|vcredist|dxsetup|directx|crashpad|"
    r"crashreport|crashhandler|^setup$|installer|updater|easyanticheat|battleye",
    re.IGNORECASE,
)
# Dossiers dont le contenu n'est jamais le jeu lui-même (moteur, redistribuables).
_DIR_EXCLUDE = {"engine", "redist", "_commonredist", "directx", "vcredist"}


def _find_game_exe(folder: Path) -> tuple[Path | None, list[Path]]:
    """Cherche l'exécutable probable du jeu dans un dossier (récursif).

    Filtre les outils internes (désinstalleur, moteur Unreal/Unity, redist),
    puis si plusieurs candidats restent (ex: lanceur racine + binaire interne
    dans Binaries/Win64/, cas classique Unreal Engine), préfère celui le plus
    proche de la racine — c'est celui prévu pour être lancé directement.
    Retourne (candidat unique ou None, liste de tous les candidats filtrés).
    """
    candidates = []
    for p in folder.rglob("*.exe"):
        rel_parts = p.relative_to(folder).parts
        if _EXE_EXCLUDE_RE.search(p.stem):
            continue
        if any(part.lower() in _DIR_EXCLUDE for part in rel_parts[:-1]):
            continue
        candidates.append(p)

    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], candidates

    min_depth = min(len(c.relative_to(folder).parts) for c in candidates)
    shallowest = [c for c in candidates if len(c.relative_to(folder).parts) == min_depth]
    if len(shallowest) == 1:
        return shallowest[0], candidates
    return None, candidates


def _resolve_exe_path(path_str: str) -> Path:
    """Valide un chemin fourni par l'utilisateur : fichier direct, ou dossier
    dans lequel on cherche l'exécutable probable (cf. _find_game_exe)."""
    exe_path = Path(path_str)
    if exe_path.is_dir():
        found, candidates = _find_game_exe(exe_path)
        if found is not None:
            return found
        if candidates:
            names = ", ".join(str(c.relative_to(exe_path)) for c in candidates[:10])
            raise_api_error(
                "JRV-GAM-002",
                400,
                f"Plusieurs exécutables trouvés dans ce dossier, précise lequel : {names}",
            )
        raise_api_error("JRV-GAM-002", 400, f"Aucun .exe trouvé dans {path_str}")
    if not exe_path.is_file():
        raise_api_error("JRV-GAM-002", 400, f"Fichier introuvable : {path_str}")
    return exe_path


class GameCreate(BaseModel):
    name: str
    path: str
    description: str = ""
    poster_url: str = ""


class GameUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    description: str | None = None
    poster_url: str | None = None


@router.post("/browse")
async def browse_exe() -> dict:
    """Ouvre le sélecteur de fichier natif Windows sur la machine où tourne Jarvis
    (sensé être la même que celle du navigateur, Jarvis étant un usage local)."""
    if sys.platform != "win32":
        raise_api_error("JRV-GAM-004", 400, "Parcourir n'est disponible que sur Windows.")
    path = await asyncio.to_thread(_pick_file_sync)
    return {"path": path}


@router.get("")
async def list_games() -> dict:
    games = load_games()
    return {
        "games": [
            {
                "alias": alias,
                "name": g.get("name", alias),
                "path": g.get("path", ""),
                "description": g.get("description", ""),
                "poster_url": g.get("poster_url", ""),
            }
            for alias, g in games.items()
        ]
    }


@router.post("")
async def add_game(body: GameCreate) -> dict:
    name = body.name.strip()
    path_str = body.path.strip().strip('"')
    if not name:
        raise_api_error("JRV-GAM-001", 400, "Le nom est vide.")
    if not path_str:
        raise_api_error("JRV-GAM-001", 400, "Le chemin est vide.")

    exe_path = _resolve_exe_path(path_str)

    games = load_games()
    alias = _unique_alias(_slugify(name), set(games))
    entry = {
        "name": name,
        "path": str(exe_path),
        "description": body.description.strip(),
        "poster_url": body.poster_url.strip(),
    }
    games[alias] = entry
    _save_games(games)
    return {"ok": True, "alias": alias, **entry}


@router.patch("/{alias}")
async def update_game(alias: str, body: GameUpdate) -> dict:
    games = load_games()
    entry = games.get(alias)
    if entry is None:
        raise_api_error("JRV-GAM-003", 404, f"Jeu inconnu : {alias}")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise_api_error("JRV-GAM-001", 400, "Le nom est vide.")
        entry["name"] = name

    if body.path is not None:
        path_str = body.path.strip().strip('"')
        if not path_str:
            raise_api_error("JRV-GAM-001", 400, "Le chemin est vide.")
        entry["path"] = str(_resolve_exe_path(path_str))

    if body.description is not None:
        entry["description"] = body.description.strip()

    if body.poster_url is not None:
        entry["poster_url"] = body.poster_url.strip()

    games[alias] = entry
    _save_games(games)
    return {"ok": True, "alias": alias, **entry}


@router.delete("/{alias}")
async def delete_game(alias: str) -> dict:
    games = load_games()
    if alias not in games:
        raise_api_error("JRV-GAM-003", 404, f"Jeu inconnu : {alias}")
    del games[alias]
    _save_games(games)
    return {"ok": True}
