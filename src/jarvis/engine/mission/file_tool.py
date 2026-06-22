# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Outil fichiers sandboxé — toutes les opérations confinées au workspace du projet."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


class SandboxedFileTool:
    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path).resolve()

    def _safe_path(self, relative_path: str) -> Path:
        """Vérifie que le chemin résolu reste dans le workspace. Lève ValueError sinon."""
        target = (self._workspace / relative_path).resolve()
        if not str(target).startswith(str(self._workspace)):
            logger.error("SANDBOX VIOLATION", path=relative_path, target=str(target))
            raise ValueError(f"ACCÈS REFUSÉ : '{relative_path}' sort du workspace autorisé.")
        return target

    def read_file(self, path: str) -> str:
        target = self._safe_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Fichier non trouvé : {path}")
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> str:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info("Sandbox write", path=path, chars=len(content))
        return f"Fichier écrit : {path} ({len(content)} caractères)"

    def list_files(self, directory: str = ".") -> list[str]:
        target = self._safe_path(directory)
        if not target.is_dir():
            return []
        return [
            str(p.relative_to(self._workspace))
            for p in sorted(target.rglob("*"))
            if p.is_file() and ".jarvis" not in str(p)
        ]

    def delete_file(self, path: str) -> str:
        target = self._safe_path(path)
        if target.exists():
            target.unlink()
            logger.info("Sandbox delete", path=path)
            return f"Supprimé : {path}"
        return f"Fichier inexistant : {path}"

    def create_directory(self, path: str) -> str:
        target = self._safe_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Répertoire créé : {path}"
