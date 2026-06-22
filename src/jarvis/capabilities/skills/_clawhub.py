# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
from loguru import logger

CLAWHUB_API = "https://clawhub.ai/api"
_TIMEOUT = 30.0


async def search_skills(query: str) -> list[dict]:
    """Recherche des skills publics sur ClawHub."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{CLAWHUB_API}/skills/search", params={"q": query})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        logger.error("ClawHub search error", error=str(e))
        return []


async def install_skill(slug: str, skills_dir: Path) -> tuple[bool, str]:
    """Télécharge et installe un skill depuis ClawHub.

    Retourne (succès, message).
    """
    dest = skills_dir / slug
    if dest.exists():
        return False, f"Le skill '{slug}' existe déjà dans {dest}."

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{CLAWHUB_API}/skills/{slug}/download")
            if r.status_code == 404:
                return False, f"Skill '{slug}' introuvable sur ClawHub."
            r.raise_for_status()
            content = r.content
    except httpx.HTTPError as e:
        return False, f"Erreur réseau ClawHub : {e}"

    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            # Sécurité : ne pas extraire de fichiers avec des chemins relatifs dangereux
            for member in z.namelist():
                if ".." in member or member.startswith("/"):
                    logger.warning("Membre ZIP suspect ignoré", member=member)
                    continue
                z.extract(member, dest)
    except zipfile.BadZipFile:
        dest.rmdir()
        return False, "Le fichier téléchargé n'est pas un ZIP valide."

    if not (dest / "SKILL.md").exists():
        import shutil

        shutil.rmtree(dest)
        return False, f"Skill '{slug}' invalide : SKILL.md manquant."

    logger.info("Skill installé depuis ClawHub", slug=slug, dir=str(dest))
    return True, f"Skill '{slug}' installé avec succès."
