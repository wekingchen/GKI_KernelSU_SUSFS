#!/usr/bin/env python3
"""Real-format, synthetic Boot v4 + LZ4 Legacy + newc CPIO fixture.

Used ONLY by hermetic unit tests. Does not claim OEM or real device provenance.
The LZ4 stream consists of one legal, literal-only block; no compressor needed.
The production decoder remains the external lz4 CLI, tested against real OTA data.
"""
from __future__ import annotations
import struct

def _align(value: int, to: int) -> int:
    return ((value + to - 1) // to) * to

def _cpio_entry(path: str, data: bytes, mode: int = 0o100644) -> bytes:
    fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(path.encode()) + 1, 0]
    head = b"070701" + b"".join(f"{v:08x}".encode() for v in fields)
    entry = head + path.encode() + b"\0"
    entry += b"\0" * (-len(entry) % 4)
    entry += data
    entry += b"\0" * (-len(entry) % 4)
    return entry

def _lz4_literal_block(data: bytes) -> bytes:
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("synthetic LZ4 fixture payload out of bounds")
    literal = len(data)
    token = min(literal, 15) << 4
    extension = bytearray()
    if literal >= 15:
        remainder = literal - 15
        while remainder >= 255:
            extension.append(255)
            remainder -= 255
        extension.append(remainder)
    block = bytes([token]) + bytes(extension) + data
    return b"\x02\x21\x4c\x18" + struct.pack("<I", len(block)) + block

def make_vendor_boot_v4(modules: dict[str, bytes]) -> bytes:
    if not modules or len(modules) > 12:
        raise ValueError("invalid fixture module count")
    cpio = b"".join(_cpio_entry("lib/modules/" + name, data)
                    for name, data in modules.items())
    cpio += _cpio_entry("TRAILER!!!", b"", 0)
    fragment = _lz4_literal_block(cpio)
    size = len(fragment)
    page = 4096
    header_size = 2128
    ramdisk_start = page
    table_start = _align(ramdisk_start + size, page)
    out = bytearray(table_start + 108)
    out[:8] = b"VNDRBOOT"
    for offset, value in ((8, 4), (12, page), (24, size),
                          (2096, header_size), (2100, 0),
                          (2112, 108), (2116, 1), (2120, 108)):
        struct.pack_into("<I", out, offset, value)
    out[ramdisk_start:ramdisk_start + size] = fragment
    struct.pack_into("<III", out, table_start, size, 0, 1)
    return bytes(out)
