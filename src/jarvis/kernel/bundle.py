# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.paths import PROJECT_ROOT

BUNDLE_DIR = PROJECT_ROOT / "bundle"
MANIFEST_PATH = BUNDLE_DIR / "manifest.json"
YOLO_PROJECT = PROJECT_ROOT / "yolov8n.pt"
PIPER_PROJECT = PROJECT_ROOT / "models" / "piper" / "fr_FR-upmc-medium.onnx"


def _venv_python() -> Path:
    if sys.platform == "win32":
        return BUNDLE_DIR / ".venv" / "Scripts" / "python.exe"
    return BUNDLE_DIR / ".venv" / "bin" / "python"


def _monorepo_python() -> Path:
    if sys.platform == "win32":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"


def _rel_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        collector.error("JRV-KRN-002", "JRV-KRN-002")
        return str(path)


def _python_version(exe: Path) -> str | None:
    if not exe.is_file():
        return None
    try:
        proc = subprocess.run(
            [
                str(exe),
                "-c",
                "import sys; print("
                "f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            version = (proc.stdout or "").strip()
            return version or None
    except (OSError, subprocess.TimeoutExpired):
        collector.error("JRV-KRN-002", "JRV-KRN-002")
        pass
    return None


def _detect_system_python() -> dict[str, Any]:
    candidates: list[Path] = []
    if sys.platform == "win32":
        for name in ("python", "python3"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        try:
            proc = subprocess.run(
                ["py", "-3", "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0:
                raw = (proc.stdout or "").strip()
                if raw:
                    candidates.append(Path(raw))
        except OSError:
            collector.error("JRV-KRN-002", "JRV-KRN-002")
            pass
    else:
        for name in ("python3", "python"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    seen: set[str] = set()
    installs: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except OSError:
            collector.error("JRV-KRN-002", "JRV-KRN-002")
            resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _python_version(candidate)
        if version:
            installs.append({"path": resolved, "version": version})

    if not installs:
        return {"installed": False, "path": None, "version": None}
    primary = installs[0]
    return {
        "installed": True,
        "path": primary["path"],
        "version": primary["version"],
        "installs": installs,
    }


def _python_runtime_info(exe: Path, source: str) -> dict[str, Any]:
    present = exe.is_file()
    return {
        "source": source,
        "present": present,
        "path": str(exe) if present else None,
        "version": _python_version(exe) if present else None,
    }


def inspect_bundle() -> dict[str, Any]:
    missing: list[str] = []
    optional_missing: list[str] = []
    manifest: dict[str, Any] = {}
    present = BUNDLE_DIR.is_dir()

    if not present:
        return {
            "present": False,
            "valid": False,
            "missing": ["bundle/"],
            "optional_missing": [],
            "version": None,
            "platform": None,
        }

    if not MANIFEST_PATH.is_file():
        missing.append("manifest.json")
    else:
        try:
            manifest = load_manifest()
        except json.JSONDecodeError:
            collector.error("JRV-KRN-002", "JRV-KRN-002")
            missing.append("manifest.json (invalid JSON)")

    venv_py = _venv_python()
    if not venv_py.is_file():
        missing.append(_rel_project(venv_py))

    for key, rel in (manifest.get("models") or {}).items():
        if not rel:
            continue
        path = BUNDLE_DIR / rel
        if not path.is_file():
            optional_missing.append(f"models/{key}: {_rel_project(path)}")

    for key, rel in (manifest.get("bin") or {}).items():
        if not rel:
            continue
        path = BUNDLE_DIR / rel
        if not path.is_file():
            optional_missing.append(f"bin/{key}: {_rel_project(path)}")

    valid = not missing
    return {
        "present": True,
        "valid": valid,
        "missing": missing,
        "optional_missing": optional_missing,
        "version": manifest.get("version"),
        "platform": manifest.get("platform"),
    }


def bundle_available() -> bool:
    return inspect_bundle()["valid"]


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def resolve_python() -> Path:
    if bundle_available():
        return _venv_python()
    monorepo = _monorepo_python()
    if monorepo.is_file():
        return monorepo
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


def _bundle_model_path(manifest: dict[str, Any], key: str, default_rel: str) -> Path | None:
    rel = (manifest.get("models") or {}).get(key) or default_rel
    path = BUNDLE_DIR / rel
    return path if path.is_file() else None


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


def _asset_status(
    *,
    label: str,
    project_path: Path,
    bundle_path: Path | None,
) -> dict[str, Any]:
    in_project = project_path.is_file()
    in_bundle = bundle_path is not None
    ok = in_project or in_bundle
    if in_project:
        location = "project"
        detail = _rel_project(project_path)
    elif in_bundle and bundle_path is not None:
        location = "bundle"
        detail = _rel_project(bundle_path)
    else:
        location = None
        detail = None
    return {
        "label": label,
        "ok": ok,
        "location": location,
        "detail": detail,
        "project_path": str(project_path) if in_project else None,
        "bundle_path": str(bundle_path) if in_bundle and bundle_path is not None else None,
    }


def stage_models_from_bundle() -> list[str]:
    if not bundle_available():
        return []
    manifest = load_manifest()
    models = manifest.get("models", {})
    staged: list[str] = []

    yolo_rel = models.get("yolo")
    if yolo_rel:
        src = BUNDLE_DIR / yolo_rel
        dst = YOLO_PROJECT
        if src.is_file() and not dst.is_file():
            shutil.copy2(src, dst)
            staged.append(str(dst))

    piper_rel = models.get("piper_onnx")
    piper_json_rel = models.get("piper_json")
    if piper_rel:
        src = BUNDLE_DIR / piper_rel
        dst = PIPER_PROJECT
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
    inspection = inspect_bundle()
    manifest = load_manifest() if inspection["present"] else {}
    system_python = _detect_system_python()
    bundle_python = _python_runtime_info(_venv_python(), "bundle")
    monorepo_python = _python_runtime_info(_monorepo_python(), "monorepo")

    runtime_path: str | None = None
    runtime_source: str | None = None
    python_ok = False
    try:
        runtime = resolve_python()
        runtime_path = str(runtime)
        python_ok = True
        if bundle_python["present"] and runtime == _venv_python():
            runtime_source = "bundle"
        elif monorepo_python["present"] and runtime == _monorepo_python():
            runtime_source = "monorepo"
    except FileNotFoundError:
        # jrv: pas de code — sonde de prerequis, l'absence est un cas prevu
        pass

    yolo_bundle = _bundle_model_path(manifest, "yolo", "models/yolov8n.pt")
    piper_bundle = _bundle_model_path(manifest, "piper_onnx", "models/piper/fr_FR-upmc-medium.onnx")
    yolo_detail = _asset_status(label="yolo", project_path=YOLO_PROJECT, bundle_path=yolo_bundle)
    piper_detail = _asset_status(
        label="piper", project_path=PIPER_PROJECT, bundle_path=piper_bundle
    )

    livekit = resolve_livekit_binary()
    livekit_project = PROJECT_ROOT / "bin" / _platform_bin_name("livekit-server")
    livekit_in_project = livekit_project.is_file()
    livekit_in_bundle = livekit is not None and str(livekit).startswith(str(BUNDLE_DIR))
    if livekit:
        if livekit_in_project and livekit == livekit_project:
            livekit_location = "project"
        elif livekit_in_bundle:
            livekit_location = "bundle"
        else:
            livekit_location = "project"
        livekit_detail_text = _rel_project(livekit)
    else:
        livekit_location = None
        livekit_detail_text = None

    bundle_valid = inspection["valid"]
    yolo_ok = yolo_detail["ok"]
    piper_ok = piper_detail["ok"]
    livekit_ok = livekit is not None

    return {
        "bundle": bundle_valid,
        "bundle_inspection": inspection,
        "bundle_version": inspection.get("version") or manifest.get("version"),
        "can_continue": bundle_valid,
        "platform": platform.system().lower(),
        "python": python_ok,
        "python_path": runtime_path,
        "python_runtime_source": runtime_source,
        "python_detail": {
            "runtime_source": runtime_source,
            "runtime_path": runtime_path,
            "runtime_version": _python_version(Path(runtime_path)) if runtime_path else None,
            "system": system_python,
            "bundle": bundle_python,
            "monorepo": monorepo_python,
        },
        "yolo_model": yolo_ok,
        "yolo_detail": yolo_detail,
        "piper_model": piper_ok,
        "piper_detail": piper_detail,
        "livekit_binary": livekit_ok,
        "livekit_path": str(livekit) if livekit else None,
        "livekit_detail": {
            "ok": livekit_ok,
            "location": livekit_location,
            "detail": livekit_detail_text,
            "project_path": str(livekit_project) if livekit_in_project else None,
            "bundle_path": str(livekit) if livekit_in_bundle and livekit is not None else None,
        },
        "offline_ready": bundle_valid and python_ok and yolo_ok and piper_ok,
    }
