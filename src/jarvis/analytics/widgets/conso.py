# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Widget Consommation & Coûts — depuis memory_data/conso/."""

import json
from datetime import date, timedelta

from jarvis.analytics.widgets.base import WidgetBase, WidgetData
from jarvis.kernel.paths import MEMORY_DATA_DIR


class ConsoWidget(WidgetBase):
    id = "conso"
    label = "Conso & Coûts"
    description = "Coûts et tokens Jarvis sur 7 et 30 jours."
    icon = "$"
    requires_env = []
    size = "medium"

    async def fetch(self) -> WidgetData:
        try:
            conso_dir = MEMORY_DATA_DIR / "conso"
            daily_costs = {}

            for i in range(30):
                d = (date.today() - timedelta(days=i)).isoformat()
                f = conso_dir / f"{d}.jsonl"
                cost = 0.0
                tokens = 0
                if f.exists():
                    for line in f.read_text().splitlines():
                        if line.strip():
                            entry = json.loads(line)
                            cost += entry.get("cost_usd", 0)
                            tokens += entry.get("input_tokens", 0)
                            tokens += entry.get("output_tokens", 0)
                daily_costs[d] = {"cost": round(cost, 4), "tokens": tokens}

            total_7d = sum(v["cost"] for k, v in list(daily_costs.items())[:7])
            total_30d = sum(v["cost"] for v in daily_costs.values())

            return WidgetData(
                success=True,
                data={
                    "daily": daily_costs,
                    "total_7d": round(total_7d, 4),
                    "total_30d": round(total_30d, 4),
                },
            )
        except Exception as e:
            return WidgetData(success=False, data={}, error=str(e))
