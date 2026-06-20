"""Tests unitaires de kernel.file_lock (verrou exclusif cross-platform)."""

from __future__ import annotations

from pathlib import Path

from jarvis.kernel.file_lock import exclusive_file_lock


def test_creates_lock_file(tmp_path: Path) -> None:
    lock = tmp_path / "sub" / "dir" / "x.lock"
    with exclusive_file_lock(lock):
        assert lock.exists()


def test_creates_parent_dirs(tmp_path: Path) -> None:
    lock = tmp_path / "a" / "b" / "c.lock"
    assert not lock.parent.exists()
    with exclusive_file_lock(lock):
        pass
    assert lock.parent.exists()


def test_sequential_reacquire(tmp_path: Path) -> None:
    lock = tmp_path / "seq.lock"
    with exclusive_file_lock(lock):
        pass
    with exclusive_file_lock(lock):
        pass


def test_yields_inside_critical_section(tmp_path: Path) -> None:
    lock = tmp_path / "crit.lock"
    entered = False
    with exclusive_file_lock(lock):
        entered = True
    assert entered


def test_releases_on_exception(tmp_path: Path) -> None:
    lock = tmp_path / "exc.lock"
    try:
        with exclusive_file_lock(lock):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with exclusive_file_lock(lock):
        pass
