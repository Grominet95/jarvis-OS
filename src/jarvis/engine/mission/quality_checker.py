# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
QualityChecker — vérifications automatiques de qualité post-étape et fin de projet.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from loguru import logger


class QualityChecker:
    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path).resolve()

    # ── File checks ───────────────────────────────────────────────────────────

    def check_file_not_empty(self, file_path: str) -> bool:
        target = self._workspace / file_path
        return target.exists() and target.stat().st_size > 0

    def list_all_files(self) -> list[dict]:
        """Liste tous les fichiers du workspace (hors .jarvis) avec métadonnées."""
        files = []
        for f in self._workspace.rglob("*"):
            if f.is_file() and ".jarvis" not in str(f):
                rel = str(f.relative_to(self._workspace))
                files.append(
                    {
                        "path": rel,
                        "size": f.stat().st_size,
                        "extension": f.suffix,
                    }
                )
        return files

    # ── HTML reference check ──────────────────────────────────────────────────

    def check_html_references(self, html_path: str) -> list[str]:
        """Vérifie que tous les fichiers référencés dans un HTML existent.

        Retourne les manquants.
        """
        html_file = self._workspace / html_path
        if not html_file.exists():
            return [f"HTML introuvable: {html_path}"]

        content = html_file.read_text(encoding="utf-8", errors="replace")
        missing = []

        for ref in re.findall(r'href=["\']([^"\']+\.css)["\']', content):
            if not ref.startswith(("http://", "https://", "//", "data:")):
                target = (self._workspace / Path(html_path).parent / ref).resolve()
                if not target.exists():
                    missing.append(f"CSS manquant: {ref}")

        for ref in re.findall(r'src=["\']([^"\']+\.js)["\']', content):
            if not ref.startswith(("http://", "https://", "//", "data:")):
                target = (self._workspace / Path(html_path).parent / ref).resolve()
                if not target.exists():
                    missing.append(f"JS manquant: {ref}")

        for ref, _ in re.findall(r'src=["\']([^"\']+\.(png|jpg|jpeg|svg|webp|gif))["\']', content):
            if not ref.startswith(("http://", "https://", "//", "data:")):
                target = (self._workspace / Path(html_path).parent / ref).resolve()
                if not target.exists():
                    missing.append(f"Image manquante: {ref}")

        return missing

    # ── Python syntax check ───────────────────────────────────────────────────

    def check_python_syntax(self, py_path: str) -> dict:
        target = self._workspace / py_path
        if not target.exists():
            return {"valid": False, "error": "Fichier introuvable"}
        try:
            ast.parse(target.read_text(encoding="utf-8", errors="replace"))
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": str(e)}

    # ── Full report ───────────────────────────────────────────────────────────

    def generate_report(self) -> dict:
        """Rapport de qualité complet : fichiers, problèmes détectés."""
        files = self.list_all_files()
        issues = []

        for f in files:
            if f["size"] == 0:
                issues.append(f"Fichier vide: {f['path']}")
            if f["extension"] == ".html":
                missing = self.check_html_references(f["path"])
                issues.extend(missing)
            if f["extension"] == ".py":
                result = self.check_python_syntax(f["path"])
                if not result["valid"]:
                    issues.append(f"Syntaxe Python invalide dans {f['path']}: {result['error']}")

        valid = len(issues) == 0
        logger.info("QualityChecker report", files=len(files), issues=len(issues), valid=valid)
        return {"files": files, "issues": issues, "valid": valid}

    # ── Incremental check (post-step) ─────────────────────────────────────────

    def check_step_output(self, files_before: list[str]) -> list[str]:
        """Détecte les problèmes sur les fichiers créés/modifiés depuis la dernière vérif."""
        current = {f["path"]: f for f in self.list_all_files()}
        new_paths = [p for p in current if p not in files_before]
        issues = []

        for path in new_paths:
            f = current[path]
            if f["size"] == 0:
                issues.append(f"Fichier vide créé: {path}")
            if f["extension"] == ".html":
                missing = self.check_html_references(path)
                issues.extend(missing)
            if f["extension"] == ".py":
                result = self.check_python_syntax(path)
                if not result["valid"]:
                    issues.append(f"Syntaxe Python invalide dans {path}: {result['error']}")

        return issues
