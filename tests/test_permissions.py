"""Tests unitaires de kernel.permissions (PermissionStore runtime)."""

from __future__ import annotations

from jarvis.kernel.permissions import PermissionStore


def test_defaults() -> None:
    store = PermissionStore()
    assert store.get("microphone") is True
    assert store.get("screen") is False
    assert store.get("camera") is False
    assert store.get("files") is False


def test_set_known_key() -> None:
    store = PermissionStore()
    store.set("camera", True)
    assert store.get("camera") is True


def test_set_unknown_key_ignored() -> None:
    store = PermissionStore()
    store.set("unknown_perm", True)
    assert store.get("unknown_perm") is True
    assert "unknown_perm" not in store.all()


def test_get_unknown_defaults_true() -> None:
    store = PermissionStore()
    assert store.get("not_tracked") is True


def test_all_returns_copy() -> None:
    store = PermissionStore()
    snapshot = store.all()
    snapshot["microphone"] = False
    assert store.get("microphone") is True


def test_all_contains_all_known_keys() -> None:
    store = PermissionStore()
    assert set(store.all()) == {"microphone", "screen", "camera", "files"}


def test_toggle_persists_on_instance() -> None:
    store = PermissionStore()
    store.set("screen", True)
    store.set("screen", False)
    assert store.get("screen") is False
