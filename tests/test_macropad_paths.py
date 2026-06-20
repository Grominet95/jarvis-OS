"""Tests unitaires de hardware.macropad_2k.paths (resolution de chemins)."""

from __future__ import annotations

import sys
from pathlib import Path

from jarvis.hardware.macropad_2k import paths


def test_sketch_dir_uses_workspace(tmp_path: Path) -> None:
    assert paths.sketch_dir(tmp_path) == tmp_path / "CH552_HID_Keyboard"


def test_sketch_dir_defaults_to_firmware_root() -> None:
    assert paths.sketch_dir(None) == paths.firmware_root() / "CH552_HID_Keyboard"


def test_sketch_ino_path(tmp_path: Path) -> None:
    expected = tmp_path / "CH552_HID_Keyboard" / "CH552_HID_Keyboard.ino"
    assert paths.sketch_ino(tmp_path) == expected


def test_generated_dir(tmp_path: Path) -> None:
    assert paths.generated_dir(tmp_path) == tmp_path / "CH552_HID_Keyboard" / "generated"


def test_usb_hid_dir(tmp_path: Path) -> None:
    expected = tmp_path / "CH552_HID_Keyboard" / "src" / "userUsbHidKeyboard"
    assert paths.usb_hid_dir(tmp_path) == expected


def test_profile_path(tmp_path: Path) -> None:
    assert paths.profile_path(tmp_path) == tmp_path / "keypad-studio-profile.json"


def test_firmware_root_under_keypad_root() -> None:
    assert paths.firmware_root() == paths.keypad_root() / "firmware"


def test_arduino_cli_executable_extension() -> None:
    exe = paths.arduino_cli_executable()
    if sys.platform.startswith("win"):
        assert exe.name == "arduino-cli.exe"
    else:
        assert exe.name == "arduino-cli"


def test_is_valid_workspace_false_when_no_ino(tmp_path: Path) -> None:
    assert paths.is_valid_workspace(tmp_path) is False


def test_is_valid_workspace_true_with_ino(tmp_path: Path) -> None:
    ino = paths.sketch_ino(tmp_path)
    ino.parent.mkdir(parents=True, exist_ok=True)
    ino.write_text("// sketch", encoding="utf-8")
    assert paths.is_valid_workspace(tmp_path) is True


def test_is_valid_workspace_accepts_str(tmp_path: Path) -> None:
    ino = paths.sketch_ino(tmp_path)
    ino.parent.mkdir(parents=True, exist_ok=True)
    ino.write_text("// sketch", encoding="utf-8")
    assert paths.is_valid_workspace(str(tmp_path)) is True
