# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Widget Jarvis Stats — données internes, aucune API externe."""

import json
from datetime import date, timedelta

from jarvis.analytics.widgets.base import WidgetBase, WidgetData
from jarvis.kernel.paths import MEMORY_DATA_DIR


class JarvisStatsWidget(WidgetBase):
    id = "jarvis_stats"
    label = "Jarvis Stats"
    description = "Conversations, missions, tokens et coûts Jarvis."
    icon = "J"
    requires_env = []
    size = "medium"

    async def fetch(self) -> WidgetData:
        try:
            # Compter les sessions depuis memory_data/sessions/
            sessions_dir = MEMORY_DATA_DIR / "sessions"
            session_files = list(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else []

            # Compter les missions
            projects_file = MEMORY_DATA_DIR / "projects.json"
            projects = []
            if projects_file.exists():
                projects = json.loads(projects_file.read_text())

            # Lire la conso du jour depuis memory_data/conso/
            today = date.today().isoformat()
            conso_file = MEMORY_DATA_DIR / "conso" / f"{today}.jsonl"
            total_cost = 0.0
            total_tokens = 0
            if conso_file.exists():
                for line in conso_file.read_text().splitlines():
                    if line.strip():
                        entry = json.loads(line)
                        total_cost += entry.get("cost_usd", 0)
                        total_tokens += entry.get("input_tokens", 0)
                        total_tokens += entry.get("output_tokens", 0)

            # Compter les sessions des 7 derniers jours
            sessions_7d = 0
            for i in range(7):
                d = (date.today() - timedelta(days=i)).isoformat()
                f = sessions_dir / f"{d}.jsonl"
                if f.exists():
                    sessions_7d += sum(1 for line in f.read_text().splitlines() if line.strip())

            return WidgetData(
                success=True,
                data={
                    "sessions_total": len(session_files),
                    "sessions_7d": sessions_7d,
                    "missions_total": len(projects),
                    "missions_done": len([p for p in projects if p.get("status") == "completed"]),
                    "cost_today": round(total_cost, 4),
                    "tokens_today": total_tokens,
                },
            )
        except Exception as e:
            return WidgetData(success=False, data={}, error=str(e))
