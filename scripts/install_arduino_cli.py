from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.hardware.macropad_2k.arduino_cli import (  # noqa: E402
    DEFAULT_VERSION,
    ensure_arduino_cli,
    ensure_ch55x_core,
)


def _log(message: str) -> None:
    print(f"[arduino-cli] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install arduino-cli + CH55xDuino core")
    parser.add_argument("--skip-core", action="store_true", help="Do not install CH55xDuino core")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="arduino-cli version to install")
    args = parser.parse_args()

    try:
        cli = ensure_arduino_cli(progress=_log)
    except Exception as exc:
        print(f"[arduino-cli] install failed: {exc}", file=sys.stderr)
        return 1
    _log(f"binary ready at {cli}")

    if args.skip_core:
        return 0

    try:
        ensure_ch55x_core(cli, progress=_log)
    except Exception as exc:
        print(f"[arduino-cli] core install failed: {exc}", file=sys.stderr)
        return 2
    _log("CH55xDuino core installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
