# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""HTTP errors with mandatory JRV stderr emission."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from jarvis.kernel.error_collector import collector


def raise_api_error(
    code: str,
    status_code: int,
    detail: str,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    collector.error(code, detail, cause=cause)
    raise HTTPException(
        status_code=status_code,
        detail=f"[{code}] {detail}",
        headers={"X-Jarvis-Error-Code": code},
    )
