from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

from jarvis.hardware.macropad_2k.paths import launchers_dir


def is_windows() -> bool:
    return sys.platform.startswith("win")


def list_installed_apps() -> list[dict[str, str]]:
    if not is_windows():
        return []
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        " [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false);"
        " Get-StartApps | Where-Object { $_.Name -and $_.AppID } | "
        " Sort-Object Name | Select-Object Name,AppID | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("list_installed_apps powershell failed: {}", exc)
        return []
    if proc.returncode != 0:
        logger.warning("Get-StartApps returned {}: {}", proc.returncode, proc.stderr)
        return []
    raw = (proc.stdout or "").strip()
    if not raw or raw == "null":
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]

    seen: set[str] = set()
    apps: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        app_id = str(item.get("AppID") or "").strip()
        if not name or not app_id:
            continue
        key = f"{name.lower()}|{app_id.lower()}"
        if key in seen:
            continue
        seen.add(key)
        apps.append({"name": name, "appId": app_id})
    return apps


def _stable_alias_seed(app_id: str, app_name: str) -> int:
    h = 5381
    payload = app_id.encode("utf-8") + b"|" + app_name.encode("utf-8")
    for b in payload:
        h = ((h << 5) + h + b) & 0xFFFFFFFF
    return h


def _alias_from_seed(seed: int) -> str:
    alpha = "bcdefghjklmnprstuvxy"
    n = seed
    out = "kp"
    for _ in range(4):
        idx = n % len(alpha)
        out += alpha[idx]
        n //= len(alpha)
    return out


def _launcher_cmd_body(app_id: str, app_name: str) -> str:
    app_id_t = (app_id or "").strip().replace('"', "")
    app_name_t = (app_name or "").strip().replace('"', "")
    if app_id_t:
        return f'@echo off\r\nstart "" explorer.exe "shell:AppsFolder\\{app_id_t}"\r\n'
    return f'@echo off\r\nstart "" "{app_name_t}"\r\n'


def _ensure_user_path_contains(directory: Path) -> None:
    if not is_windows():
        return
    dir_s = str(directory).replace("'", "''")
    script = (
        f"$target='{dir_s}';"
        " $cur=[Environment]::GetEnvironmentVariable('Path','User');"
        " if([string]::IsNullOrWhiteSpace($cur))"
        "{[Environment]::SetEnvironmentVariable('Path',$target,'User');exit 0};"
        " $parts=$cur -split ';'"
        " | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' };"
        " $exists=$false;"
        " foreach($p in $parts)"
        "{if($p.TrimEnd('\\') -ieq $target.TrimEnd('\\')){$exists=$true;break}};"
        " if(-not $exists){$new=($cur.TrimEnd(';') + ';' + $target);"
        " [Environment]::SetEnvironmentVariable('Path',$new,'User')}"
    )
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Failed to update user PATH for launchers: {}", exc)


def create_app_launcher(app_id: str, app_name: str, slot: str) -> str:
    if not is_windows():
        raise RuntimeError("create_app_launcher: Windows only")
    target = launchers_dir()
    _ensure_user_path_contains(target)

    if slot == "k1":
        alias = "kpa"
    elif slot == "k2":
        alias = "kpb"
    else:
        seed = _stable_alias_seed(app_id, app_name)
        alias = _alias_from_seed(seed)

    body = _launcher_cmd_body(app_id, app_name)
    path = target / f"{alias}.cmd"
    path.write_text(body, encoding="utf-8")
    return alias


def open_device_manager() -> bool:
    if not is_windows():
        return False
    try:
        os.startfile("devmgmt.msc")
        return True
    except OSError:
        return False
