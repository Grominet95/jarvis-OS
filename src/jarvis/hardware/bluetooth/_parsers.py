"""Parsers Bluetooth — sortie texte des outils système → list[dict] UI-shaped.

Extrait de `interfaces/api/config/devices.py` en Phase F §F.1.5. Aucune
dépendance FastAPI.
"""

from __future__ import annotations

import json as _json
import re
import subprocess

_BT_ID_MAP = {
    "headphones": "audio · BT",
    "headset": "audio · BT",
    "mouse": "mouse · BT",
    "keyboard": "keyboard · BT",
    "gamepad": "gamepad · BT",
    "joystick": "gamepad · BT",
}


def parse_bt_macos(out: str, devices: list) -> None:
    """Parse la sortie de `system_profiler SPBluetoothDataType` (macOS).

    Pousse dans `devices` un dict UI-shaped par device détecté, en
    distinguant Connected vs Nearby (non connectés).
    """
    section: str | None = None
    cur: dict | None = None

    def _flush(d: dict | None) -> None:
        if not d:
            return
        name = d["_name"]
        if re.fullmatch(r"[0-9A-Fa-f:]+", name):
            return
        bt_type = d["_type"] or "Device"
        connected = d["_connected"]
        devices.append(
            {
                "name": name,
                "id": _BT_ID_MAP.get(bt_type.lower(), "bluetooth · BT"),
                "status": "Connected" if connected else "Nearby",
                "col": "green" if connected else "muted",
                "a": ["Type", bt_type],
                "b": ["Vendor", d["_vendor"] or "—"],
                "type": "bluetooth",
            }
        )

    for line in out.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 6 and stripped.endswith(":"):
            _flush(cur)
            cur = None
            if "Not Connected" in stripped:
                section = "not_connected"
            elif "Connected" in stripped:
                section = "connected"
            else:
                section = None
            continue

        if section is None:
            continue

        if indent == 10 and stripped.endswith(":"):
            _flush(cur)
            cur = {
                "_name": stripped[:-1],
                "_connected": section == "connected",
                "_type": None,
                "_vendor": None,
            }
            continue

        if cur and indent >= 14 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if key == "Minor Type":
                cur["_type"] = val
            elif key == "Vendor ID" and "004C" in val:
                cur["_vendor"] = "Apple"

    _flush(cur)


def parse_bt_windows(devices: list) -> None:
    """Parse la sortie de `Get-PnpDevice -Class Bluetooth -PresentOnly` (Windows).

    Pousse dans `devices` un dict UI-shaped par device détecté. Filtre les
    drivers internes (énumérateur Microsoft, Realtek/Broadcom adapters, etc.).
    """
    skip = re.compile(
        r"(?i)enumerator|microsoft\s+bluetooth|^\s*intel\(r\)\s+wireless\s+bluetooth|"
        r"realtek\s+bluetooth|broadcom\s+bluetooth|virtual|rfcomm|"
        r"generic\s+attribute|device\s+association|le\s+audio|"
        r"^bluetooth\s+device\s*\("
    )
    ps = (
        "Get-PnpDevice -Class 'Bluetooth' -PresentOnly | "
        "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps],
        text=True,
        timeout=12,
    )
    items = _json.loads(out)
    if isinstance(items, dict):
        items = [items]
    seen: set[str] = set()
    for item in items:
        name = (item.get("FriendlyName") or "").strip() or "Unknown"
        if skip.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        status = (item.get("Status") or "Unknown").strip()
        ok = status == "OK"
        nl = name.lower()
        if "mouse" in nl:
            bt_id = _BT_ID_MAP["mouse"]
        elif "keyboard" in nl:
            bt_id = _BT_ID_MAP["keyboard"]
        elif "headphone" in nl or "headset" in nl or "airpods" in nl or "buds" in nl:
            bt_id = _BT_ID_MAP["headphones"]
        elif "gamepad" in nl or "controller" in nl or "xbox" in nl or "dualshock" in nl:
            bt_id = _BT_ID_MAP["gamepad"]
        else:
            bt_id = "bluetooth · BT"
        devices.append(
            {
                "name": name,
                "id": bt_id,
                "status": "Connected" if ok else "Nearby",
                "col": "green" if ok else "muted",
                "a": ["Type", "Bluetooth"],
                "b": ["État", status],
                "type": "bluetooth",
            }
        )
