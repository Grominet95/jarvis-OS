# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""FastAPI exception handlers for JarvisError."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from jarvis.kernel.error_collector import collector
from jarvis.kernel.errors import JarvisError


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = str(exc.detail)
    code = "JRV-API-001"
    if detail.startswith("[JRV-"):
        end = detail.find("]")
        if end > 5:
            code = detail[1:end]
            detail = detail[end + 2 :].lstrip()
    else:
        collector.error(code, detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": code},
        headers={"X-Jarvis-Error-Code": code},
    )


async def jarvis_error_handler(_request: Request, exc: JarvisError) -> JSONResponse:
    collector.error(exc.code, exc.message, cause=exc.cause or exc, context=exc.context)
    status = 403 if exc.code.startswith("JRV-PRM-") else 500
    return JSONResponse(
        status_code=status,
        content={"detail": exc.message, "code": exc.code},
        headers={"X-Jarvis-Error-Code": exc.code},
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, JarvisError):
        return await jarvis_error_handler(_request, exc)
    collector.error("JRV-UNK-001", f"Unhandled API error: {exc}", cause=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur serveur.", "code": "JRV-UNK-001"},
        headers={"X-Jarvis-Error-Code": "JRV-UNK-001"},
    )
