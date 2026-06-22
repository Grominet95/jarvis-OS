# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

_KEYS: frozenset[str] = frozenset({"microphone", "screen", "camera", "files"})


class PermissionStore:
    """Permissions runtime accordées par l'utilisateur depuis l'UI."""

    def __init__(self) -> None:
        self._state: dict[str, bool] = {
            "microphone": True,
            "screen": False,
            "camera": False,
            "files": False,
        }

    def get(self, key: str) -> bool:
        return self._state.get(key, True)

    def set(self, key: str, value: bool) -> None:
        if key in _KEYS:
            self._state[key] = value

    def all(self) -> dict[str, bool]:
        return dict(self._state)


permissions = PermissionStore()
