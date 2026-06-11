from __future__ import annotations

import json
import secrets
from pathlib import Path

from loguru import logger

from jarvis.hardware.macropad_2k.firmware_gen import generate_from_bundle
from jarvis.hardware.macropad_2k.models import (
    KeypadProfile,
    ProfileSlot,
    WorkspaceProfileBundle,
    default_bundle,
    default_profile,
)
from jarvis.hardware.macropad_2k.paths import (
    firmware_root,
    is_valid_workspace,
    profile_path,
    workspace_state_path,
)


def _new_slot_id() -> str:
    return f"p_{secrets.token_hex(4)}"


def merge_profile(raw: object, workspace: str) -> KeypadProfile:
    base = default_profile(workspace)
    if not isinstance(raw, dict):
        return base
    try:
        merged = base.model_dump()
        for k, v in raw.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        merged["workspaceRoot"] = workspace
        return KeypadProfile.model_validate(merged)
    except Exception as exc:
        logger.warning("merge_profile: validation failed, using defaults. error={}", exc)
        return base


def migrate_to_bundle(raw: object, workspace: str) -> WorkspaceProfileBundle:
    if isinstance(raw, dict) and raw.get("bundleVersion") == 2:
        raw_profiles = raw.get("profiles") or []
        slots: list[ProfileSlot] = []
        for s in raw_profiles:
            if not isinstance(s, dict):
                logger.warning(
                    "migrate_to_bundle: slot invalide ignoré (type={})", type(s).__name__
                )
                continue
            sid = s.get("id") or _new_slot_id()
            sname = s.get("name") or "Profil"
            data = merge_profile(s.get("data") or {}, workspace)
            slots.append(ProfileSlot(id=sid, name=sname, data=data))
        if not slots:
            return default_bundle(workspace)
        ids = {s.id for s in slots}
        active = raw.get("activeProfileId")
        if not isinstance(active, str) or active not in ids:
            active = slots[0].id
        return WorkspaceProfileBundle(bundleVersion=2, activeProfileId=active, profiles=slots)
    return WorkspaceProfileBundle(
        bundleVersion=2,
        activeProfileId="default",
        profiles=[ProfileSlot(id="default", name="Principal", data=merge_profile(raw, workspace))],
    )


def load_bundle(workspace: Path) -> WorkspaceProfileBundle:
    p = profile_path(workspace)
    if not p.is_file():
        return default_bundle(str(workspace))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_bundle(str(workspace))
    return migrate_to_bundle(data, str(workspace))


def save_bundle(bundle: WorkspaceProfileBundle, workspace: Path) -> None:
    if not is_valid_workspace(workspace):
        raise FileNotFoundError("invalid workspace: CH552_HID_Keyboard missing")
    normalized = bundle.model_copy(deep=True)
    for slot in normalized.profiles:
        slot.data.workspaceRoot = str(workspace)
    payload = normalized.model_dump(mode="json")
    p = profile_path(workspace)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def persist_bundle(bundle: WorkspaceProfileBundle, workspace: Path) -> None:
    save_bundle(bundle, workspace)
    generate_from_bundle(bundle, workspace)


def load_default_workspace() -> Path | None:
    state_file = workspace_state_path()
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        path = data.get("workspace") if isinstance(data, dict) else None
        if isinstance(path, str) and is_valid_workspace(path):
            return Path(path)

    fw = firmware_root()
    if is_valid_workspace(fw):
        return fw
    return None


def save_default_workspace(workspace: Path) -> None:
    state_file = workspace_state_path()
    payload = {"workspace": str(Path(workspace).resolve())}
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
