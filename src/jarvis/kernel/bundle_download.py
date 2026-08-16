# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from jarvis.kernel.bundle import (
    BUNDLE_DIR,
    PROJECT_ROOT,
    bundle_available,
    prerequisites_status,
    stage_models_from_bundle,
)
from jarvis.kernel.error_collector import collector  # jrv: autofix

BUNDLE_RELEASE_VERSION = "v0.3.2"
BUNDLE_CDN_ROOT = f"https://techalchemy.fr/jarvis-bundle-windows-{BUNDLE_RELEASE_VERSION}"
BUNDLE_ZIP_URL = f"{BUNDLE_CDN_ROOT}/bundle.zip"
BUNDLE_ZIP_BYTES = 657_929_168
# Empreinte SHA-256 de bundle.zip. Vide = non verifiee, seule la taille l'est —
# or une taille identique ne prouve rien sur le contenu, et l'archive contient un
# venv Python et des binaires qui seront EXECUTES. Publier bundle.zip.sha256 a
# cote de l'archive et coller la valeur ici suffit a activer la verification.
BUNDLE_ZIP_SHA256 = ""

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "percent": 0,
    "message": "",
    "error": None,
    "bytes_downloaded": 0,
    "bytes_total": BUNDLE_ZIP_BYTES,
    "speed_mb_s": None,
    "eta_seconds": None,
}


def bundle_download_info() -> dict[str, Any]:
    return {
        "available": bundle_available(),
        "downloadable": sys.platform == "win32" and not bundle_available(),
        "release_version": BUNDLE_RELEASE_VERSION,
        "release_url": BUNDLE_CDN_ROOT,
        "zip_url": BUNDLE_ZIP_URL,
        "zip_bytes": BUNDLE_ZIP_BYTES,
        "platform": sys.platform,
    }


def get_download_status() -> dict[str, Any]:
    with _lock:
        status = dict(_state)
        if status["phase"] == "done" and bundle_available():
            _state.update(
                phase="idle",
                running=False,
                percent=0,
                message="",
                bytes_downloaded=0,
                speed_mb_s=None,
                eta_seconds=None,
            )
    status["bundle"] = bundle_available()
    status["prerequisites"] = prerequisites_status()
    return status


def _set_state(**kwargs: object) -> None:
    with _lock:
        _state.update(kwargs)


def start_bundle_download() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"started": False, "reason": "windows_only"}
    if bundle_available():
        return {"started": False, "reason": "already_present"}
    with _lock:
        if _state["running"]:
            return {"started": False, "reason": "already_running"}
        _state.update(
            running=True,
            phase="download",
            percent=0,
            message="Connecting…",
            error=None,
            bytes_downloaded=0,
            bytes_total=BUNDLE_ZIP_BYTES,
            speed_mb_s=None,
            eta_seconds=None,
        )
    threading.Thread(target=_run_download, name="bundle-download", daemon=True).start()
    return {"started": True}


def _zip_member_dest(name: str) -> str | None:
    """Chemin relatif sûr d'un membre d'archive, ou None si le membre est à ignorer.

    Rejette tout ce qui sortirait de BUNDLE_DIR. Sans ce filtre, un membre nommé
    `bundle/../../evil` ou `/etc/cron.d/evil` s'écrirait hors du dossier bundle :
    `BUNDLE_DIR / rel` avec un `rel` absolu renvoie `rel` tel quel (sémantique
    pathlib), et un `..` remonte l'arborescence. `zipfile.extractall()` assainit
    de lui-même, mais on écrit membre par membre pour suivre la progression —
    donc l'assainissement est à notre charge.
    """
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        return None
    if normalized.startswith("bundle/"):
        normalized = normalized[len("bundle/") :]
    if not normalized:
        return None

    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    # Lettre de lecteur Windows ("C:/…", "C:evil") : absolue une fois sur cible.
    first = candidate.parts[0] if candidate.parts else ""
    if len(first) >= 2 and first[1] == ":":
        return None
    return normalized


def _safe_dest(rel: str) -> Path:
    """Résout `rel` sous BUNDLE_DIR en refusant toute évasion résiduelle (liens…)."""
    root = BUNDLE_DIR.resolve()
    dest = (root / rel).resolve()
    if dest != root and root not in dest.parents:
        raise RuntimeError(f"Archive member escapes bundle directory: {rel!r}")
    return dest


def _extract_zip_to_bundle(zf: zipfile.ZipFile, phase_started: float) -> None:
    members = [m for m in zf.infolist() if _zip_member_dest(m.filename)]
    total = len(members)
    if total == 0:
        raise RuntimeError("Invalid archive: no files to extract")

    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    for index, member in enumerate(members, start=1):
        rel = _zip_member_dest(member.filename)
        if not rel:
            continue
        dest = _safe_dest(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)

        elapsed = max(time.monotonic() - phase_started, 0.001)
        eta = int((total - index) / (index / elapsed)) if index > 0 else None
        pct = 70 + int(index * 22 / total)
        _set_state(
            phase="extract",
            percent=min(92, pct),
            message=f"Extraction {index}/{total}",
            eta_seconds=eta,
            speed_mb_s=None,
        )

    if not (BUNDLE_DIR / "manifest.json").is_file():
        raise RuntimeError("Invalid archive: manifest.json missing after extraction")


def _verify_archive(zip_path: Path) -> None:
    """Contrôle l'archive avant extraction : taille, puis empreinte si publiée."""
    size = zip_path.stat().st_size
    if size != BUNDLE_ZIP_BYTES:
        raise RuntimeError(
            f"Invalid bundle.zip size: expected {BUNDLE_ZIP_BYTES}, got {size}. "
            "Téléchargement incomplet, ou archive du CDN désynchronisée de "
            f"BUNDLE_RELEASE_VERSION ({BUNDLE_RELEASE_VERSION})."
        )
    if not BUNDLE_ZIP_SHA256:
        return
    digest = hashlib.sha256()
    with zip_path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != BUNDLE_ZIP_SHA256.lower():
        raise RuntimeError(
            f"bundle.zip SHA-256 mismatch: expected {BUNDLE_ZIP_SHA256.lower()}, got {actual}"
        )


def _rehome_bundle_windows() -> None:
    script = PROJECT_ROOT / "scripts" / "release" / "rehome_bundle.ps1"
    if not script.is_file():
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProjectRoot",
            str(PROJECT_ROOT),
        ],
        check=False,
        cwd=str(PROJECT_ROOT),
    )


def _run_download() -> None:
    staging = Path(tempfile.mkdtemp(prefix="jarvis-bundle-"))
    zip_path = staging / "bundle.zip"
    try:
        phase_started = time.monotonic()
        _set_state(phase="download", percent=0, message="Connecting…")
        with httpx.stream("GET", BUNDLE_ZIP_URL, follow_redirects=True, timeout=900.0) as resp:
            resp.raise_for_status()
            header_total = int(resp.headers.get("content-length", "0") or 0)
            total = header_total or BUNDLE_ZIP_BYTES
            _set_state(bytes_total=total)
            downloaded = 0
            with zip_path.open("wb") as out:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    out.write(chunk)
                    downloaded += len(chunk)
                    elapsed = max(time.monotonic() - phase_started, 0.001)
                    speed_mb_s = (downloaded / elapsed) / (1024 * 1024)
                    eta_seconds = None
                    if speed_mb_s > 0 and total > downloaded:
                        eta_seconds = int((total - downloaded) / (speed_mb_s * 1024 * 1024))
                    pct = min(68, int(downloaded * 68 / total))
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    _set_state(
                        bytes_downloaded=downloaded,
                        percent=pct,
                        speed_mb_s=round(speed_mb_s, 2),
                        eta_seconds=eta_seconds,
                        message=f"{mb_done:.0f} / {mb_total:.0f} Mo",
                    )

        _verify_archive(zip_path)

        extract_started = time.monotonic()
        _set_state(
            phase="extract",
            percent=70,
            message="Starting extraction…",
            speed_mb_s=None,
            eta_seconds=None,
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            _extract_zip_to_bundle(zf, extract_started)

        _set_state(
            phase="rehome",
            percent=93,
            message="Python venv configuration…",
            speed_mb_s=None,
            eta_seconds=8,
        )
        _rehome_bundle_windows()

        _set_state(
            phase="stage",
            percent=97,
            message="Copying ML models…",
            speed_mb_s=None,
            eta_seconds=5,
        )
        stage_models_from_bundle()

        _set_state(
            running=False,
            phase="done",
            percent=100,
            message="Bundle installed",
            error=None,
            speed_mb_s=None,
            eta_seconds=0,
        )
    except Exception as exc:
        collector.error("JRV-KRN-002", "JRV-KRN-002", cause=exc)
        _set_state(
            running=False,
            phase="error",
            message="Download failed",
            error=str(exc),
            speed_mb_s=None,
            eta_seconds=None,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        with _lock:
            if _state["phase"] not in ("error", "done"):
                _state["running"] = False
