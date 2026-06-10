from __future__ import annotations

from loguru import logger

KEYPAD_HID_VID = 0x1209
KEYPAD_HID_PID = 0xC55D
CH55X_BOOTLOADER_VID = 0x4348
CH55X_BOOTLOADER_PID = 0x55E0


def keypad_hid_present() -> bool:
    try:
        import hid
    except Exception as exc:
        logger.debug("keypad_hid_present: hidapi unavailable: {}", exc)
        return False
    try:
        for d in hid.enumerate():
            if d.get("vendor_id") == KEYPAD_HID_VID and d.get("product_id") == KEYPAD_HID_PID:
                return True
    except Exception as exc:
        logger.debug("keypad_hid_present: enumerate failed: {}", exc)
    return False


def ch55x_bootloader_present() -> bool:
    try:
        import libusb_package
        import usb.backend.libusb1
        import usb.core
    except Exception as exc:
        logger.debug("ch55x_bootloader_present: pyusb unavailable: {}", exc)
        return False
    try:
        backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        if backend is None:
            return False
        devices = usb.core.find(
            backend=backend,
            find_all=True,
            idVendor=CH55X_BOOTLOADER_VID,
            idProduct=CH55X_BOOTLOADER_PID,
        )
        return any(True for _ in (devices or []))
    except Exception as exc:
        logger.debug("ch55x_bootloader_present: find failed: {}", exc)
        return False


def usb_status() -> dict[str, bool]:
    return {
        "hidPresent": keypad_hid_present(),
        "bootloaderPresent": ch55x_bootloader_present(),
    }
