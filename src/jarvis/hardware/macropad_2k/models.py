from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModifierId = Literal["ctrl", "shift", "alt", "gui"]
LightingEffect = Literal["static", "breath", "rainbow", "reactive", "wave", "theater", "sparkle"]
LightingTrigger = Literal["press", "release", "both", "hold"]
KeyMode = Literal["hold", "macro"]


class KeyChord(BaseModel):
    modifiers: list[ModifierId] = Field(default_factory=list)
    hidCode: str = "KeyA"
    label: str = "A"
    mode: KeyMode = "hold"
    macroText: str = ""
    macroDelayMs: int = 180
    macroTapEnter: bool = True


class DeviceSettings(BaseModel):
    keypadProductId: str = "macropad_2k_le_labo"
    productName: str = "Macropad 2 touches Le Labo"


class KeysOptions(BaseModel):
    debounceMs: int = 5
    layoutFrAzerty: bool = True
    softwareRapidTrigger: bool = False
    rapidTriggerResetMs: int = 2


class HardwareSettings(BaseModel):
    keyLedsGpio: str = "P3.4"
    keyLedOrder: list[int] = Field(default_factory=lambda: [1, 2])
    edgeLedsGpio: str = "P3.0"
    edgeLedCount: int = 25
    pcbNote: str = "Visual left is P2 (K2), visual right is P1 (K1)"


class LightingSettings(BaseModel):
    effect: LightingEffect = "static"
    keyBrightness: float = 0.75
    edgeBrightness: float = 0.75
    keySpeed: float = 0.6
    edgeSpeed: float = 0.6
    trigger: LightingTrigger = "press"
    staticKeyColor: str = "#30ad6c"
    staticEdgeColor: str = "#30ad6c"
    keyPixels: list[str] = Field(default_factory=lambda: ["#00f0ff", "#ff2d95"])
    edgePixels: list[str] = Field(default_factory=lambda: ["#8b5cf6"] * 25)


class KeypadKeys(BaseModel):
    k1RightP1: KeyChord = Field(default_factory=lambda: KeyChord(hidCode="KeyA", label="A"))
    k2LeftP2: KeyChord = Field(default_factory=lambda: KeyChord(hidCode="KeyB", label="B"))


class KeypadProfile(BaseModel):
    version: int = 1
    workspaceRoot: str = ""
    device: DeviceSettings = Field(default_factory=DeviceSettings)
    keysOptions: KeysOptions = Field(default_factory=KeysOptions)
    keys: KeypadKeys = Field(default_factory=KeypadKeys)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    lighting: LightingSettings = Field(default_factory=LightingSettings)


class ProfileSlot(BaseModel):
    id: str
    name: str
    data: KeypadProfile


class WorkspaceProfileBundle(BaseModel):
    bundleVersion: int = 2
    activeProfileId: str = "default"
    profiles: list[ProfileSlot] = Field(default_factory=list)


class KeypadUsbStatus(BaseModel):
    hidPresent: bool = False
    bootloaderPresent: bool = False


class InstalledApp(BaseModel):
    name: str
    appId: str


class CompileResult(BaseModel):
    ok: bool
    output: str
    binPath: str | None = None
    hexPath: str | None = None


class UploadResult(BaseModel):
    ok: bool
    output: str


def default_profile(workspace: str = "") -> KeypadProfile:
    return KeypadProfile(workspaceRoot=workspace)


def default_bundle(workspace: str = "") -> WorkspaceProfileBundle:
    return WorkspaceProfileBundle(
        bundleVersion=2,
        activeProfileId="default",
        profiles=[ProfileSlot(id="default", name="Principal", data=default_profile(workspace))],
    )


def get_active_profile(bundle: WorkspaceProfileBundle) -> KeypadProfile:
    for slot in bundle.profiles:
        if slot.id == bundle.activeProfileId:
            return slot.data
    if bundle.profiles:
        return bundle.profiles[0].data
    return default_profile()
