from __future__ import annotations

import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from jarvis.kernel.paths import PROJECT_ROOT

BUNDLE_DIR = PROJECT_ROOT / "bundle"
MANIFEST_PATH = BUNDLE_DIR / "manifest.json"


def _venv_python() -> Path:
    if sys.platform == "win32":
        return BUNDLE_DIR / ".venv" / "Scripts" / "python.exe"
    return BUNDLE_DIR / ".venv" / "bin" / "python"


def bundle_available() -> bool:
    return MANIFEST_PATH.is_file() and _venv_python().is_file()


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def resolve_python() -> Path:
    if bundle_available():
        return _venv_python()
    if sys.platform == "win32":
        candidates = (PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",)
    else:
        candidates = (PROJECT_ROOT / ".venv" / "bin" / "python",)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Python runtime introuvable. Utilise un bundle offline (scripts/release/build_bundle) "
        "ou lance uv sync depuis le depot."
    )


def resolve_uv() -> str:
    if sys.platform == "win32":
        bundled = BUNDLE_DIR / "bin" / "uv.exe"
    else:
        bundled = BUNDLE_DIR / "bin" / "uv"
    if bundled.is_file():
        return str(bundled)
    return "uv"


def _platform_bin_name(name: str) -> str:
    if sys.platform == "win32":
        return f"{name}.exe"
    return name


def resolve_livekit_binary() -> Path | None:
    manifest = load_manifest()
    rel = manifest.get("bin", {}).get("livekit")
    if rel:
        path = BUNDLE_DIR / rel
        if path.is_file():
            return path
    for candidate in (
        BUNDLE_DIR / "bin" / _platform_bin_name("livekit-server"),
        PROJECT_ROOT / "bin" / _platform_bin_name("livekit-server"),
    ):
        if candidate.is_file():
            return candidate
    return None


def stage_models_from_bundle() -> list[str]:
    if not bundle_available():
        return []
    manifest = load_manifest()
    models = manifest.get("models", {})
    staged: list[str] = []

    yolo_rel = models.get("yolo")
    if yolo_rel:
        src = BUNDLE_DIR / yolo_rel
        dst = PROJECT_ROOT / "yolov8n.pt"
        if src.is_file() and not dst.is_file():
            shutil.copy2(src, dst)
            staged.append(str(dst))

    piper_rel = models.get("piper_onnx")
    piper_json_rel = models.get("piper_json")
    if piper_rel:
        src = BUNDLE_DIR / piper_rel
        dst = PROJECT_ROOT / "models" / "piper" / "fr_FR-upmc-medium.onnx"
        if src.is_file() and not dst.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            staged.append(str(dst))
    if piper_json_rel:
        src = BUNDLE_DIR / piper_json_rel
        dst = PROJECT_ROOT / "models" / "piper" / "fr_FR-upmc-medium.onnx.json"
        if src.is_file() and not dst.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            staged.append(str(dst))

    return staged


def prerequisites_status() -> dict[str, Any]:
    manifest = load_manifest()
    yolo_ok = (PROJECT_ROOT / "yolov8n.pt").is_file()
    piper_ok = (PROJECT_ROOT / "models" / "piper" / "fr_FR-upmc-medium.onnx").is_file()
    livekit = resolve_livekit_binary()
    python_path: str | None = None
    python_ok = False
    try:
        python_path = str(resolve_python())
        python_ok = True
    except FileNotFoundError:
        pass

    return {
        "bundle": bundle_available(),
        "bundle_version": manifest.get("version"),
        "platform": platform.system().lower(),
        "python": python_ok,
        "python_path": python_path,
        "yolo_model": yolo_ok,
        "piper_model": piper_ok,
        "livekit_binary": livekit is not None,
        "livekit_path": str(livekit) if livekit else None,
        "offline_ready": bundle_available() and python_ok and yolo_ok and piper_ok,
    }
