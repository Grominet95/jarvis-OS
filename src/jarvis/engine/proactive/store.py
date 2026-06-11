"""
InitiativeStore — persistance des initiatives sur le disque.
Format : JSONL dans memory_data/initiatives/
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from jarvis.engine.proactive.schemas import ExecutionMode, Initiative, InitiativeType, Priority
from jarvis.engine.vocab import AutonomyLevel
from jarvis.kernel.paths import MEMORY_DATA_DIR


def _title_key(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def _jaccard(a: str, b: str) -> float:
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _shares_keyword(a: str, b: str, min_len: int = 7) -> bool:
    """True if both titles share at least one meaningful word of length ≥ min_len."""
    wa = {w for w in re.findall(r"\w+", a.lower()) if len(w) >= min_len}
    wb = {w for w in re.findall(r"\w+", b.lower()) if len(w) >= min_len}
    return bool(wa & wb)


def _similar(a: str, b: str) -> bool:
    return _title_key(a) == _title_key(b) or _jaccard(a, b) >= 0.35 or _shares_keyword(a, b)


def _dedup_initiatives(initiatives: list) -> list:
    """Keep the oldest initiative when two titles are semantically similar."""
    kept: list = []
    for candidate in initiatives:
        for existing in kept:
            if _similar(candidate.title, existing.title):
                break
        else:
            kept.append(candidate)
    return kept


INITIATIVES_DIR = MEMORY_DATA_DIR / "initiatives"


class InitiativeStore:
    def __init__(self) -> None:
        INITIATIVES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Helpers privés ────────────────────────────────────────────────────────

    def _days_files(self, days: int) -> list[Path]:
        """Retourne les fichiers JSONL des N derniers jours CALENDAIRES,
        triés du plus ancien au plus récent."""
        from datetime import date, timedelta

        cutoff = (date.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        return sorted(f for f in INITIATIVES_DIR.glob("*.jsonl") if f.stem >= cutoff)

    def _parse_initiative(self, data: dict) -> Initiative:
        # PHASE 6 — nouveaux champs avec .get(...) defaults pour compat JSONL legacy.
        deadline_str = data.get("deadline")
        return Initiative(
            id=data["id"],
            type=InitiativeType(data["type"]),
            title=data["title"],
            context=data["context"],
            reasoning=data["reasoning"],
            action=data["action"],
            priority=Priority(data["priority"]),
            execution_mode=ExecutionMode(data["execution_mode"]),
            draft_content=data.get("draft_content"),
            mission_description=data.get("mission_description"),
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]),
            autonomy_level=AutonomyLevel(
                int(data.get("autonomy_level", int(AutonomyLevel.SUGGEST)))
            ),
            permission_required=data.get("permission_required", "agent_mission"),
            cost_max_usd=data.get("cost_max_usd"),
            risk=data.get("risk", "low"),
            deadline=datetime.fromisoformat(deadline_str) if deadline_str else None,
            next_action=data.get("next_action", ""),
            requires_validation=bool(data.get("requires_validation", False)),
        )

    def _find_file_for_id(self, initiative_id: str, days: int = 7) -> Path | None:
        """Retourne le fichier JSONL qui contient l'initiative, ou None."""
        for f in reversed(self._days_files(days)):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                try:
                    if json.loads(line).get("id") == initiative_id:
                        return f
                except Exception:
                    pass
        return None

    def _all_pending_titles(self) -> list[str]:
        """Collect titles of all pending initiatives across the last 7 days."""
        titles = []
        for f in self._days_files(7):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("status") == "pending":
                        titles.append(d.get("title", ""))
                except Exception:
                    pass
        return titles

    # ── Écriture ──────────────────────────────────────────────────────────────

    def save(self, initiative: Initiative) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = INITIATIVES_DIR / f"{today}.jsonl"

        # Dédup cross-cycle sur les 7 derniers jours
        for etitle in self._all_pending_titles():
            if _similar(initiative.title, etitle):
                return

        with log_file.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "id": initiative.id,
                        "type": initiative.type,
                        "title": initiative.title,
                        "context": initiative.context,
                        "reasoning": initiative.reasoning,
                        "action": initiative.action,
                        "priority": initiative.priority,
                        "execution_mode": initiative.execution_mode,
                        "draft_content": initiative.draft_content,
                        "mission_description": initiative.mission_description,
                        "status": initiative.status,
                        "created_at": initiative.created_at.isoformat(),
                        # PHASE 6 — champs gouvernance §10.1
                        "autonomy_level": int(initiative.autonomy_level),
                        "permission_required": initiative.permission_required,
                        "cost_max_usd": initiative.cost_max_usd,
                        "risk": initiative.risk,
                        "deadline": (
                            initiative.deadline.isoformat() if initiative.deadline else None
                        ),
                        "next_action": initiative.next_action,
                        "requires_validation": initiative.requires_validation,
                    }
                )
                + "\n"
            )

    # ── Lecture ───────────────────────────────────────────────────────────────

    def load_pending(self) -> list[Initiative]:
        """Charge toutes les initiatives en attente du jour, dédupliquées."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = INITIATIVES_DIR / f"{today}.jsonl"

        if not log_file.exists():
            return []

        initiatives = []
        for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("status") == "pending":
                    initiatives.append(self._parse_initiative(data))
            except Exception:
                pass

        return _dedup_initiatives(initiatives)

    def load_pending_all(self, days: int = 7) -> list[Initiative]:
        """Charge toutes les initiatives 'pending' des N derniers jours, dédupliquées."""
        all_initiatives: list[Initiative] = []
        for f in self._days_files(days):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("status") == "pending":
                        all_initiatives.append(self._parse_initiative(data))
                except Exception:
                    pass
        return _dedup_initiatives(all_initiatives)

    def list_recent(self, days: int = 7, statuses: list[str] | None = None) -> list[Initiative]:
        """Retourne les initiatives des N derniers jours filtrées par statut (tous si None)."""
        all_items: list[Initiative] = []
        target = set(statuses) if statuses else None
        for f in self._days_files(days):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if target is None or data.get("status") in target:
                        all_items.append(self._parse_initiative(data))
                except Exception:
                    pass
        return all_items

    def get_by_id(self, initiative_id: str, days: int = 7) -> Initiative | None:
        """Recherche une initiative par ID sur les N derniers jours (plus récent en premier)."""
        for f in reversed(self._days_files(days)):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("id") == initiative_id:
                        return self._parse_initiative(data)
                except Exception:
                    pass
        return None

    # ── Mise à jour ───────────────────────────────────────────────────────────

    def update_initiative(self, initiative_id: str, updates: dict) -> None:
        """Met à jour les champs d'une initiative existante (cherche dans N derniers jours)."""
        log_file = self._find_file_for_id(initiative_id)
        if not log_file:
            return

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        updated = []
        for line in lines:
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("id") == initiative_id:
                    data.update(updates)
                line = json.dumps(data)
            except Exception:
                pass
            updated.append(line)

        log_file.write_text("\n".join(updated) + "\n", encoding="utf-8")

    def update_status(self, initiative_id: str, status: str) -> None:
        """Met à jour le statut d'une initiative (cherche dans N derniers jours)."""
        log_file = self._find_file_for_id(initiative_id)
        if not log_file:
            return

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        updated = []
        for line in lines:
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("id") == initiative_id:
                    data["status"] = status
                line = json.dumps(data)
            except Exception:
                pass
            updated.append(line)

        log_file.write_text("\n".join(updated) + "\n", encoding="utf-8")
