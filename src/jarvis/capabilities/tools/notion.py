from __future__ import annotations

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.settings import settings


class NotionTasksTool(Tool):
    """Récupère les tâches non cochées de la section 'Tâches du jour' de Notion."""

    name = "notion_tasks"
    description = (
        "Récupère les tâches non cochées de la section 'Tâches du jour' de la page Notion de Barth."
    )
    input_schema: dict = {  # noqa: RUF012
        "type": "object",
        "properties": {},
        "required": [],
    }

    _BASE_URL = "https://api.notion.com/v1"
    _NOTION_VERSION = "2022-06-28"

    async def execute(self, **kwargs: object) -> ToolResult:
        token = settings.notion_token
        page_id = settings.notion_page_id
        if not token or not page_id:
            return ToolResult(
                content="Notion non configuré (token ou page_id manquant).",
                is_error=True,
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self._NOTION_VERSION,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                tasks = await self._fetch_tasks(client, headers, page_id)
        except Exception as e:
            logger.error("NotionTasksTool error", error=str(e))
            return ToolResult(content=f"Erreur Notion : {e}", is_error=True)

        if not tasks:
            return ToolResult(content="Aucune tâche non cochée dans 'Tâches du jour'.")
        return ToolResult(content="\n".join(f"- {t}" for t in tasks))

    async def _fetch_tasks(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        page_id: str,
    ) -> list[str]:
        url = f"{self._BASE_URL}/blocks/{page_id}/children"
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        blocks = resp.json().get("results", [])

        in_section = False
        tasks: list[str] = []

        for block in blocks:
            btype = block.get("type", "")

            if btype.startswith("heading_"):
                rich_text = block.get(btype, {}).get("rich_text", [])
                text = "".join(rt.get("plain_text", "") for rt in rich_text)
                if "Tâches du jour" in text:
                    in_section = True
                elif in_section:
                    break
                continue

            if in_section and btype == "to_do":
                to_do_data = block.get("to_do", {})
                if not to_do_data.get("checked", False):
                    rich_text = to_do_data.get("rich_text", [])
                    text = "".join(rt.get("plain_text", "") for rt in rich_text)
                    if text.strip():
                        tasks.append(text.strip())

        return tasks
