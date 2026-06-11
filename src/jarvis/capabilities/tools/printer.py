"""
Outil imprimante 3D pour Jarvis — BambuLab.
- slice  : OrcaSlicer CLI (génère le G-code)
- print  : upload + start_print via bambulabs_api (MQTT)
- status : état temps réel via bambulabs_api
- cancel : stop_print via bambulabs_api
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.approval import get_approval_checker
from jarvis.kernel.settings import settings

_ORCA_CLI = "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"


def _require_bambu() -> tuple[str, str, str] | None:
    """Retourne (ip, serial, access_code) ou None si non configuré."""
    ip = settings.printer_ip
    serial = settings.printer_serial
    code = settings.printer_access_code
    if not (ip and serial and code):
        return None
    return ip, serial, code


def _make_printer() -> object:
    """Instancie un Printer bambulabs_api avec les settings courants."""
    import bambulabs_api as bl

    creds = _require_bambu()
    if creds is None:
        raise ValueError("PRINTER_IP / PRINTER_SERIAL / PRINTER_ACCESS_CODE non configurés")
    ip, serial, code = creds
    return bl.Printer(ip, code, serial)


def _wait_ready(printer: object, timeout: float = 5.0) -> None:
    """Attend que le client MQTT soit prêt."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if printer.mqtt_client_ready():
            return
        time.sleep(0.2)


class Printer3DTool(Tool):
    name = "printer_3d"
    description = (
        "Contrôle la BambuLab via MQTT.\n\n"
        "Actions disponibles :\n"
        "- slice  : slicer un fichier STL en G-code avec OrcaSlicer\n"
        "- print  : uploader le G-code et lancer l'impression sur la BambuLab\n"
        "- status : état de l'impression en cours (progression, temps restant)\n"
        "- cancel : annuler l'impression en cours\n\n"
        "Toujours demander confirmation via printer_slice / printer_print avant d'exécuter.\n\n"
        "Utilise cet outil quand l'utilisateur dit :\n"
        "'imprime ce modèle', 'slice ce STL', 'état de l'impression', 'annule l'impression'"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["slice", "print", "status", "cancel"],
            },
            "stl_path": {
                "type": "string",
                "description": "Chemin vers le fichier STL (pour slice)",
            },
            "gcode_path": {
                "type": "string",
                "description": "Chemin vers le fichier G-code .gcode ou .3mf (pour print)",
            },
            "profile": {
                "type": "string",
                "description": "Profil de slicer OrcaSlicer (ex: '0.2mm Standard')",
            },
            "plate": {
                "type": "integer",
                "description": "Numéro de plateau BambuLab (défaut: 1)",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: str,
        stl_path: str = "",
        gcode_path: str = "",
        profile: str = "0.2mm Standard",
        plate: int = 1,
        **_: object,
    ) -> ToolResult:

        checker = get_approval_checker()
        action_id = str(uuid.uuid4())[:8]

        if action == "slice":
            if checker:
                ok = await checker.check(
                    "printer_slice",
                    f"Slicer {Path(stl_path).name if stl_path else '?'} (profil: {profile})",
                    action_id,
                )
                if not ok:
                    return ToolResult(content="Slicing refusé.", is_error=True)
            return await self._slice(stl_path, profile)

        if action == "print":
            if checker:
                fname = Path(gcode_path).name if gcode_path else "?"
                ok = await checker.check(
                    "printer_print",
                    f"Lancer l'impression de {fname} sur la BambuLab",
                    action_id,
                )
                if not ok:
                    return ToolResult(content="Impression refusée.", is_error=True)
            return await self._print(gcode_path, plate)

        if action == "status":
            return await self._status()

        if action == "cancel":
            return await self._cancel()

        return ToolResult(content=f"Action inconnue: {action}", is_error=True)

    # ── Slice ────────────────────────────────────────────────────────────────

    async def _slice(self, stl_path: str, profile: str) -> ToolResult:
        if not stl_path:
            return ToolResult(content="stl_path requis pour slice", is_error=True)

        stl = Path(stl_path).expanduser()
        if not stl.exists():
            return ToolResult(content=f"Fichier non trouvé: {stl_path}", is_error=True)

        if not Path(_ORCA_CLI).exists():
            return ToolResult(content=f"OrcaSlicer introuvable : {_ORCA_CLI}", is_error=True)

        output_dir = stl.parent
        cmd = [_ORCA_CLI, "--slice", str(stl), "--output", str(output_dir)]
        logger.info(f"Slicing {stl.name} profile='{profile}'")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except TimeoutError:
            proc.kill()
            return ToolResult(content="Timeout slicing (>120s)", is_error=True)

        if proc.returncode == 0:
            gcode_files = sorted(output_dir.glob("*.gcode")) + sorted(output_dir.glob("*.3mf"))
            result_path = str(gcode_files[0]) if gcode_files else "?"
            return ToolResult(content=f"Slicing terminé. Fichier : {result_path}")
        return ToolResult(content=f"Erreur slicing: {stderr.decode()[:300]}", is_error=True)

    # ── Print (bambulabs_api) ────────────────────────────────────────────────

    async def _print(self, gcode_path: str, plate: int = 1) -> ToolResult:
        if not gcode_path:
            return ToolResult(content="gcode_path requis pour print", is_error=True)

        gcode = Path(gcode_path).expanduser()
        if not gcode.exists():
            return ToolResult(content=f"Fichier non trouvé: {gcode_path}", is_error=True)

        if _require_bambu() is None:
            return ToolResult(
                content="PRINTER_IP / PRINTER_SERIAL / PRINTER_ACCESS_CODE non configurés",
                is_error=True,
            )

        loop = asyncio.get_event_loop()

        def _do_print() -> str:
            printer = _make_printer()
            printer.connect()
            try:
                _wait_ready(printer)
                with gcode.open("rb") as f:
                    remote_name = printer.upload_file(f, gcode.name)
                time.sleep(1)
                ok = printer.start_print(remote_name, plate_number=plate)
                if ok:
                    return f"Impression lancée : {gcode.name} (plateau {plate})"
                return "Échec démarrage impression (start_print=False)"
            finally:
                printer.disconnect()

        try:
            msg = await asyncio.wait_for(loop.run_in_executor(None, _do_print), timeout=60)
            if msg.startswith("Échec"):
                return ToolResult(content=msg, is_error=True)
            return ToolResult(content=msg)
        except Exception as e:
            logger.error(f"Printer print error: {e}")
            return ToolResult(content=str(e), is_error=True)

    # ── Status (bambulabs_api) ───────────────────────────────────────────────

    async def _status(self) -> ToolResult:
        if _require_bambu() is None:
            return ToolResult(
                content="PRINTER_IP / PRINTER_SERIAL / PRINTER_ACCESS_CODE non configurés",
                is_error=True,
            )

        loop = asyncio.get_event_loop()

        def _get_status() -> dict:
            printer = _make_printer()
            printer.connect()
            try:
                _wait_ready(printer)
                time.sleep(1)
                return {
                    "state": str(printer.get_state()),
                    "percentage": printer.get_percentage(),
                    "time_min": printer.get_time(),
                    "file": printer.get_file_name(),
                }
            finally:
                printer.disconnect()

        try:
            info = await asyncio.wait_for(loop.run_in_executor(None, _get_status), timeout=15)
            state = info["state"]
            pct = info["percentage"]
            mins = info["time_min"]
            fname = info["file"] or ""

            if pct not in (None, ""):
                parts = [f"État : {state}", f"Progression : {pct}%"]
                if mins:
                    parts.append(f"Temps restant : {mins}min")
                if fname:
                    parts.append(f"Fichier : {fname}")
                return ToolResult(content=" | ".join(parts))
            return ToolResult(content=f"État BambuLab : {state}")
        except Exception as e:
            logger.error(f"Printer status error: {e}")
            return ToolResult(content=str(e), is_error=True)

    # ── Cancel (bambulabs_api) ───────────────────────────────────────────────

    async def _cancel(self) -> ToolResult:
        if _require_bambu() is None:
            return ToolResult(
                content="PRINTER_IP / PRINTER_SERIAL / PRINTER_ACCESS_CODE non configurés",
                is_error=True,
            )

        loop = asyncio.get_event_loop()

        def _do_cancel() -> bool:
            printer = _make_printer()
            printer.connect()
            try:
                _wait_ready(printer)
                return printer.stop_print()
            finally:
                printer.disconnect()

        try:
            ok = await asyncio.wait_for(loop.run_in_executor(None, _do_cancel), timeout=15)
            if ok:
                return ToolResult(content="Impression annulée.")
            return ToolResult(content="Échec annulation (stop_print=False)", is_error=True)
        except Exception as e:
            logger.error(f"Printer cancel error: {e}")
            return ToolResult(content=str(e), is_error=True)
