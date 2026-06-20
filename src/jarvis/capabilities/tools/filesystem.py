from __future__ import annotations

import asyncio
import fnmatch
import os
import platform
from collections.abc import Generator
from pathlib import Path

from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.permissions import permissions as _perms

_EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache", "Library"}
_MAX_FILE_SIZE = 100_000  # 100 Ko
_MDFIND_TIMEOUT = 10.0


def _walk_filtered(root: Path) -> Generator[Path, None, None]:
    """os.walk avec exclusion des répertoires lourds et cachés."""
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS and not d.startswith(".")]
        for filename in filenames:
            yield Path(dirpath) / filename


async def _mdfind(pattern: str, directory: str | None = None) -> list[str]:
    """Recherche via Spotlight (mdfind) — contourne les restrictions TCC macOS.

    pattern : glob-style (ex: 'COUCOUJAJA.html', '*.py', 'main*')
    On passe un prédicat kMDItemFSName et on filtre post-hoc avec fnmatch.
    """
    # Extrait la partie fixe du pattern pour la requête Spotlight
    stem = pattern.replace("*", "").replace("?", "").strip()
    predicate = f'kMDItemFSName == "*{stem}*"cd' if stem else 'kMDItemKind != ""'

    cmd = ["mdfind"]
    if directory:
        cmd += ["-onlyin", directory]
    cmd.append(predicate)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_MDFIND_TIMEOUT)
        lines = stdout.decode(errors="replace").strip().splitlines()
        # Post-filter avec le glob exact
        return [line for line in lines if fnmatch.fnmatch(Path(line).name, pattern)]
    except Exception as e:
        logger.debug("mdfind failed", error=str(e))
        return []


class ReadFileTool(Tool):
    """Lecture seule d'un fichier texte — aucune écriture possible."""

    name = "read_file"
    description = (
        "Lit le contenu d'un fichier texte sur le Mac de l'utilisateur (lecture seule, aucune "
        "modification). Utilise cet outil quand l'utilisateur demande de lire ou analyser un fichier."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Chemin absolu ou avec ~ vers le fichier",
            },
        },
        "required": ["path"],
    }

    def __init__(self, allowed_roots: list[Path]) -> None:
        self._allowed_roots = [r.resolve() for r in allowed_roots]

    def _is_allowed(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved.is_relative_to(root) for root in self._allowed_roots)

    async def execute(self, path: str, **_: object) -> ToolResult:

        if not _perms.get("files"):
            return ToolResult(
                content="Accès aux fichiers désactivé dans les permissions.", is_error=True
            )

        p = Path(path).expanduser().resolve()

        if not self._is_allowed(p):
            return ToolResult(
                content="Accès refusé : hors des répertoires autorisés.",
                is_error=True,
            )
        if not p.exists():
            return ToolResult(content=f"Fichier introuvable : {p}", is_error=True)
        if not p.is_file():
            return ToolResult(content=f"Pas un fichier : {p}", is_error=True)
        if p.stat().st_size > _MAX_FILE_SIZE:
            return ToolResult(
                content=f"Fichier trop grand ({p.stat().st_size} octets, max {_MAX_FILE_SIZE}).",
                is_error=True,
            )
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            logger.debug("File read", path=str(p), chars=len(content))
            return ToolResult(content=content)
        except OSError as e:
            return ToolResult(content=f"Erreur de lecture : {e}", is_error=True)


class FindFilesTool(Tool):
    """Recherche de fichiers par nom/extension — ne traverse pas les dossiers système."""

    name = "find_files"
    description = (
        "Cherche des fichiers par nom ou extension sur le Mac de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur demande de trouver des fichiers."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Pattern glob : '*.py', 'main*', 'README.md'",
            },
            "directory": {
                "type": "string",
                "description": "Répertoire de départ (optionnel, défaut : home)",
            },
            "max_results": {
                "type": "integer",
                "description": "Nombre max de résultats (défaut : 20, max : 50)",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, allowed_roots: list[Path]) -> None:
        self._allowed_roots = [r.resolve() for r in allowed_roots]

    def _is_allowed(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(
            resolved == root or resolved.is_relative_to(root) for root in self._allowed_roots
        )

    async def execute(
        self,
        pattern: str,
        directory: str | None = None,
        max_results: int = 20,
        **_: object,
    ) -> ToolResult:

        if not _perms.get("files"):
            return ToolResult(
                content="Accès aux fichiers désactivé dans les permissions.", is_error=True
            )

        root = Path(directory).expanduser().resolve() if directory else Path.home()

        if not self._is_allowed(root):
            return ToolResult(content="Accès refusé.", is_error=True)

        cap = min(max_results, 50)

        # Sur macOS, mdfind (Spotlight) accède à Downloads/Documents/Desktop sans restriction TCC
        if platform.system() == "Darwin":
            hits = await _mdfind(pattern, directory=str(root))
            hits = hits[:cap]
            if hits:
                logger.debug("FindFiles via mdfind", pattern=pattern, count=len(hits))
                return ToolResult(content="\n".join(hits))

        # Fallback POSIX : os.walk filtré (ne traverse pas les dossiers protégés macOS)
        results: list[str] = []
        for file_path in _walk_filtered(root):
            if fnmatch.fnmatch(file_path.name, pattern):
                results.append(str(file_path))
                if len(results) >= cap:
                    break

        if not results:
            return ToolResult(content=f"Aucun fichier trouvé pour '{pattern}'.")
        return ToolResult(content="\n".join(results))
