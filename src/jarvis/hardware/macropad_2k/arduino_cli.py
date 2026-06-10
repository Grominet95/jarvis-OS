from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from jarvis.hardware.macropad_2k.paths import arduino_cli_dir, arduino_cli_executable

DEFAULT_VERSION = "1.4.1"

BOARD_INDEX = (
    "https://raw.githubusercontent.com/DeqingSun/ch55xduino/ch55xduino/"
    "package_ch55xduino_mcs51_index.json"
)

FQBN = (
    "CH55xDuino:mcs51:ch552:"
    "clock=16internal,usb_settings=user148,upload_method=usb,bootloader_pin=p36"
)

ProgressCallback = Callable[[str], None]


def _detect_arduino_archive_name(version: str) -> tuple[str, str]:
    sys_name = platform.system()
    machine = platform.machine().lower()

    if sys_name == "Windows":
        if machine in ("amd64", "x86_64", "arm64", "aarch64"):
            base = "Windows_64bit"
            ext = "zip"
        else:
            base = "Windows_32bit"
            ext = "zip"
    elif sys_name == "Darwin":
        if machine in ("arm64", "aarch64"):
            base = "macOS_ARM64"
            ext = "tar.gz"
        else:
            base = "macOS_64bit"
            ext = "tar.gz"
    else:
        if machine in ("aarch64", "arm64"):
            base = "Linux_ARM64"
            ext = "tar.gz"
        elif machine.startswith("armv7"):
            base = "Linux_ARMv7"
            ext = "tar.gz"
        elif machine in ("x86_64", "amd64"):
            base = "Linux_64bit"
            ext = "tar.gz"
        else:
            base = "Linux_32bit"
            ext = "tar.gz"

    name = f"arduino-cli_{version}_{base}.{ext}"
    return name, ext


def arduino_cli_download_url(version: str = DEFAULT_VERSION) -> str:
    name, _ = _detect_arduino_archive_name(version)
    return f"https://github.com/arduino/arduino-cli/releases/download/v{version}/{name}"


def _extract_archive(archive: Path, dest: Path, ext: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if ext == "zip":
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest, filter="data")


def install_arduino_cli(
    version: str = DEFAULT_VERSION,
    progress: ProgressCallback | None = None,
) -> Path:
    exe = arduino_cli_executable()
    if exe.is_file():
        return exe

    url = arduino_cli_download_url(version)
    name, ext = _detect_arduino_archive_name(version)
    if progress:
        progress(f"Downloading {name} from {url}")
    logger.info("Downloading arduino-cli {}", url)

    target_dir = arduino_cli_dir()
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / name
        with urllib.request.urlopen(url, timeout=120) as resp, archive.open("wb") as out:
            shutil.copyfileobj(resp, out)
        if progress:
            progress("Extracting archive")
        _extract_archive(archive, target_dir, ext)

    if not exe.is_file():
        for candidate in target_dir.rglob("arduino-cli*"):
            if candidate.is_file() and not candidate.name.endswith((".md", ".txt")):
                shutil.move(str(candidate), str(exe))
                break

    if not exe.is_file():
        raise RuntimeError(f"arduino-cli installed but executable not found at {exe}")

    if not sys.platform.startswith("win"):
        try:
            os.chmod(exe, 0o755)
        except OSError:
            pass

    if progress:
        progress(f"arduino-cli ready at {exe}")
    logger.info("arduino-cli installed at {}", exe)
    return exe


def find_arduino_cli() -> Path | None:
    env = os.environ.get("ARDUINO_CLI")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    exe = arduino_cli_executable()
    if exe.is_file():
        return exe
    found = shutil.which("arduino-cli")
    if found:
        return Path(found)
    candidates = [
        Path("/opt/homebrew/bin/arduino-cli"),
        Path("/usr/local/bin/arduino-cli"),
        Path("/usr/bin/arduino-cli"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def ensure_arduino_cli(progress: ProgressCallback | None = None) -> Path:
    found = find_arduino_cli()
    if found:
        return found
    return install_arduino_cli(progress=progress)


def _tooling_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CI": env.get("CI", "1"),
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "TERM": "dumb",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if extra:
        env.update(extra)
    return env


def _strip_ansi(s: str) -> str:
    out: list[str] = []
    i = 0
    b = s
    n = len(b)
    while i < n:
        ch = b[i]
        if ch == "\x1b" and i + 1 < n:
            nxt = b[i + 1]
            if nxt == "[":
                i += 2
                while i < n:
                    c = b[i]
                    i += 1
                    if 0x40 <= ord(c) <= 0x7E:
                        break
                continue
            if nxt == "]":
                i += 2
                while i < n:
                    if b[i] == "\x07":
                        i += 1
                        break
                    if b[i] == "\x1b" and i + 1 < n and b[i + 1] == "\\":
                        i += 2
                        break
                    i += 1
                continue
            if 0x40 <= ord(nxt) <= 0x5F:
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def run_cli(
    cli: Path,
    args: list[str],
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
    timeout: int | None = 600,
) -> tuple[int, str]:
    full = [str(cli), "--no-color", *args]
    logger.debug("arduino-cli {}", " ".join(args))
    proc = subprocess.run(
        full,
        cwd=str(cwd) if cwd else None,
        env=_tooling_env(env_extra),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, _strip_ansi(out)


def ensure_ch55x_core(cli: Path, progress: ProgressCallback | None = None) -> str:
    code, out = run_cli(cli, ["core", "list", "--additional-urls", BOARD_INDEX])
    log = out
    if code == 0 and "CH55xDuino" in out:
        return log
    if progress:
        progress("Updating arduino board index")
    code, out = run_cli(cli, ["core", "update-index", "--additional-urls", BOARD_INDEX])
    log += out
    if code != 0:
        raise RuntimeError(f"arduino-cli core update-index failed:\n{log}")
    if progress:
        progress("Installing CH55xDuino core")
    code, out = run_cli(
        cli, ["core", "install", "CH55xDuino:mcs51", "--additional-urls", BOARD_INDEX]
    )
    log += out
    if code != 0:
        raise RuntimeError(f"arduino-cli core install failed:\n{log}")
    return log
