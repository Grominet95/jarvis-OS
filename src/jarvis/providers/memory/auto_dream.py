from __future__ import annotations

import asyncio
import json
from pathlib import Path

from loguru import logger

from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.memory.ingest import IngestResult, MemoryIngest
from jarvis.providers.memory.mirror import MemoryMirror

# Plafond du nombre de sessions ingérées par run deep (la plus récente d'abord).
_MAX_SESSIONS_PER_DEEP = 5
# Plafond de caractères par session passée à l'extracteur (les sessions très
# longues sont tronquées à leur tail, qui contient en général le contexte le
# plus récent et le plus actionnable).
_MAX_CHARS_PER_SESSION = 8000

_DEFAULT_PREFS = "# Préférences Barth\n\nAucune préférence enregistrée.\n"

_MICRO_SYSTEM = (
    "Tu es un agent de mémorisation pour Jarvis. "
    "Analyse l'échange et mets à jour les préférences de Barth uniquement si tu détectes "
    "une nouvelle préférence explicite (note que, retiens que, j'aime, je préfère…) ou "
    "un signal implicite fort. Retourne uniquement le markdown mis à jour, sans explication. "
    "Si rien à changer, retourne le fichier identique."
)

_DEEP_SYSTEM = (
    "Tu es un agent de mémorisation pour Jarvis. "
    "Analyse les sessions fournies et synthétise les apprentissages durables sur Barth "
    "(préférences, habitudes, contexte). "
    "Retourne uniquement le markdown mis à jour des préférences."
)


class AutoDream:
    """Micro-update fire-and-forget après chaque échange + analyse profonde nocturne à 3h."""

    def __init__(
        self,
        llm: LLMProvider,
        prefs_path: Path,
        sessions_dir: Path,
        memory_ingest: MemoryIngest | None = None,
        mirror: MemoryMirror | None = None,
    ) -> None:
        self._llm = llm
        self._prefs_path = prefs_path
        self._sessions_dir = sessions_dir
        self._ensure_prefs()
        self._mirror = mirror
        # MOUVEMENT 2 (option D, Generative Agents) : l'ingestion Kernel est
        # déclenchée UNIQUEMENT par _run_deep (passe nocturne), et JAMAIS par
        # _run_micro (à chaque message). On évite la double extraction côté
        # ConsolidationAgent + AutoDream micro, et on respecte le principe de
        # synthèse périodique sur la conversation complète.
        # Le hook PHASE 3 dans _run_micro reste présent comme mort code inerte
        # car self._ingest est désormais TOUJOURS None côté micro en pratique
        # (main.py passe None à AutoDream micro, le memory_ingest n'est consommé
        # qu'au deep via _ingest_recent_sessions).
        self._ingest = memory_ingest

    def _ensure_prefs(self) -> None:
        if not self._prefs_path.exists():
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            self._prefs_path.write_text(_DEFAULT_PREFS, encoding="utf-8")

    def _read_prefs(self) -> str:
        return self._prefs_path.read_text(encoding="utf-8")

    def _write_prefs(self, content: str) -> None:
        self._prefs_path.write_text(content, encoding="utf-8")

    # ── Micro (fire-and-forget, après chaque échange) ─────────

    def fire_micro(self, user_message: str, assistant_message: str) -> None:
        asyncio.create_task(
            self._run_micro_safe(user_message, assistant_message),
            name="autodream-micro",
        )

    async def _run_micro_safe(self, user_message: str, assistant_message: str) -> None:
        try:
            await self._run_micro(user_message, assistant_message)
        except Exception as e:
            logger.exception("AutoDream micro error", error=str(e))

    async def _run_micro(self, user_message: str, assistant_message: str) -> None:
        prefs = self._read_prefs()
        prompt = (
            f"Préférences actuelles :\n{prefs}\n\n"
            f"Échange :\nBarth : {user_message}\nJarvis : {assistant_message}"
        )
        result = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=_MICRO_SYSTEM,
            stream=False,
        )
        updated = str(result).strip()
        if updated and updated != prefs.strip():
            self._write_prefs(updated)
            logger.info("AutoDream micro: préférences mises à jour")

        # PHASE 3 — Ingestion parallèle dans le Kernel (best-effort, ne bloque pas).
        if self._ingest is not None:
            try:
                await self._ingest.ingest(
                    content=f"Barth : {user_message}\nJarvis : {assistant_message}",
                    source="auto_dream_micro",
                    event_type="exchange",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("AutoDream micro: ingest Kernel error", error=str(exc))

    # ── Deep (nocturne, appelé par le scheduler à 3h) ─────────

    async def deep_analyze(self) -> None:
        try:
            await self._run_deep()
        except Exception as e:
            logger.exception("AutoDream deep error", error=str(e))

    async def _run_deep(self) -> None:
        sessions_text = self._load_recent_sessions()
        if not sessions_text:
            logger.debug("AutoDream deep: aucune session à analyser")
            return

        # 1) Synthèse texte → user_prefs.md (comportement historique préservé).
        prefs = self._read_prefs()
        prompt = f"Préférences actuelles :\n{prefs}\n\nSessions récentes :\n{sessions_text}"
        result = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            system=_DEEP_SYSTEM,
            stream=False,
        )
        updated = str(result).strip()
        if updated:
            self._write_prefs(updated)
            logger.info("AutoDream deep: préférences mises à jour")

        # 2) Ingestion batch dans le Memory Kernel — UNE extraction par session
        # entière (jamais par message). Le matcher v2 voit l'état cumulé du
        # Kernel à chaque ingest individuel → dédoublonnage intra-batch garanti.
        if self._ingest is not None:
            await self._ingest_recent_sessions()

        # 3) Régénération du miroir Markdown (SQLite → MD unidirectionnel, §6.7).
        # Tourne UNIQUEMENT en deep nocturne — c'est l'instant où la base est
        # stable après ingestion. Échec silencieux : le miroir est secondaire.
        if self._mirror is not None:
            try:
                report = self._mirror.export()
                logger.info(
                    "MemoryMirror exporté",
                    files=len(report.files_written),
                    facts=report.facts_exported,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("MemoryMirror export échec", error=str(exc))

    # ── Ingestion batch deep ──────────────────────────────────

    def _list_recent_session_files(self) -> list[Path]:
        """Renvoie les N sessions les plus récentes (par mtime, plus récente first).

        On itère ensuite de la plus ancienne à la plus récente pour que les facts
        des sessions anciennes soient en base AVANT l'extraction des nouvelles.
        Le matcher v2 peut alors confirmer/déduplique correctement intra-batch.
        """
        if not self._sessions_dir.exists():
            return []
        files = sorted(self._sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        return files[-_MAX_SESSIONS_PER_DEEP:]

    @staticmethod
    def _session_to_text(path: Path) -> str:
        """Concatène les messages d'une session JSONL en un texte unique.

        Format : alternance 'Barth : ...' / 'Jarvis : ...'.
        Le texte complet est passé à l'extracteur en UN SEUL APPEL — l'extracteur
        raisonne sur la session ENTIÈRE, pas message par message.
        """
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        parts: list[str] = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = obj.get("role", "")
            content = obj.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue
            speaker = "Barth" if role == "user" else "Jarvis"
            parts.append(f"{speaker} : {content.strip()}")
        text = "\n".join(parts)
        # Tronque au tail si la session est très longue : on garde le contexte
        # le plus récent (où sont les facts les plus actionnables).
        if len(text) > _MAX_CHARS_PER_SESSION:
            text = "...\n" + text[-_MAX_CHARS_PER_SESSION:]
        return text

    async def _ingest_recent_sessions(self) -> list[IngestResult]:
        """Ingère les N dernières sessions, UNE extraction par session entière.

        Renvoie la liste des IngestResult pour permettre une trace d'observation.
        """
        assert self._ingest is not None
        results: list[IngestResult] = []
        files = self._list_recent_session_files()
        for path in files:
            text = self._session_to_text(path)
            if not text.strip():
                continue
            try:
                r = await self._ingest.ingest(
                    content=text,
                    source=f"session:{path.name}",
                    event_type="session_summary",
                )
                results.append(r)
            except Exception as exc:  # noqa: BLE001 — un échec d'ingest ne bloque pas le batch
                logger.warning(
                    "AutoDream deep: ingest session échec",
                    file=path.name,
                    error=str(exc),
                )
        logger.info(
            "AutoDream deep: ingest batch terminé",
            sessions=len(results),
            arbiter_calls=self._ingest.arbiter_calls,
        )
        return results

    def _load_recent_sessions(self) -> str:
        """Compatibilité historique : concat texte des 5 dernières sessions (8000 chars)."""
        if not self._sessions_dir.exists():
            return ""
        files = sorted(self._sessions_dir.glob("*.jsonl"))[-5:]
        parts: list[str] = []
        for f in files:
            try:
                parts.append(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return "\n".join(parts)[:8000]
