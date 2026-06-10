from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from jarvis.hardware.macropad_2k.arduino_cli import find_arduino_cli, install_arduino_cli
from jarvis.hardware.macropad_2k.flasher import compile_firmware, upload_firmware
from jarvis.hardware.macropad_2k.launcher import (
    create_app_launcher,
    is_windows,
    list_installed_apps,
    open_device_manager,
)
from jarvis.hardware.macropad_2k.models import (
    KeypadUsbStatus,
    WorkspaceProfileBundle,
    get_active_profile,
)
from jarvis.hardware.macropad_2k.paths import (
    arduino_cli_executable,
    firmware_root,
    is_valid_workspace,
)
from jarvis.hardware.macropad_2k.profile_store import (
    load_bundle,
    load_default_workspace,
    migrate_to_bundle,
    persist_bundle,
    save_default_workspace,
)
from jarvis.hardware.macropad_2k.usb import usb_status

router = APIRouter(prefix="/api/macropad", tags=["macropad"])
_ui_router = APIRouter()


@_ui_router.get("/macropad", include_in_schema=False)
async def keypad_ui() -> FileResponse:
    return FileResponse("src/jarvis/interfaces/ui/static/macropad_2k.html")


class WorkspaceBody(BaseModel):
    path: str


class ProfileBundleBody(BaseModel):
    bundle: dict[str, Any]
    workspace: str


class CompileBody(BaseModel):
    workspace: str
    blinkHz: float | None = None


class UploadBody(BaseModel):
    workspace: str
    preferPython: bool = False
    attempts: int = 1


class LauncherBody(BaseModel):
    appId: str
    appName: str
    slot: str


def _resolve_workspace(raw: str | None) -> Path:
    if not raw:
        ws = load_default_workspace()
        if ws is None:
            ws = firmware_root()
    else:
        ws = Path(raw).expanduser().resolve()
    if not is_valid_workspace(ws):
        raise HTTPException(
            status_code=400,
            detail=f"workspace invalide (CH552_HID_Keyboard manquant): {ws}",
        )
    return ws


@router.get("/status", response_model=KeypadUsbStatus)
async def get_status() -> KeypadUsbStatus:
    data = await asyncio.to_thread(usb_status)
    return KeypadUsbStatus(**data)


@router.get("/workspace")
async def get_workspace() -> dict[str, Any]:
    ws = load_default_workspace()
    if ws is None:
        return {"workspace": None, "valid": False, "vendored": str(firmware_root())}
    return {
        "workspace": str(ws),
        "valid": is_valid_workspace(ws),
        "vendored": str(firmware_root()),
    }


@router.post("/workspace")
async def set_workspace(body: WorkspaceBody) -> dict[str, Any]:
    ws = Path(body.path).expanduser().resolve()
    if not is_valid_workspace(ws):
        raise HTTPException(
            status_code=400, detail="dossier invalide (CH552_HID_Keyboard manquant)"
        )
    save_default_workspace(ws)
    return {"workspace": str(ws), "valid": True}


@router.get("/workspace/validate")
async def validate_workspace(path: str) -> dict[str, Any]:
    ws = Path(path).expanduser().resolve()
    return {"valid": is_valid_workspace(ws), "workspace": str(ws)}


@router.get("/profile")
async def get_profile(workspace: str | None = None) -> dict[str, Any]:
    ws = _resolve_workspace(workspace)
    bundle = await asyncio.to_thread(load_bundle, ws)
    return {"workspace": str(ws), "bundle": bundle.model_dump(mode="json")}


@router.put("/profile")
async def put_profile(body: ProfileBundleBody) -> dict[str, Any]:
    ws = _resolve_workspace(body.workspace)
    try:
        bundle = migrate_to_bundle(body.bundle, str(ws))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"profil invalide: {exc}") from exc
    await asyncio.to_thread(persist_bundle, bundle, ws)
    return {"ok": True, "workspace": str(ws)}


@router.get("/arduino-cli")
async def get_arduino_cli_status() -> dict[str, Any]:
    found = find_arduino_cli()
    return {
        "installed": found is not None,
        "path": str(found) if found else None,
        "vendored": str(arduino_cli_executable()),
    }


@router.post("/arduino-cli/install")
async def post_install_arduino_cli() -> dict[str, Any]:
    try:
        path = await asyncio.to_thread(install_arduino_cli)
    except Exception as exc:
        logger.exception("install_arduino_cli failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "path": str(path)}


@router.post("/compile")
async def post_compile(body: CompileBody) -> dict[str, Any]:
    ws = _resolve_workspace(body.workspace)
    bundle: WorkspaceProfileBundle = await asyncio.to_thread(load_bundle, ws)
    profile = get_active_profile(bundle)
    try:
        result = await asyncio.to_thread(
            compile_firmware,
            ws,
            profile,
            body.blinkHz,
            None,
        )
    except Exception as exc:
        logger.exception("compile_firmware failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/upload")
async def post_upload(body: UploadBody) -> dict[str, Any]:
    ws = _resolve_workspace(body.workspace)
    try:
        result = await asyncio.to_thread(
            upload_firmware,
            ws,
            None,
            body.preferPython,
            max(1, body.attempts),
        )
    except Exception as exc:
        logger.exception("upload_firmware failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.get("/installed-apps")
async def get_installed_apps() -> dict[str, Any]:
    if not is_windows():
        return {"apps": [], "platform": "non-windows"}
    apps = await asyncio.to_thread(list_installed_apps)
    return {"apps": apps, "platform": "windows"}


@router.post("/launcher")
async def post_launcher(body: LauncherBody) -> dict[str, Any]:
    if not is_windows():
        raise HTTPException(status_code=400, detail="launcher disponible uniquement sous Windows")
    try:
        alias = await asyncio.to_thread(create_app_launcher, body.appId, body.appName, body.slot)
    except Exception as exc:
        logger.exception("create_app_launcher failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "alias": alias}


@router.post("/open-device-manager")
async def post_open_device_manager() -> dict[str, Any]:
    if not is_windows():
        raise HTTPException(
            status_code=400, detail="device manager disponible uniquement sous Windows"
        )
    ok = await asyncio.to_thread(open_device_manager)
    return {"ok": ok}
