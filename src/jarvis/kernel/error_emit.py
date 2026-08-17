# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Stdlib-only terminal error emission (preflight-safe)."""

from __future__ import annotations

import sys

_LEVEL_PREFIX = {
    "error": "ERROR",
    "warning": "WARN",
    "impossible": "IMPOSSIBLE",
}


def emit_to_stderr(code: str, message: str, *, level: str = "error") -> None:
    prefix = _LEVEL_PREFIX.get(level, level.upper())
    line = f"[{code}] {prefix}: {message}"
    print(line, file=sys.stderr, flush=True)
