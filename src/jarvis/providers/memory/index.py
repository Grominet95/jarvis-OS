from __future__ import annotations

from pathlib import Path

from loguru import logger


class MemoryIndex:
    """Lecture/écriture de MEMORY.md — l'index des pointeurs mémoire.

    MEMORY.md ne contient que des pointeurs, jamais de contenu direct.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._path = memory_dir / "MEMORY.md"

    def read(self) -> str:
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("MemoryIndex.read failed", error=str(e))
            return ""

    def add_pointer(self, section: str, key: str, filepath: str, description: str) -> None:
        """Ajoute ou met à jour un pointeur dans MEMORY.md.

        Si la clé existe déjà, la ligne est mise à jour sur place.
        Si la section existe, le pointeur y est ajouté.
        Sinon, une nouvelle section est créée en fin de fichier.
        """
        content = self.read()
        pointer_line = f"- {key}: `{filepath}` — {description}"
        lines = content.splitlines()

        # Mise à jour si le pointeur existe déjà
        for i, line in enumerate(lines):
            if line.strip().startswith(f"- {key}:"):
                lines[i] = pointer_line
                self._write("\n".join(lines))
                logger.debug("MemoryIndex pointer updated", key=key)
                return

        # Insertion dans la bonne section
        in_section = False
        for i, line in enumerate(lines):
            if line.strip() == f"## {section}":
                in_section = True
            elif in_section and (line.startswith("## ") or line.startswith("# ")):
                lines.insert(i, pointer_line)
                self._write("\n".join(lines))
                logger.debug("MemoryIndex pointer added", key=key, section=section)
                return
            elif in_section and i == len(lines) - 1:
                lines.append(pointer_line)
                self._write("\n".join(lines))
                logger.debug("MemoryIndex pointer added (end of section)", key=key)
                return

        # Section introuvable → créer en fin de fichier
        lines.extend(["", f"## {section}", pointer_line])
        self._write("\n".join(lines))
        logger.debug("MemoryIndex new section created", section=section, key=key)

    def _write(self, content: str) -> None:
        try:
            self._path.write_text(content + "\n", encoding="utf-8")
        except OSError as e:
            logger.error("MemoryIndex.write failed", error=str(e))
