# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult

_TIMEOUT = 20.0
_MAX_TEXT_LEN = 8000  # chars max retournés au LLM
_MAX_LINKS = 25

# Hôtes internes/locaux bloqués — jamais d'accès au réseau interne
_BLOCKED_HOST_RE = re.compile(
    r"^("
    r"localhost"
    r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|0\.0\.0\.0"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|::1"
    r"|.*\.local"
    r")$",
    re.IGNORECASE,
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Jarvis/1.0; personal assistant; +https://github.com/Grominet95)"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def _validate_url(url: str) -> str | None:
    """Retourne un message d'erreur si l'URL est invalide ou bloquée, None sinon."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "URL invalide."
    if parsed.scheme not in ("http", "https"):
        return f"Schéma non supporté : '{parsed.scheme}'. Seuls http et https sont autorisés."
    host = parsed.hostname or ""
    if not host:
        return "URL sans hôte."
    if _BLOCKED_HOST_RE.match(host):
        return "Accès aux ressources locales/internes interdit par sécurité."
    return None


class BrowserTool(Tool):
    """Navigation web : extraction de texte, liens et recherche DuckDuckGo.

    Basé sur httpx + BeautifulSoup4 (sites HTML statiques).
    Pour les sites JavaScript-heavy, une intégration Playwright peut être
    ajoutée ultérieurement (uv add playwright && playwright install chromium).

    Sécurité :
    - Accès aux hôtes internes bloqué (localhost, 192.168.x, 10.x…)
    - Seuls http/https autorisés
    - Timeout strict de 20s
    - Contenu tronqué à 8000 caractères pour limiter le context LLM
    """

    name = "browser"
    description = (
        "Navigue sur le web pour extraire du contenu ou faire une recherche. "
        "Actions : "
        "'get_text' (extrait le texte principal d'une page web), "
        "'get_links' (liste les liens d'une page), "
        "'search' (recherche DuckDuckGo, retourne les 5 premiers résultats). "
        "Exemples : météo, actualités, documentation, prix, horaires."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_text", "get_links", "search"],
                "description": "Action à effectuer.",
            },
            "url": {
                "type": "string",
                "description": "URL complète (requis pour get_text et get_links).",
            },
            "query": {
                "type": "string",
                "description": "Terme de recherche (requis pour search).",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: str,
        url: str = "",
        query: str = "",
        **_: object,
    ) -> ToolResult:
        if action == "search":
            return await self._search(query)

        if action in ("get_text", "get_links"):
            err = _validate_url(url)
            if err:
                return ToolResult(content=err, is_error=True)
            if action == "get_text":
                return await self._get_text(url)
            return await self._get_links(url)

        return ToolResult(content=f"Action inconnue : '{action}'.", is_error=True)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _fetch_html(self, url: str) -> tuple[str, str | None]:
        """Retourne (html, erreur_ou_None)."""
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=True,
                headers=_HEADERS,
            ) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.text, None
        except httpx.TimeoutException:
            return "", f"Timeout ({_TIMEOUT}s) pour {url}."
        except httpx.HTTPStatusError as e:
            return "", f"HTTP {e.response.status_code} sur {url}."
        except httpx.RequestError as e:
            return "", f"Erreur réseau : {e}."

    def _require_bs4(self) -> str | None:
        """Retourne un message d'erreur si bs4 n'est pas installé."""
        try:
            import bs4  # noqa: F401

            return None
        except ImportError:
            return "beautifulsoup4 non installé. Lance : uv add beautifulsoup4 lxml"

    async def _get_text(self, url: str) -> ToolResult:
        bs4_err = self._require_bs4()
        if bs4_err:
            return ToolResult(content=bs4_err, is_error=True)

        html, err = await self._fetch_html(url)
        if err:
            return ToolResult(content=err, is_error=True)

        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        soup = BeautifulSoup(html, "lxml")
        # Supprimer les éléments non-contenus
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s{2,}", " ", text).strip()
        text = text[:_MAX_TEXT_LEN]
        if len(text) == _MAX_TEXT_LEN:
            text += "\n[contenu tronqué à 8000 caractères]"

        logger.debug("BrowserTool get_text", url=url, chars=len(text))
        return ToolResult(content=text or "Aucun contenu textuel trouvé sur cette page.")

    async def _get_links(self, url: str) -> ToolResult:
        bs4_err = self._require_bs4()
        if bs4_err:
            return ToolResult(content=bs4_err, is_error=True)

        html, err = await self._fetch_html(url)
        if err:
            return ToolResult(content=err, is_error=True)

        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        soup = BeautifulSoup(html, "lxml")
        seen: set[str] = set()
        lines: list[str] = []

        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if not href.startswith("http") or href in seen:
                continue
            seen.add(href)
            text = a.get_text(strip=True) or href
            lines.append(f"- {text[:80]}: {href}")
            if len(lines) >= _MAX_LINKS:
                break

        logger.debug("BrowserTool get_links", url=url, count=len(lines))
        return ToolResult(content="\n".join(lines) or "Aucun lien trouvé sur cette page.")

    async def _search(self, query: str) -> ToolResult:
        if not query.strip():
            return ToolResult(content="'query' requis pour l'action search.", is_error=True)

        bs4_err = self._require_bs4()
        if bs4_err:
            return ToolResult(content=bs4_err, is_error=True)

        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}&kl=fr-fr"
        html, err = await self._fetch_html(search_url)
        if err:
            return ToolResult(content=err, is_error=True)

        from bs4 import BeautifulSoup  # type: ignore[import-untyped]

        soup = BeautifulSoup(html, "lxml")
        results: list[str] = []

        for result in soup.select(".result")[:5]:
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            url_el = result.select_one(".result__url")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            link = url_el.get_text(strip=True) if url_el else ""
            parts = [f"**{title}**"]
            if snippet:
                parts.append(snippet)
            if link:
                parts.append(f"→ {link}")
            results.append("\n".join(parts))

        logger.debug("BrowserTool search", query=query, results=len(results))
        return ToolResult(
            content="\n\n---\n\n".join(results) if results else "Aucun résultat trouvé."
        )
