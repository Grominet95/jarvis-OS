from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def keypad_root() -> Path:
    return Path(__file__).resolve().parent


def firmware_root() -> Path:
    return keypad_root() / "firmware"


def sketch_dir(workspace: Path | None = None) -> Path:
    base = workspace if workspace is not None else firmware_root()
    return Path(base) / "CH552_HID_Keyboard"


def sketch_ino(workspace: Path | None = None) -> Path:
    return sketch_dir(workspace) / "CH552_HID_Keyboard.ino"


def generated_dir(workspace: Path | None = None) -> Path:
    return sketch_dir(workspace) / "generated"


def usb_hid_dir(workspace: Path | None = None) -> Path:
    return sketch_dir(workspace) / "src" / "userUsbHidKeyboard"


def tools_root() -> Path:
    p = project_root() / "tools"
    p.mkdir(parents=True, exist_ok=True)
    return p


def arduino_cli_dir() -> Path:
    p = tools_root() / "arduino-cli"
    p.mkdir(parents=True, exist_ok=True)
    return p


def arduino_cli_executable() -> Path:
    name = "arduino-cli.exe" if sys.platform.startswith("win") else "arduino-cli"
    return arduino_cli_dir() / name


def build_dir(workspace: Path | None = None) -> Path:
    base = workspace if workspace is not None else firmware_root()
    return Path(base) / "build" / "CH552_HID_Keyboard"


def output_dir(workspace: Path | None = None) -> Path:
    base = workspace if workspace is not None else firmware_root()
    return Path(base) / "Object File1"


def profile_path(workspace: Path | None = None) -> Path:
    base = workspace if workspace is not None else firmware_root()
    return Path(base) / "keypad-studio-profile.json"


def profile_export_path(workspace: Path | None = None) -> Path:
    return generated_dir(workspace) / "keypad_profile.json"


def workspace_state_path() -> Path:
    base = project_root() / "memory_data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "keypad_workspace.json"


def launchers_dir() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
    p = Path(home) / ".lelabo" / "launchers"
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_valid_workspace(path: Path | str) -> bool:
    p = Path(path) if not isinstance(path, Path) else path
    return sketch_ino(p).is_file()
