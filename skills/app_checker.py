"""
Vérifie si les applications requises par un skill sont installées.
"""
from __future__ import annotations
import platform
import subprocess
from pathlib import Path
from loguru import logger


def check_app_installed(app: dict) -> dict:
    """
    Vérifie si une application est installée.
    app : entrée de requires_apps depuis skill.yaml
    Retourne : {name, installed, required, url, message}
    """
    system = platform.system().lower()
    name = app.get("name", "")
    required = app.get("required", False)
    url = app.get("url", "")

    installed = False

    if system == "darwin":
        mac_bundle = app.get("mac_bundle", "")
        if mac_bundle:
            for prefix in ["/Applications", str(Path.home() / "Applications")]:
                if Path(f"{prefix}/{mac_bundle}.app").exists():
                    installed = True
                    break
        if not installed and mac_bundle:
            try:
                result = subprocess.run(
                    ["mdfind", f"kMDItemFSName == '{mac_bundle}.app'"],
                    capture_output=True, text=True, timeout=3
                )
                installed = bool(result.stdout.strip())
            except Exception:
                pass

    elif system == "windows":
        windows_exe = app.get("windows_exe", "")
        if windows_exe:
            try:
                result = subprocess.run(
                    ["where", windows_exe],
                    capture_output=True, text=True, timeout=3
                )
                installed = result.returncode == 0
            except Exception:
                pass

    elif system == "linux":
        linux_cmd = app.get("linux_cmd", "")
        if linux_cmd:
            try:
                result = subprocess.run(
                    ["which", linux_cmd],
                    capture_output=True, text=True, timeout=3
                )
                installed = result.returncode == 0
            except Exception:
                pass

    message = ""
    if not installed and required:
        message = f"Requis — télécharger sur {url}"
    elif not installed and not required:
        message = f"Optionnel — {url}"

    return {
        "name": name,
        "installed": installed,
        "required": required,
        "url": url,
        "message": message,
    }


def check_all_apps(requires_apps: list[dict]) -> dict:
    """
    Vérifie toutes les apps requises.
    Retourne {all_required_installed, apps: [...]}
    """
    results = [check_app_installed(app) for app in requires_apps]

    all_required_installed = all(
        r["installed"] or not r["required"]
        for r in results
    )

    return {
        "all_required_installed": all_required_installed,
        "apps": results,
    }
