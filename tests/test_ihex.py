"""Tests unitaires de hardware.macropad_2k.ihex (decodage Intel HEX)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.hardware.macropad_2k.ihex import ihex_to_bin_file, ihex_to_bytes


def _checksum(data: bytes) -> int:
    return (-sum(data)) & 0xFF


def _record(count: int, addr: int, rectype: int, payload: bytes) -> str:
    body = bytes([count, (addr >> 8) & 0xFF, addr & 0xFF, rectype]) + payload
    return ":" + (body + bytes([_checksum(body)])).hex().upper()


def _hex_file(tmp_path: Path, records: list[str]) -> Path:
    p = tmp_path / "fw.hex"
    p.write_text("\n".join(records) + "\n", encoding="ascii")
    return p


def test_ihex_simple_data(tmp_path: Path) -> None:
    records = [
        _record(4, 0x0000, 0x00, bytes([0xDE, 0xAD, 0xBE, 0xEF])),
        _record(0, 0x0000, 0x01, b""),
    ]
    blob = ihex_to_bytes(_hex_file(tmp_path, records))
    assert blob == bytes([0xDE, 0xAD, 0xBE, 0xEF])


def test_ihex_fills_gaps_with_ff(tmp_path: Path) -> None:
    records = [
        _record(1, 0x0000, 0x00, bytes([0x01])),
        _record(1, 0x0003, 0x00, bytes([0x02])),
        _record(0, 0x0000, 0x01, b""),
    ]
    blob = ihex_to_bytes(_hex_file(tmp_path, records))
    assert blob == bytes([0x01, 0xFF, 0xFF, 0x02])


def test_ihex_stops_at_eof_record(tmp_path: Path) -> None:
    records = [
        _record(1, 0x0000, 0x00, bytes([0xAA])),
        _record(0, 0x0000, 0x01, b""),
        _record(1, 0x0001, 0x00, bytes([0xBB])),
    ]
    blob = ihex_to_bytes(_hex_file(tmp_path, records))
    assert blob == bytes([0xAA])


def test_ihex_ignores_non_colon_lines(tmp_path: Path) -> None:
    p = tmp_path / "fw.hex"
    p.write_text(
        "; comment\n" + _record(1, 0x0000, 0x00, bytes([0x42])) + "\n",
        encoding="ascii",
    )
    assert ihex_to_bytes(p) == bytes([0x42])


def test_ihex_empty_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.hex"
    p.write_text("; nothing\n", encoding="ascii")
    with pytest.raises(ValueError, match="empty intel hex"):
        ihex_to_bytes(p)


def test_ihex_to_bin_file(tmp_path: Path) -> None:
    records = [
        _record(2, 0x0000, 0x00, bytes([0x12, 0x34])),
        _record(0, 0x0000, 0x01, b""),
    ]
    hex_path = _hex_file(tmp_path, records)
    bin_path = tmp_path / "out.bin"
    ihex_to_bin_file(hex_path, bin_path)
    assert bin_path.read_bytes() == bytes([0x12, 0x34])
