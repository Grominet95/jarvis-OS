from __future__ import annotations

from pathlib import Path

from loguru import logger


class TopicStore:
    """Lecture/écriture des fichiers thématiques Markdown.

    Les fichiers thématiques sont la source de vérité mémoire.
    MEMORY.md n'en contient que des pointeurs.
    """

    def __init__(self, topics_dir: Path) -> None:
        self._dir = topics_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_all(self) -> list[str]:
        return sorted(f.name for f in self._dir.glob("*.md"))

    def load(self, filename: str) -> str:
        try:
            return (self._dir / filename).read_text(encoding="utf-8")
        except OSError as e:
            logger.error("TopicStore.load failed", file=filename, error=str(e))
            return ""

    def load_all(self) -> dict[str, str]:
        """Charge tous les fichiers thématiques. Retourne {filename: content}."""
        return {name: self.load(name) for name in self.list_all()}

    def write(self, filename: str, content: str) -> None:
        """Écrit ou écrase un fichier thématique."""
        path = self._dir / filename
        try:
            path.write_text(content, encoding="utf-8")
            logger.info("TopicStore written", file=filename)
        except OSError as e:
            logger.error("TopicStore.write failed", file=filename, error=str(e))

    def exists(self, filename: str) -> bool:
        return (self._dir / filename).exists()
