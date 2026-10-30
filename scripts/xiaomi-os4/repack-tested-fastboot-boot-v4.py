#!/usr/bin/env python3
"""Repack the already-tested pandora OS4 R62 temporary boot image with the
R62 BakaSU/SUSFS/NoMount Image.

This tool is intentionally narrow and fail-closed:
- input template must be the previously tested FASTBOOT-BOOT-ONLY boot-v4 image;
- its embedded kernel must match R62 #7 exactly;
- input must not carry an AVB footer;
- only the kernel payload, kernel_size and one deliberate cmdline guard are changed;
- the cmdline guard appends module_blacklist=kernelsu so the current LKM-patched
  init_boot cannot load a second KernelSU on top of BakaSU Built-in;
- ramdisk, OS version, all other boot header fields and any existing
  boot-signature bytes are preserved byte-for-byte.

The output is for `fastboot boot` only. It is NOT a persistent flash image.
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
EXPECTED_FEATURE_KERNEL_SHA256 = "f0d842b770d63ef97a633233d1bd2db18228c796e836e77d8c22fc3b9d19a15c"
EXPECTED_PIDS_KMI_KERNEL_SHA256 = "97d7ee90bc498b0cc4617155c3a9cdc94dfd9d36b84f05993b9ff1fb5dbd2b88"
EXPECTED_TEMPLATE_RELEASE = b"6.12.69-android16-6-os4r62-analysis-4k"
EXPECTED_FEATURE_RELEASE = b"6.12.69-android16-6-os4r62-features-4k"
EXPECTED_PIDS_KMI_RELEASE = b"6.12.69-android16-6-os4r62-dspids-kmi-4k"


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
            fail("template already has module_blacklist= without kernelsu; manual review required")
    else:
        guarded = original + (b" " if original else b"") + LKM_GUARD

    if len(guarded) + 1 > CMDLINE_SIZE:
        fail("boot-v4 cmdline has no room for kernelsu LKM guard")
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE] = b"\0" * CMDLINE_SIZE
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + len(guarded)] = guarded
    return original, guarded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("template", type=Path, help="tested R62 #7 FASTBOOT-BOOT-ONLY.img")
    ap.add_argument("image", type=Path, help="approved R62 feature Image")
    ap.add_argument("output", type=Path, help="output temporary boot image")
    args = ap.parse_args()

    template = args.template.read_bytes()
    new_kernel = args.image.read_bytes()

    template_boot_sha = sha256(template)
    if template_boot_sha != EXPECTED_TEMPLATE_BOOT_SHA256:
        fail(f"tested FASTBOOT-BOOT-ONLY template SHA256 mismatch: {template_boot_sha}")

    if len(template) < PAGE_SIZE or template[:8] != BOOT_MAGIC:
        fail("template is not an Android boot image")

    kernel_size, ramdisk_size, _os_version, header_size = struct.unpack_from("<IIII", template, 8)
    header_version = struct.unpack_from("<I", template, 40)[0]
    signature_size = struct.unpack_from("<I", template, 1580)[0]

    if header_version != 4:
        fail(f"expected boot header v4, got v{header_version}")
    if header_size != HEADER_V4_SIZE:
        fail(f"expected header_size={HEADER_V4_SIZE}, got {header_size}")
    if template[-64:-60] == b"AVBf":
        fail("template unexpectedly contains an AVB footer; use the tested FASTBOOT-BOOT-ONLY image")

    kernel_off = PAGE_SIZE
    kernel_end = kernel_off + kernel_size
    ramdisk_off = kernel_off + align(kernel_size)
    ramdisk_end = ramdisk_off + ramdisk_size
    suffix_off = ramdisk_off + align(ramdisk_size)

    if kernel_end > len(template) or ramdisk_end > len(template) or suffix_off > len(template):
        fail("template layout is truncated or inconsistent with boot-v4 header")

    old_kernel = template[kernel_off:kernel_end]
    old_sha = sha256(old_kernel)
    if old_sha != EXPECTED_TEMPLATE_KERNEL_SHA256:
        fail(f"template kernel SHA256 mismatch: {old_sha}")
    if EXPECTED_TEMPLATE_RELEASE not in old_kernel:
        fail("template kernel release marker does not match the tested R62 #7 image")

    new_sha = sha256(new_kernel)
    approved = (
        (EXPECTED_FEATURE_KERNEL_SHA256, EXPECTED_FEATURE_RELEASE),
        (EXPECTED_PIDS_KMI_KERNEL_SHA256, EXPECTED_PIDS_KMI_RELEASE),
    )
    approved_release = next((release for digest, release in approved if digest == new_sha), None)
    if approved_release is None:
        fail(f"feature Image SHA256 mismatch: {new_sha}")
    if approved_release not in new_kernel:
        fail("approved feature Image release marker is missing")

    ramdisk = template[ramdisk_off:ramdisk_end]
    suffix = template[suffix_off:]
    if signature_size > len(suffix):
        fail(f"signature_size={signature_size} exceeds preserved suffix={len(suffix)}")

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
    if struct.unpack_from("<I", out, 8)[0] != len(new_kernel):
        fail("output kernel_size field validation failed")
    out_kernel = bytes(out[PAGE_SIZE:PAGE_SIZE + len(new_kernel)])
    if sha256(out_kernel) != new_sha:
        fail("output embedded kernel hash validation failed")
    if bytes(out)[-64:-60] == b"AVBf":
        fail("output unexpectedly contains an AVB footer")
    out_cmdline_raw = bytes(out[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE])
    out_cmdline = out_cmdline_raw.split(b"\0", 1)[0]
    if LKM_GUARD not in out_cmdline.split():
        fail("output is missing module_blacklist=kernelsu LKM guard")

    args.output.write_bytes(out)
    print(f"template_boot_sha256={template_boot_sha}")
    print(f"template_kernel_sha256={old_sha}")
    print(f"feature_kernel_sha256={new_sha}")
    print(f"template_kernel_size={kernel_size}")
    print(f"feature_kernel_size={len(new_kernel)}")
    print(f"ramdisk_size={ramdisk_size}")
    print(f"signature_size={signature_size}")
    print(f"preserved_suffix_bytes={len(suffix)}")
    print(f"template_cmdline={original_cmdline.decode('ascii', errors='replace')}")
    print(f"guarded_cmdline={guarded_cmdline.decode('ascii', errors='replace')}")
    print("lkm_guard=module_blacklist=kernelsu")
    print(f"output_size={len(out)}")
    print(f"output_sha256={sha256(bytes(out))}")
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")


if __name__ == "__main__":
    main()
