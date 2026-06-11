"""Service Bluetooth — parsers macOS / Windows.

Extrait de `interfaces/api/config/devices.py` en Phase F §F.1.5 (entrée
BACKLOG). Le router HTTP appelait directement `_parse_bt_macos` /
`_parse_bt_windows`, ce qui couplait la logique métier au router. Les
parsers prennent désormais leur place ici, en `hardware/` (L1 autonome,
sibling de `hardware/macropad_2k/`), et le router les importe.

Aucune dépendance FastAPI : pur data-transformer (sortie texte d'outils
système → `list[dict]` UI-shaped).
"""

from __future__ import annotations

from jarvis.hardware.bluetooth._parsers import parse_bt_macos, parse_bt_windows

__all__ = ["parse_bt_macos", "parse_bt_windows"]
