# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
import sys
import threading
import types
from typing import Any

from jarvis.kernel.error_collector import collector
from jarvis.kernel.errors import JarvisError


def _handle_uncaught(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: types.TracebackType | None,
) -> None:
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc, tb)
        return
    if isinstance(exc, JarvisError):
        collector.error(exc.code, exc.message, cause=exc.cause or exc)
    else:
        collector.error(
            "JRV-UNK-001",
            f"Uncaught {exc_type.__name__}: {exc}",
            cause=exc,
        )
    sys.__excepthook__(exc_type, exc, tb)


def _asyncio_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    exc = context.get("exception")
    msg = context.get("message", "asyncio task failure")
    if exc is not None:
        collector.error("JRV-UNK-001", msg, cause=exc)
    else:
        collector.error("JRV-UNK-001", msg)


def _thread_handler(args: threading.ExceptHookArgs) -> None:
    collector.error(
        "JRV-UNK-001",
        f"Thread {args.thread.name} failed",
        cause=args.exc_value,
    )


def install_error_hooks() -> None:
    sys.excepthook = _handle_uncaught
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_handler  # type: ignore[attr-defined]


def install_asyncio_handler(loop: asyncio.AbstractEventLoop | None = None) -> None:
    try:
        target = loop or asyncio.get_running_loop()
    except RuntimeError:  # jrv: no running loop at hook install
        try:
            target = asyncio.get_event_loop()
        except RuntimeError:  # jrv: no event loop fallback failed
            return
    target.set_exception_handler(_asyncio_handler)
