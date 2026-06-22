# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Log d'audit immuable des décisions du gate composite (§9).

Chaque appel à `Governance.gate()` produit une entrée tracée sur disque (JSONL).
Le log est append-only — on ne supprime jamais une entrée.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    """Une décision du gate composite, immuable."""

    timestamp: datetime
    decision: str  # "auto" | "dry_run" | "approval" | "refused"
    context_id: str  # "step:proj_xxx:s001", "tool:write_file:proj_xxx", etc.
    access_level: int
    action_category: str
    estimated_cost_usd: float
    # Décision détaillée par axe — utile au debug et au curator (PHASE 6)
    risk_decision: str
    category_decision: str
    budget_decision: str
    budget_status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class AuditLog:
    """Append-only JSONL des décisions du gate.

    Une instance par projet (chemin = workspace/.jarvis/audit.jsonl) OU une instance
    globale (chemin = memory_data/audit.jsonl) — au choix du caller.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, entry: AuditEntry) -> None:
        """Ajoute une entrée. Sérialise la datetime en ISO."""
        d = asdict(entry)
        d["timestamp"] = entry.timestamp.isoformat()
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def read_all(self) -> list[AuditEntry]:
        """Relit toutes les entrées (tests, curator, debug)."""
        if not self._path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            entries.append(
                AuditEntry(
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    decision=d["decision"],
                    context_id=d["context_id"],
                    access_level=d["access_level"],
                    action_category=d["action_category"],
                    estimated_cost_usd=d["estimated_cost_usd"],
                    risk_decision=d["risk_decision"],
                    category_decision=d["category_decision"],
                    budget_decision=d["budget_decision"],
                    budget_status=d.get("budget_status"),
                    extra=d.get("extra", {}),
                )
            )
        return entries
