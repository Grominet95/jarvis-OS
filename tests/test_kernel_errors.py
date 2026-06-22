# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests de la hiérarchie d'exceptions kernel.errors (CDC §A.1.3)."""

from __future__ import annotations

import pytest

from jarvis.kernel.errors import (
    BudgetExceeded,
    JarvisError,
    LLMError,
    MemoryError_,
    PermissionDenied,
    SkillError,
    ToolError,
)


def test_jarvis_error_is_root() -> None:
    assert issubclass(JarvisError, Exception)


@pytest.mark.parametrize(
    "exc",
    [LLMError, MemoryError_, ToolError, SkillError, BudgetExceeded, PermissionDenied],
)
def test_all_descend_from_jarvis_error(exc: type[Exception]) -> None:
    assert issubclass(exc, JarvisError)


def test_catching_jarvis_error_catches_subclasses() -> None:
    """Une couche haute doit pouvoir attraper toute la famille via JarvisError seul."""
    families = (LLMError, MemoryError_, ToolError, SkillError, BudgetExceeded, PermissionDenied)
    for exc_cls in families:
        with pytest.raises(JarvisError):
            raise exc_cls("boom")


def test_memory_error_does_not_shadow_builtin() -> None:
    """Le nom `MemoryError_` (avec underscore) évite de masquer le builtin MemoryError."""
    assert MemoryError_ is not MemoryError
    assert not issubclass(MemoryError_, MemoryError)
