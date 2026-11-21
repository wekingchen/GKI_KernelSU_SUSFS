#!/usr/bin/env python3
"""Bounded, read-only Android vendor_boot v4 LZ4 legacy CPIO .ko inventory.

Every returned module is from an original vendor_boot ramdisk fragment of the
same stock-input ZIP. No flash, write or ABI acceptance occurs here.
"""
from __future__ import annotations
import struct
import subprocess

PAGE = 4096
MAX_RAMDISK = 64 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024
MAX_MODULES = 4096
MAX_MODULE = 40 * 1024 * 1024


def _up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def _cpio_modules(raw: bytes):
    p = 0
    entries = 0
    while p + 110 <= len(raw):
        if raw[p:p + 6] not in (b"070701", b"070702"):
            raise ValueError("vendor ramdisk is not valid newc CPIO")
        try:
            fields = [int(raw[p + 6 + i * 8:p + 14 + i * 8], 16)
                      for i in range(13)]
        except ValueError as exc:
            raise ValueError("invalid CPIO header field") from exc
        size, namesize, mode = fields[6], fields[11], fields[1]
        if not 2 <= namesize <= 2048 or size > MAX_MODULE:
            raise ValueError("vendor ramdisk member exceeds bounds")
        end = p + 110 + namesize
        if end > len(raw) or raw[end - 1] != 0:
            raise ValueError("invalid CPIO filename")
        name = raw[p + 110:end - 1].decode("utf-8", "strict")
        if name == "TRAILER!!!":
            return
        if (not name or name.startswith("/") or
                any(x in ("", ".", "..") for x in name.split("/"))):
            raise ValueError("unsafe vendor ramdisk member name")
        data_start = _up(end, 4)
        if data_start + size > len(raw):
            raise ValueError("truncated vendor ramdisk CPIO member")
        if (mode & 0o170000) == 0o100000 and name.startswith("lib/modules/") and name.endswith(".ko"):
            yield name, raw[data_start:data_start + size]
        p = _up(data_start + size, 4)
        entries += 1
        if entries > 15000:
            raise ValueError("vendor ramdisk member count exceeds limit")
    raise ValueError("vendor ramdisk missing newc trailer")


def extract_vendor_boot_modules(vendor_boot: bytes) -> list[tuple[str, bytes]]:
    if len(vendor_boot) < PAGE or vendor_boot[:8] != b"VNDRBOOT":
        raise ValueError("invalid vendor_boot v4")
    version, page = struct.unpack_from("<II", vendor_boot, 8)
    ramdisk_size = struct.unpack_from("<I", vendor_boot, 24)[0]
    header_size, dtb_size = struct.unpack_from("<II", vendor_boot, 2096)
    table_size, entries, entry_size = struct.unpack_from("<III", vendor_boot, 2112)
    if (version != 4 or page != PAGE or header_size != 2128 or
            not 0 < ramdisk_size <= MAX_RAMDISK or not 1 <= entries <= 32 or
            entry_size != 108 or table_size < entries * entry_size or
            table_size > 64 * 1024):
        raise ValueError("unsupported vendor_boot v4 table/layout")
    start = _up(header_size, page)
    dtb_start = _up(start + ramdisk_size, page)
    table_start = _up(dtb_start + dtb_size, page)
    if (start + ramdisk_size > len(vendor_boot) or
            table_start + table_size > len(vendor_boot)):
        raise ValueError("truncated vendor_boot v4")
    compressed = vendor_boot[start:start + ramdisk_size]
    modules = []
    names = set()
    fragment_regions = []
    for i in range(entries):
        off = table_start + i * entry_size
        size, ramdisk_off, _type = struct.unpack_from("<III", vendor_boot, off)
        if not 0 < size <= MAX_RAMDISK or ramdisk_off + size > len(compressed):
            raise ValueError("invalid vendor_boot ramdisk fragment offset")
        fragment_regions.append((ramdisk_off, ramdisk_off + size))
        fragment = compressed[ramdisk_off:ramdisk_off + size]
        if fragment[:4] != b"\x02\x21\x4c\x18":
            raise ValueError("unsupported vendor ramdisk compression (expected LZ4 legacy)")
        try:
            proc = subprocess.run(["lz4", "-dc"], input=fragment,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=90, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("vendor ramdisk LZ4 decode failed") from exc
        if not proc.stdout or len(proc.stdout) > MAX_EXPANDED:
            raise ValueError("invalid vendor ramdisk expansion size")
        for name, data in _cpio_modules(proc.stdout):
            if name in names:
                raise ValueError("duplicated vendor_boot module")
            names.add(name)
            modules.append((name, data))
            if len(modules) > MAX_MODULES:
                raise ValueError("vendor_boot module count exceeded")
    fragment_regions.sort()
    if any(fragment_regions[j][1] > fragment_regions[j + 1][0] for j in range(len(fragment_regions) - 1)):
        raise ValueError("overlapping vendor_boot fragments")
    if not modules:
        raise ValueError("vendor_boot has no verified .ko files")
    return modules
