# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Hiérarchie d'exceptions Jarvis (CDC §A.1.3)."""

from __future__ import annotations

from typing import Any


class JarvisError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause
        self.context = context or {}


class LLMError(JarvisError):
    pass


class MemoryError_(JarvisError):  # noqa: N801
    pass


class ToolError(JarvisError):
    pass


class SkillError(JarvisError):
    pass


class BudgetExceeded(JarvisError):
    pass


class PermissionDenied(JarvisError):
    pass
