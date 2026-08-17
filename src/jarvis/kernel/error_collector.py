# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Central error collector — always emits JRV codes to stderr."""

from __future__ import annotations

import traceback
from typing import Any

from loguru import logger

from jarvis.kernel._error_codes_generated import ERROR_REGISTRY
from jarvis.kernel.error_emit import emit_to_stderr

_LEVEL_TO_SEVERITY = {
    "error": "error",
    "warning": "warning",
    "impossible": "error",
}


def _format_message(code: str, message: str, cause: BaseException | None) -> str:
    spec = ERROR_REGISTRY.get(code, {})
    title = spec.get("title_fr") or message
    if cause and str(cause) and str(cause) not in message:
        return f"{title} — {message} ({type(cause).__name__}: {cause})"
    if message and message != title:
        return f"{title} — {message}"
    return title


class ErrorCollector:
    def emit(
        self,
        code: str,
        message: str,
        *,
        level: str = "error",
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        if code not in ERROR_REGISTRY and not code.startswith("JRV-"):
            code = "JRV-ENG-000"
        spec = ERROR_REGISTRY.get(code, {})
        severity = spec.get("severity") or _LEVEL_TO_SEVERITY.get(level, "error")
        emit_level = "warning" if severity == "warning" else level
        formatted = _format_message(code, message, cause)
        emit_to_stderr(code, formatted, level=emit_level)
        log_fn = logger.warning if severity == "warning" else logger.error
        log_fn(
            formatted,
            code=code,
            domain=spec.get("domain"),
            context=context or {},
        )
        if cause is not None:
            logger.debug(
                "Error cause traceback:\n{}",
                "".join(traceback.format_exception(type(cause), cause, cause.__traceback__)),
            )

    def error(
        self,
        code: str,
        message: str,
        *,
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.emit(code, message, level="error", cause=cause, context=context)

    def warning(
        self,
        code: str,
        message: str,
        *,
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.emit(code, message, level="warning", cause=cause, context=context)

    def impossible(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.emit("JRV-ENG-999", message, level="impossible", cause=cause, context=context)


collector = ErrorCollector()
