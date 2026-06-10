from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from jarvis.hardware.macropad_2k.arduino_cli import (
    BOARD_INDEX,
    FQBN,
    ensure_arduino_cli,
    ensure_ch55x_core,
    run_cli,
)
from jarvis.hardware.macropad_2k.firmware_gen import generate
from jarvis.hardware.macropad_2k.ihex import ihex_to_bin_file
from jarvis.hardware.macropad_2k.models import KeypadProfile
from jarvis.hardware.macropad_2k.paths import (
    build_dir,
    output_dir,
    sketch_dir,
    sketch_ino,
)

ProgressCallback = Callable[[str], None]


def _set_blink_half_ms(ino_path: Path, ms: int) -> bool:
    if not ino_path.is_file():
        return False
    text = ino_path.read_text(encoding="utf-8")
    if text and ord(text[0]) == 0xFEFF:
        text = text[1:]
    pattern = re.compile(r"^(\s*#define\s+BLINK_HALF_PERIOD_MS\s+)\d+", re.MULTILINE)
    if not pattern.search(text):
        return False
    new_text = pattern.sub(rf"\g<1>{ms}", text, count=1)
    ino_path.write_text(new_text, encoding="utf-8")
    return True


def _sketch_uses_blink(ino_path: Path) -> bool:
    if not ino_path.is_file():
        return False
    return "#define BLINK_HALF_PERIOD_MS" in ino_path.read_text(encoding="utf-8", errors="ignore")


def _hz_to_blink_half_ms(hz: float) -> int:
    return max(1, round(500.0 / hz))


def compile_firmware(
    workspace: Path,
    profile: KeypadProfile,
    blink_hz: float | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    workspace = workspace.resolve()
    sketch = sketch_dir(workspace)
    ino = sketch_ino(workspace)
    if not ino.is_file():
        raise FileNotFoundError(f"sketch not found: {ino}")

    cli = ensure_arduino_cli(progress=progress)
    log_parts: list[str] = []

    log_parts.append(ensure_ch55x_core(cli, progress=progress))

    if _sketch_uses_blink(ino):
        hz = blink_hz if blink_hz and blink_hz > 0 else 2.0
        half = _hz_to_blink_half_ms(hz)
        if _set_blink_half_ms(ino, half):
            log_parts.append(f"BLINK_HALF_PERIOD_MS = {half} (from {hz} Hz)\n")

    if progress:
        progress("Generating firmware headers from profile")
    generate(profile, workspace)

    build = build_dir(workspace)
    build.mkdir(parents=True, exist_ok=True)
    out = output_dir(workspace)
    out.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("Compiling sketch with arduino-cli")
    code, log = run_cli(
        cli,
        [
            "compile",
            "--fqbn",
            FQBN,
            "--output-dir",
            str(build),
            "--additional-urls",
            BOARD_INDEX,
            str(sketch),
        ],
        cwd=workspace,
    )
    log_parts.append(log)
    if code != 0:
        raise RuntimeError("compile failed:\n" + "".join(log_parts))

    hex_files = sorted(build.glob("*.hex"))
    if not hex_files:
        raise RuntimeError(f"no .hex produced under {build}")
    src_hex = hex_files[0]
    bin_path = out / "firmware.bin"
    hex_copy = out / "firmware.hex"
    shutil.copyfile(src_hex, hex_copy)
    if progress:
        progress("Converting Intel HEX to binary")
    ihex_to_bin_file(src_hex, bin_path)

    log_parts.append(f"OK: {bin_path}\nOK: {hex_copy}\n")
    return {
        "ok": True,
        "output": "".join(log_parts),
        "binPath": str(bin_path),
        "hexPath": str(hex_copy),
    }


def upload_firmware_arduino_cli(
    workspace: Path,
    progress: ProgressCallback | None = None,
    attempts: int = 1,
) -> dict:
    workspace = workspace.resolve()
    sketch = sketch_dir(workspace)
    build = build_dir(workspace)
    out = output_dir(workspace)
    bin_path = out / "firmware.bin"
    if not bin_path.is_file():
        raise FileNotFoundError(f"missing {bin_path} (compile first)")
    if not any(build.glob("*.hex")):
        raise FileNotFoundError(f"no .hex in {build} (compile first)")

    cli = ensure_arduino_cli(progress=progress)
    ensure_ch55x_core(cli, progress=progress)

    args = [
        "upload",
        "--fqbn",
        FQBN,
        "--input-dir",
        str(build),
        "--additional-urls",
        BOARD_INDEX,
        str(sketch),
    ]

    log = ""
    last_code = 0
    for n in range(1, max(1, attempts) + 1):
        if progress:
            progress(f"Uploading firmware (attempt {n}/{attempts})")
        code, attempt_log = run_cli(cli, args, cwd=workspace)
        log += attempt_log
        last_code = code
        if code == 0:
            return {"ok": True, "output": log}
        time.sleep(0.5)

    raise RuntimeError(f"arduino-cli upload failed (code {last_code}):\n{log}")


def upload_firmware_python(
    workspace: Path,
    progress: ProgressCallback | None = None,
) -> dict:
    workspace = workspace.resolve()
    bin_path = output_dir(workspace) / "firmware.bin"
    if not bin_path.is_file():
        raise FileNotFoundError(f"missing {bin_path} (compile first)")

    try:
        import libusb_package  # noqa: F401
        import usb.backend.libusb1  # noqa: F401
        import usb.core  # noqa: F401
    except Exception as exc:
        raise RuntimeError("pyusb/libusb-package missing") from exc

    if progress:
        progress("Flashing via ch55xtool (Python)")

    cmd = [sys.executable, "-m", "ch55xtool.ch55xtool", "-f", str(bin_path), "-r"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"ch55xtool failed (code {proc.returncode}):\n{out}")
    return {"ok": True, "output": out}


def upload_firmware(
    workspace: Path,
    progress: ProgressCallback | None = None,
    prefer_python: bool = False,
    attempts: int = 1,
) -> dict:
    if prefer_python:
        try:
            return upload_firmware_python(workspace, progress=progress)
        except Exception as exc:
            logger.warning("Python upload failed, falling back to arduino-cli: {}", exc)
    return upload_firmware_arduino_cli(workspace, progress=progress, attempts=attempts)
