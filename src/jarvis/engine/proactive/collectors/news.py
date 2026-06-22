# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
NewsCollector — agrège les actualités pertinentes via RSS.
Sources : tech française et internationale, maker, IA, business.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import feedparser
from loguru import logger

from jarvis.engine.proactive.collectors.base import CollectorBase
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority
from jarvis.kernel.connectivity import is_offline_mode

RSS_FEEDS = [
    {"url": "https://www.frandroid.com/feed", "category": "tech_fr"},
    {"url": "https://next.ink/feed/", "category": "tech_fr"},
    {"url": "https://techcrunch.com/feed/", "category": "tech_en"},
    {"url": "https://www.theverge.com/rss/index.xml", "category": "tech_en"},
    {"url": "https://hackaday.com/feed/", "category": "maker"},
    {"url": "https://blog.adafruit.com/feeds/all.atom.xml", "category": "maker"},
    {"url": "https://www.maddyness.com/feed/", "category": "business_fr"},
]

RELEVANT_KEYWORDS = [
    "esp32",
    "raspberry pi",
    "arduino",
    "pcb",
    "cnc",
    "nfc",
    "iot",
    "llm",
    "gpt",
    "claude",
    "mistral",
    "openai",
    "ia",
    "ai",
    "maker",
    "embedded",
    "firmware",
    "electronics",
    "startup",
    "levée de fonds",
    "youtube",
    "créateur",
]


class NewsCollector(CollectorBase):
    name = "news"

    async def _collect(self) -> list[ContextItem]:
        if is_offline_mode():
            logger.debug("NewsCollector ignoré — mode local")
            return []

        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, self._fetch_feed, feed) for feed in RSS_FEEDS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items = []
        for result in results:
            if isinstance(result, list):
                items.extend(result)

        items.sort(key=lambda x: x.priority == Priority.HIGH, reverse=True)
        return items[:15]

    def _fetch_feed(self, feed_config: dict) -> list[ContextItem]:
        try:
            feed = feedparser.parse(feed_config["url"])
            items = []

            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")[:300]

                text = (title + " " + summary).lower()
                is_relevant = any(kw in text for kw in RELEVANT_KEYWORDS)

                if not is_relevant:
                    continue

                items.append(
                    ContextItem(
                        type=ItemType.NEWS,
                        title=title,
                        summary=summary,
                        raw=f"{title}\n{summary}",
                        source=feed_config["category"],
                        timestamp=datetime.now(),
                        priority=Priority.LOW,
                        metadata={"url": entry.get("link", "")},
                    )
                )

            return items
        except Exception:
            return []
