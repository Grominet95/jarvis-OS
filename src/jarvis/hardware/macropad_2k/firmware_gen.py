from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from jarvis.hardware.macropad_2k.models import (
    KeyChord,
    KeypadProfile,
    WorkspaceProfileBundle,
    get_active_profile,
)
from jarvis.hardware.macropad_2k.paths import generated_dir, sketch_dir, usb_hid_dir

MANUFACTURER_USB = "Techalchemy SI"
USB_SERIAL_FIXED = "TCY-CH552-KB"

HID_CODE_TO_KEYBYTE: dict[str, str] = {
    **{f"Key{c}": f"'{c.lower()}'" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    **{f"Digit{n}": f"'{n}'" for n in "0123456789"},
    "Enter": "KEY_RETURN",
    "Escape": "KEY_ESC",
    "Backspace": "KEY_BACKSPACE",
    "Tab": "KEY_TAB",
    "Space": "' '",
    "Minus": "'-'",
    "Equal": "'='",
    "BracketLeft": "'['",
    "BracketRight": "']'",
    "Backslash": "'\\\\'",
    "Semicolon": "';'",
    "Quote": "'\\''",
    "Backquote": "'`'",
    "Comma": "','",
    "Period": "'.'",
    "Slash": "'/'",
    **{f"F{i}": f"KEY_F{i}" for i in range(1, 25)},
}

EFFECT_MAP: dict[str, int] = {
    "static": 0,
    "breath": 1,
    "rainbow": 2,
    "reactive": 3,
    "wave": 4,
    "theater": 5,
    "sparkle": 6,
}


def _sanitize_usb_string(s: str | None, default: str) -> str:
    raw = s if isinstance(s, str) and s else default
    decomposed = unicodedata.normalize("NFD", raw)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    printable = "".join(c for c in ascii_only if 0x20 <= ord(c) <= 0x7E).strip()
    if not printable:
        printable = default
    return printable[:31]


def _sanitize_ascii_text(s: str | None, max_len: int = 96) -> str:
    if not isinstance(s, str):
        return ""
    decomposed = unicodedata.normalize("NFD", s)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    printable = "".join(c for c in ascii_only if 0x20 <= ord(c) <= 0x7E)
    return printable[:max_len]


def _clamp_int(value: object, lo: int, hi: int, fallback: int) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, n))


def _clamp01(value: object, fallback: float = 1.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return fallback
    if n != n:
        return fallback
    return max(0.0, min(1.0, n))


def _hex_to_rgb(
    hex_value: object, fallback: tuple[int, int, int] = (128, 128, 128)
) -> tuple[int, int, int]:
    if not isinstance(hex_value, str):
        return fallback
    raw = hex_value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        return fallback
    try:
        n = int(raw, 16)
    except ValueError:
        return fallback
    return (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF


def _scale_rgb(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    f = max(0.0, min(1.0, factor))
    return tuple(max(0, min(255, round(v * f))) for v in rgb)  # type: ignore[return-value]


def _mods_mask(mods: list[str] | None) -> int:
    if not isinstance(mods, list):
        return 0
    m = 0
    if "ctrl" in mods:
        m |= 1
    if "shift" in mods:
        m |= 2
    if "alt" in mods:
        m |= 4
    if "gui" in mods:
        m |= 8
    return m


def _key_def_from_chord(chord: KeyChord, fallback: str) -> dict[str, Any]:
    mode = 1 if chord.mode == "macro" else 0
    hid_code = chord.hidCode if isinstance(chord.hidCode, str) else fallback
    key_expr = HID_CODE_TO_KEYBYTE.get(hid_code, HID_CODE_TO_KEYBYTE.get(fallback, "'a'"))
    return {
        "mode": mode,
        "mods": _mods_mask(chord.modifiers),
        "keyExpr": key_expr,
        "delayMs": _clamp_int(chord.macroDelayMs, 0, 1200, 180),
        "tapEnter": 0 if chord.macroTapEnter is False else 1,
        "macroText": _sanitize_ascii_text(chord.macroText, 96),
    }


def _c_string_literal(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _c_char(ch: str) -> str:
    if ch == "\\":
        return "'\\\\'"
    if ch == "'":
        return "'\\''"
    return f"'{ch}'"


def _make_string_descriptor(name: str, value: str) -> str:
    chars = list(value)
    n = len(chars)
    lines = [f"    ((({n} + 1) * 2) | (DTYPE_String << 8))"]
    for ch in chars:
        lines.append(f"    {_c_char(ch)}")
    body = ",\n".join(lines)
    return f"__code uint16_t {name}[] = {{\n{body}\n}};"


def _lighting_for_firmware(profile: KeypadProfile) -> dict[str, Any]:
    hw = profile.hardware
    lighting = profile.lighting
    edge_count = _clamp_int(hw.edgeLedCount, 1, 64, 25)
    effect = lighting.effect
    key_speed = _clamp01(lighting.keySpeed, 0.6)
    edge_speed = _clamp01(lighting.edgeSpeed, 0.6)
    key_brightness = _clamp01(lighting.keyBrightness, 0.75)
    edge_brightness = _clamp01(lighting.edgeBrightness, 0.75)
    key_fallback = lighting.staticKeyColor
    edge_fallback = lighting.staticEdgeColor
    key_pixels = lighting.keyPixels or []
    edge_pixels = lighting.edgePixels or []

    if effect == "static":
        key_colors = [_hex_to_rgb(key_fallback), _hex_to_rgb(key_fallback)]
        edge_colors = [_hex_to_rgb(edge_fallback) for _ in range(edge_count)]
    else:
        key_colors = [
            _hex_to_rgb(key_pixels[0] if len(key_pixels) > 0 else key_fallback),
            _hex_to_rgb(key_pixels[1] if len(key_pixels) > 1 else key_fallback),
        ]
        if edge_pixels:
            edge_colors = [
                _hex_to_rgb(
                    edge_pixels[i] if i < len(edge_pixels) else edge_pixels[i % len(edge_pixels)]
                )
                for i in range(edge_count)
            ]
        else:
            edge_colors = [_hex_to_rgb(edge_fallback) for _ in range(edge_count)]

    key_colors = [_scale_rgb(c, key_brightness) for c in key_colors]
    edge_colors = [_scale_rgb(c, edge_brightness) for c in edge_colors]

    return {
        "keyColors": key_colors,
        "edgeColors": edge_colors,
        "effect": effect,
        "keySpeed": key_speed,
        "edgeSpeed": edge_speed,
    }


def _resolve_profile_for_firmware(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("bundleVersion") == 2 and isinstance(raw.get("profiles"), list):
        active = raw.get("activeProfileId", "default")
        for slot in raw["profiles"]:
            if isinstance(slot, dict) and slot.get("id") == active:
                data = slot.get("data")
                if isinstance(data, dict):
                    return data
        first = raw["profiles"][0] if raw["profiles"] else None
        if isinstance(first, dict) and isinstance(first.get("data"), dict):
            return first["data"]
    return raw


def generate_from_bundle(bundle: WorkspaceProfileBundle, workspace: Path) -> None:
    profile = get_active_profile(bundle)
    generate(profile, workspace)


def generate_from_raw(raw_root: dict[str, Any], workspace: Path) -> None:
    profile_data = _resolve_profile_for_firmware(raw_root)
    profile = KeypadProfile.model_validate(profile_data)
    generate(profile, workspace)


def generate(profile: KeypadProfile, workspace: Path) -> None:
    sketch = sketch_dir(workspace)
    gen = generated_dir(workspace)
    usb_dir = usb_hid_dir(workspace)
    gen.mkdir(parents=True, exist_ok=True)
    usb_dir.mkdir(parents=True, exist_ok=True)

    product_name = _sanitize_usb_string(profile.device.productName, "Keypad CH552")
    manufacturer = _sanitize_usb_string(MANUFACTURER_USB, MANUFACTURER_USB)
    serial = _sanitize_usb_string(USB_SERIAL_FIXED, USB_SERIAL_FIXED)

    descriptors = "\n".join(
        [
            _make_string_descriptor("ProductDescriptor", product_name),
            "",
            _make_string_descriptor("ManufacturerDescriptor", manufacturer),
            "",
            _make_string_descriptor("SerialDescriptor", serial),
        ]
    )
    h_body = "\n".join(
        [
            "#ifndef USB_STRING_DESCRIPTORS_GEN_H",
            "#define USB_STRING_DESCRIPTORS_GEN_H",
            "",
            descriptors,
            "",
            "#endif",
            "",
        ]
    )
    (usb_dir / "usb_string_descriptors.h").write_text(h_body, encoding="utf-8")

    debounce_ms = _clamp_int(profile.keysOptions.debounceMs, 2, 50, 5)
    layout_fr = profile.keysOptions.layoutFrAzerty is not False
    sw_rapid = profile.keysOptions.softwareRapidTrigger is True
    rt_reset_ms = _clamp_int(profile.keysOptions.rapidTriggerResetMs, 1, 8, 2)
    rt_poll_ms = 2

    cfg_body = "\n".join(
        [
            "#ifndef KEYPAD_GEN_CONFIG_H",
            "#define KEYPAD_GEN_CONFIG_H",
            f"#define KEYPAD_DEBOUNCE_MS {debounce_ms}",
            f"#define KEYBOARD_LAYOUT_FR_AZERTY {1 if layout_fr else 0}",
            f"#define KEYPAD_SOFTWARE_RAPID_TRIGGER {1 if sw_rapid else 0}",
            f"#define KEYPAD_RT_POLL_MS {rt_poll_ms}",
            f"#define KEYPAD_RT_RESET_MS {rt_reset_ms}",
            "#define KEYPAD_FW_VARIANT 1",
            "#endif",
            "",
        ]
    )
    (gen / "keypad_config.h").write_text(cfg_body, encoding="utf-8")

    light = _lighting_for_firmware(profile)
    effect_id = EFFECT_MAP.get(light["effect"], 0)
    key_speed8 = max(0, min(255, round(light["keySpeed"] * 255)))
    edge_speed8 = max(0, min(255, round(light["edgeSpeed"] * 255)))
    key_flat = ", ".join(str(v) for c in light["keyColors"] for v in c)
    edge_flat = ", ".join(str(v) for c in light["edgeColors"] for v in c)
    led_header = "\n".join(
        [
            "#ifndef KEYPAD_LED_PROFILE_H",
            "#define KEYPAD_LED_PROFILE_H",
            f"#define KEYPAD_EFFECT_ID {effect_id}",
            f"#define KEYPAD_KEY_SPEED8 {key_speed8}",
            f"#define KEYPAD_EDGE_SPEED8 {edge_speed8}",
            f"#define KEYPAD_KEY_LED_COUNT {len(light['keyColors'])}",
            f"#define KEYPAD_EDGE_LED_COUNT {len(light['edgeColors'])}",
            "static const uint8_t KEYPAD_KEY_LED_RGB"
            f"[KEYPAD_KEY_LED_COUNT * 3] = {{ {key_flat} }};",
            "static const uint8_t KEYPAD_EDGE_LED_RGB"
            f"[KEYPAD_EDGE_LED_COUNT * 3] = {{ {edge_flat} }};",
            "#endif",
            "",
        ]
    )
    (gen / "keypad_led_profile.h").write_text(led_header, encoding="utf-8")

    k1 = _key_def_from_chord(profile.keys.k1RightP1, "KeyA")
    k2 = _key_def_from_chord(profile.keys.k2LeftP2, "KeyB")
    keys_header = "\n".join(
        [
            "#ifndef KEYPAD_KEYS_PROFILE_H",
            "#define KEYPAD_KEYS_PROFILE_H",
            f"#define KEYPAD_K1_MODE {k1['mode']}",
            f"#define KEYPAD_K1_MODS {k1['mods']}",
            f"#define KEYPAD_K1_KEY {k1['keyExpr']}",
            f"#define KEYPAD_K1_MACRO_DELAY_MS {k1['delayMs']}",
            f"#define KEYPAD_K1_MACRO_ENTER {k1['tapEnter']}",
            f"static const char KEYPAD_K1_MACRO_TEXT[] = {_c_string_literal(k1['macroText'])};",
            f"#define KEYPAD_K2_MODE {k2['mode']}",
            f"#define KEYPAD_K2_MODS {k2['mods']}",
            f"#define KEYPAD_K2_KEY {k2['keyExpr']}",
            f"#define KEYPAD_K2_MACRO_DELAY_MS {k2['delayMs']}",
            f"#define KEYPAD_K2_MACRO_ENTER {k2['tapEnter']}",
            f"static const char KEYPAD_K2_MACRO_TEXT[] = {_c_string_literal(k2['macroText'])};",
            "#endif",
            "",
        ]
    )
    (gen / "keypad_keys_profile.h").write_text(keys_header, encoding="utf-8")

    profile_export = profile.model_dump(mode="json")
    (gen / "keypad_profile.json").write_text(
        json.dumps(profile_export, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _ = sketch
