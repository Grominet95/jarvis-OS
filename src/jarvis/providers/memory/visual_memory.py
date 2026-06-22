# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
Mémoire visuelle — stocke les souvenirs visuels de Jarvis.

Format : entrées Markdown datées avec description, source et contexte.
Compatible avec le système mémoire existant (topics/).
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from jarvis.kernel.paths import MEMORY_DATA_DIR

_VISUAL_MEMORY_FILE = MEMORY_DATA_DIR / "topics" / "visual_memory.md"
_MAX_ENTRIES = 100
_HEADER = (
    "# Mémoire Visuelle\n\n"
    "Ce fichier contient les souvenirs visuels de Jarvis — "
    "ce qu'il a observé via la webcam ou l'analyse d'images.\n\n"
)

_KEYWORDS = [
    "esp32",
    "pcb",
    "composant",
    "schéma",
    "résistance",
    "condensateur",
    "arduino",
    "raspberry",
    "circuit",
    "soudure",
    "datasheet",
    "texte",
    "document",
    "facture",
    "note",
    "livre",
    "code",
    "écran",
]


def _extract_tags(text: str) -> list[str]:
    tl = text.lower()
    return [k for k in _KEYWORDS if k in tl]


def _ensure_file() -> None:
    _VISUAL_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _VISUAL_MEMORY_FILE.exists():
        _VISUAL_MEMORY_FILE.write_text(_HEADER, encoding="utf-8")


async def store(
    description: str,
    source: str,
    context: str = "",
    tags: list[str] | None = None,
) -> None:
    """Ajoute un souvenir visuel dans la mémoire."""
    _ensure_file()

    if tags is None:
        tags = _extract_tags(description)

    now = datetime.now()
    tag_str = " ".join(f"`{t}`" for t in tags) if tags else ""
    entry = (
        f"\n## {now.strftime('%Y-%m-%d %H:%M')} — {source}\n"
        f"{tag_str}\n\n"
        f"**Contexte :** {context}\n\n"
        f"{description}\n"
    )

    content = _VISUAL_MEMORY_FILE.read_text(encoding="utf-8")
    # Insérer après le header (avant le premier ## ou à la fin)
    insert_at = content.find("\n## ")
    if insert_at == -1:
        content += entry
    else:
        content = content[:insert_at] + entry + content[insert_at:]

    # Tronquer aux MAX_ENTRIES dernières entrées
    parts = content.split("\n## ")
    if len(parts) > _MAX_ENTRIES + 1:
        parts = parts[: _MAX_ENTRIES + 1]
        content = "\n## ".join(parts)

    _VISUAL_MEMORY_FILE.write_text(content, encoding="utf-8")

    await _update_index()
    logger.debug("Visual memory stored", source=source, preview=description[:60])


async def search(query: str) -> list[str]:
    """Recherche par mots-clés dans les souvenirs visuels."""
    _ensure_file()
    content = _VISUAL_MEMORY_FILE.read_text(encoding="utf-8")
    entries = content.split("\n## ")[1:]

    words = query.lower().split()
    matches = []
    for entry in entries:
        if any(w in entry.lower() for w in words):
            matches.append("## " + entry[:400])

    return matches[:5]


async def _update_index() -> None:
    """S'assure que visual_memory.md est référencé dans MEMORY.md."""
    index = MEMORY_DATA_DIR / "MEMORY.md"
    if not index.exists():
        return
    content = index.read_text(encoding="utf-8")
    pointer = "- visual: `topics/visual_memory.md`"
    if pointer not in content:
        content += f"\n{pointer} — Souvenirs visuels (webcam, documents, analyses)\n"
        index.write_text(content, encoding="utf-8")
