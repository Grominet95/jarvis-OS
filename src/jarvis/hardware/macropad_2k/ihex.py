from __future__ import annotations

from pathlib import Path


def ihex_to_bytes(path: Path | str) -> bytes:
    mem: dict[int, int] = {}
    upper = 0
    src = Path(path)
    with src.open("r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            data = bytes.fromhex(line[1:])
            count = data[0]
            addr_hi = data[1]
            addr_lo = data[2]
            rectype = data[3]
            payload = data[4 : 4 + count]
            if rectype == 0x00:
                base = upper + (addr_hi << 8) + addr_lo
                for i, b in enumerate(payload):
                    mem[base + i] = b
            elif rectype == 0x01:
                break
            elif rectype == 0x04:
                if len(payload) >= 2:
                    upper = ((payload[0] << 8) | payload[1]) << 16
            elif rectype == 0x02:
                if len(payload) >= 2:
                    upper = (((payload[0] << 8) | payload[1]) << 4) & 0xFFFFF
    if not mem:
        raise ValueError("empty intel hex")
    lo = min(mem)
    hi = max(mem)
    out = bytearray(hi - lo + 1)
    for a in range(lo, hi + 1):
        out[a - lo] = mem.get(a, 0xFF)
    return bytes(out)


def ihex_to_bin_file(hex_path: Path | str, bin_path: Path | str) -> None:
    blob = ihex_to_bytes(hex_path)
    Path(bin_path).write_bytes(blob)
