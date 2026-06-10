"""Widget GitHub — stars, forks, commits récents."""

import asyncio
import os

import httpx

from jarvis.analytics.widgets.base import WidgetBase, WidgetData


class GitHubWidget(WidgetBase):
    id = "github"
    label = "GitHub"
    description = "Stars, forks et activité du repo Jarvis."
    icon = "G"
    requires_env = ["GITHUB_TOKEN", "GITHUB_REPO"]
    size = "small"

    async def fetch(self) -> WidgetData:
        if not self.is_configured():
            return WidgetData(success=False, data={}, error="Config manquante")

        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPO", "").strip().rstrip("/")
        # Accepte URL complète ou "owner/repo"
        if "github.com/" in repo:
            repo = repo.split("github.com/")[-1]

        try:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                repo_r, prs_r = await asyncio.gather(
                    client.get(f"https://api.github.com/repos/{repo}"),
                    client.get(
                        f"https://api.github.com/repos/{repo}/pulls",
                        params={"state": "open", "per_page": 100},
                    ),
                )
                data = repo_r.json()
                open_prs = len(prs_r.json()) if isinstance(prs_r.json(), list) else 0
                open_issues_total = data.get("open_issues_count", 0)

                return WidgetData(
                    success=True,
                    data={
                        "stars": data.get("stargazers_count", 0),
                        "forks": data.get("forks_count", 0),
                        "watchers": data.get("subscribers_count", 0),
                        "open_issues": max(0, open_issues_total - open_prs),
                        "open_prs": open_prs,
                    },
                )
        except Exception as e:
            return WidgetData(success=False, data={}, error=str(e))
