#!/usr/bin/env python3
"""Repack the verified Xiaomi 17 Pro OS4 R62 #7 temporary boot-v4 template
with a candidate Image that has already passed the caller's ABI gate.

Unlike repack-tested-fastboot-boot-v4.py, the candidate SHA/release are passed
explicitly by the CI job because a newly-built candidate cannot be hardcoded
before the build. The trusted template identity remains hardcoded.

This is for fastboot boot only; never persistent flashing.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path
from typing import NoReturn

BOOT_MAGIC = b"ANDROID!"
PAGE_SIZE = 4096
HEADER_V4_SIZE = 1584
CMDLINE_OFFSET = 44
CMDLINE_SIZE = 1536
LKM_GUARD = b"module_blacklist=kernelsu"
EXPECTED_TEMPLATE_BOOT_SHA256 = "3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_TEMPLATE_KERNEL_SHA256 = "f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"
EXPECTED_TEMPLATE_RELEASE = b"6.12.69-android16-6-os4r62-analysis-4k"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, size: int = PAGE_SIZE) -> int:
    return (value + size - 1) // size * size


def fail(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def add_lkm_guard(header_page: bytearray) -> tuple[bytes, bytes]:
    raw = bytes(header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE])
    nul = raw.find(b"\0")
    if nul < 0:
        fail("boot-v4 cmdline field is not NUL-terminated")
    original = raw[:nul]
    if b"module_blacklist=" in original:
        tokens = original.split()
        values = [t.split(b"=", 1)[1] for t in tokens if t.startswith(b"module_blacklist=")]
        if any(b"kernelsu" in v.split(b",") for v in values):
            guarded = original
        else:
            fail("template already has module_blacklist= without kernelsu")
    else:
        guarded = original + (b" " if original else b"") + LKM_GUARD

    if len(guarded) + 1 > CMDLINE_SIZE:
        fail("boot-v4 cmdline has no room for kernelsu LKM guard")
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE] = b"\0" * CMDLINE_SIZE
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + len(guarded)] = guarded
    return original, guarded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("template", type=Path)
    ap.add_argument("image", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--expected-image-sha256", required=True)
    ap.add_argument("--expected-release", required=True)
    args = ap.parse_args()

    template = args.template.read_bytes()
    new_kernel = args.image.read_bytes()

    if sha256(template) != EXPECTED_TEMPLATE_BOOT_SHA256:
        fail("tested FASTBOOT-BOOT-ONLY template SHA256 mismatch")
    if len(template) < PAGE_SIZE or template[:8] != BOOT_MAGIC:
        fail("template is not an Android boot image")

    kernel_size, ramdisk_size, _os_version, header_size = struct.unpack_from("<IIII", template, 8)
    header_version = struct.unpack_from("<I", template, 40)[0]
    signature_size = struct.unpack_from("<I", template, 1580)[0]
    if header_version != 4 or header_size != HEADER_V4_SIZE:
        fail("boot-v4 header mismatch")
    if template[-64:-60] == b"AVBf":
        fail("template unexpectedly contains an AVB footer")

    kernel_off = PAGE_SIZE
    kernel_end = kernel_off + kernel_size
    ramdisk_off = kernel_off + align(kernel_size)
    ramdisk_end = ramdisk_off + ramdisk_size
    suffix_off = ramdisk_off + align(ramdisk_size)
    if kernel_end > len(template) or ramdisk_end > len(template) or suffix_off > len(template):
        fail("template layout is truncated")

    old_kernel = template[kernel_off:kernel_end]
    if sha256(old_kernel) != EXPECTED_TEMPLATE_KERNEL_SHA256:
        fail("template kernel SHA256 mismatch")
    if EXPECTED_TEMPLATE_RELEASE not in old_kernel:
        fail("template release marker mismatch")

    new_sha = sha256(new_kernel)
    if new_sha != args.expected_image_sha256:
        fail(f"candidate Image SHA256 mismatch: {new_sha}")
    expected_release = args.expected_release.encode()
    if expected_release not in new_kernel:
        fail("candidate kernel release marker missing")

    ramdisk = template[ramdisk_off:ramdisk_end]
    suffix = template[suffix_off:]
    if signature_size > len(suffix):
        fail("signature size exceeds preserved suffix")

    header_page = bytearray(template[:PAGE_SIZE])
    struct.pack_into("<I", header_page, 8, len(new_kernel))
    original_cmdline, guarded_cmdline = add_lkm_guard(header_page)

    out = bytearray(header_page)
    out += new_kernel
    out += b"\0" * (align(len(new_kernel)) - len(new_kernel))
    out += ramdisk
    out += b"\0" * (align(len(ramdisk)) - len(ramdisk))
    out += suffix

    if out[:8] != BOOT_MAGIC or struct.unpack_from("<I", out, 40)[0] != 4:
        fail("internal output validation failed")
    if sha256(bytes(out[PAGE_SIZE:PAGE_SIZE + len(new_kernel)])) != new_sha:
        fail("embedded candidate Image hash mismatch")
    if bytes(out)[-64:-60] == b"AVBf":
        fail("output unexpectedly contains an AVB footer")
    out_cmdline = bytes(out[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE]).split(b"\0", 1)[0]
    if LKM_GUARD not in out_cmdline.split():
        fail("output missing kernelsu LKM guard")

    args.output.write_bytes(out)
    print(f"template_boot_sha256={EXPECTED_TEMPLATE_BOOT_SHA256}")
    print(f"candidate_kernel_sha256={new_sha}")
    print(f"candidate_release={args.expected_release}")
    print(f"guarded_cmdline={guarded_cmdline.decode('ascii', errors='replace')}")
    print(f"output_sha256={sha256(bytes(out))}")
    print("FINAL_BOOT_V4_AUDIT=PASS")
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")


if __name__ == "__main__":
    main()
