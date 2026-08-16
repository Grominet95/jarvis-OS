# firmware_gen.py

- **Layer:** L1
- **Path:** `src/jarvis/hardware/macropad_2k/firmware_gen.py`
- **Purpose:** Module `hardware/macropad_2k/firmware_gen.py`.
- **Key symbols:** Functions: `_sanitize_usb_string`, `_sanitize_ascii_text`, `_clamp_int`, `_clamp01`, `_hex_to_rgb`, `_scale_rgb`, `_mods_mask`, `_key_def_from_chord`, `_c_string_literal`, `_c_char`, `_make_string_descriptor`, `_lighting_for_firmware`
- **Depends on:** See imports in source file (layer rules enforced by import-linter).
- **Used by:** See `maps/file-to-doc.yaml` reverse lookup or ripgrep callers.
- **Config:** See `07-config/env-reference.md` if this module reads settings.
- **Events:** See `02-kernel/events-bus.md` if module emits/subscribes to bus events.
- **Related flows:** See `maps/process-map.md` and section overviews in INDEX.
- **Source of truth:** [src/jarvis/hardware/macropad_2k/firmware_gen.py](../../src/jarvis/hardware/macropad_2k/firmware_gen.py)

## Related docs

- [INDEX](../../../INDEX.md)
- [AI_INSTRUCTIONS](../../../AI_INSTRUCTIONS.md)
- [overview](../../overview.md)
- [route-map](../../../maps/route-map.md)
- [setup-flow](../../../01-entry-points/setup-flow.md)
- [windows-launchers](../../../01-entry-points/windows-launchers.md)
- [bundle-offline](../../../02-kernel/bundle-offline.md)
- [process-map](../../../maps/process-map.md)
- [env-reference](../../../07-config/env-reference.md)
- [run-flow](../../../01-entry-points/run-flow.md)

- **Last reviewed:** 2026-08-15 (jarvis-os @ local)
