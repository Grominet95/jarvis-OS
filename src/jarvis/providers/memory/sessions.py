from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger


class SessionStore:
    """Stockage append-only des transcripts en JSONL.

    Un fichier par session : sessions/YYYY-MM-DD_<uuid>.jsonl
    Chaque ligne : {"ts": "...", "role": "user|assistant", "content": "..."}
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _find(self, session_id: str) -> Path | None:
        matches = list(self._dir.glob(f"*_{session_id}.jsonl"))
        return matches[0] if matches else None

    def _path_for(self, session_id: str) -> Path:
        existing = self._find(session_id)
        if existing:
            return existing
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        return self._dir / f"{date}_{session_id}.jsonl"

    def load(self, session_id: str) -> list[dict]:
        """Charge l'historique d'une session. Retourne [] si introuvable."""
        path = self._find(session_id)
        if not path:
            return []
        messages: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                messages.append({"role": entry["role"], "content": entry["content"]})
        except (OSError, json.JSONDecodeError) as e:
            logger.error("SessionStore.load failed", session_id=session_id, error=str(e))
        return messages

    def append(self, session_id: str, role: str, content: str) -> None:
        """Ajoute un message au transcript. Crée le fichier si nécessaire."""
        path = self._path_for(session_id)
        entry = {"ts": datetime.now(UTC).isoformat(), "role": role, "content": content}
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("SessionStore.append failed", path=str(path), error=str(e))

    def list_recent(self, n: int = 20) -> list[Path]:
        """Retourne les n fichiers les plus récents (par mtime)."""
        files = sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:n]

    def list_all(self) -> list[Path]:
        """Retourne tous les fichiers de sessions triés par mtime décroissant."""
        return sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
