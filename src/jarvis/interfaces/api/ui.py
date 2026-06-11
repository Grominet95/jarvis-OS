from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


def _versioned_html(html_path: Path, assets: list[tuple[str, str]]) -> str:
    """Injecte ?v=<mtime> dans les refs CSS/JS pour forcer le cache-busting."""
    content = html_path.read_text(encoding="utf-8")
    for src_attr, asset_path in assets:
        try:
            v = int(Path(asset_path).stat().st_mtime)
            content = re.sub(
                r'((?:href|src)=["\'])(' + re.escape(src_attr) + r')(["\'])',
                lambda m, _v=v: m.group(1) + m.group(2) + "?v=" + str(_v) + m.group(3),
                content,
            )
        except OSError:
            pass
    return content


@router.get("/command", include_in_schema=False)
async def command_center_ui() -> FileResponse:
    return FileResponse("src/jarvis/interfaces/ui/static/command.html")


@router.get("/dashboard", include_in_schema=False)
async def dashboard_ui() -> Response:
    from fastapi.responses import Response as FastResponse

    content = _versioned_html(
        Path("src/jarvis/interfaces/ui/static/dashboard.html"),
        [
            ("/_shared.css", "src/jarvis/interfaces/ui/static/_shared.css"),
            ("/dashboard.css", "src/jarvis/interfaces/ui/static/dashboard.css"),
            ("/_shared.js", "src/jarvis/interfaces/ui/static/_shared.js"),
            ("/dashboard.js", "src/jarvis/interfaces/ui/static/dashboard.js"),
        ],
    )
    return FastResponse(
        content=content, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


@router.get("/settings", include_in_schema=False)
async def settings_ui() -> Response:
    from fastapi.responses import Response as FastResponse

    content = _versioned_html(
        Path("src/jarvis/interfaces/ui/static/settings.html"),
        [
            ("/_shared.css", "src/jarvis/interfaces/ui/static/_shared.css"),
            ("/settings.css", "src/jarvis/interfaces/ui/static/settings.css"),
            ("/_shared.js", "src/jarvis/interfaces/ui/static/_shared.js"),
            ("/settings-charts.js", "src/jarvis/interfaces/ui/static/settings-charts.js"),
            ("/settings.js", "src/jarvis/interfaces/ui/static/settings.js"),
        ],
    )
    return FastResponse(
        content=content, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


@router.get("/", include_in_schema=False)
async def home_ui() -> Response:
    from fastapi.responses import Response as FastResponse

    content = _versioned_html(
        Path("src/jarvis/interfaces/ui/static/home.html"),
        [
            ("/_shared.css", "src/jarvis/interfaces/ui/static/_shared.css"),
            ("/home.css", "src/jarvis/interfaces/ui/static/home.css"),
            ("/_shared.js", "src/jarvis/interfaces/ui/static/_shared.js"),
            ("/three.min.js", "src/jarvis/interfaces/ui/static/three.min.js"),
            ("/orb.js", "src/jarvis/interfaces/ui/static/orb.js"),
            ("/home.js", "src/jarvis/interfaces/ui/static/home.js"),
        ],
    )
    return FastResponse(
        content=content, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


@router.get("/capabilities", include_in_schema=False)
async def capabilities_ui() -> Response:
    from fastapi.responses import Response as FastResponse

    content = _versioned_html(
        Path("src/jarvis/interfaces/ui/static/capabilities.html"),
        [
            ("/_shared.css", "src/jarvis/interfaces/ui/static/_shared.css"),
            ("/capabilities.css", "src/jarvis/interfaces/ui/static/capabilities.css"),
            ("/_shared.js", "src/jarvis/interfaces/ui/static/_shared.js"),
            ("/capabilities.js", "src/jarvis/interfaces/ui/static/capabilities.js"),
        ],
    )
    return FastResponse(
        content=content, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Point de contrôle — vérifie que le serveur est up."""
    return HealthResponse(status="ok", version="0.1.0")
