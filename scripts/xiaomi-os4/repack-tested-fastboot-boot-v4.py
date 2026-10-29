#!/usr/bin/env python3
"""Repack the already-tested pandora OS4 R62 temporary boot image with the
R62 BakaSU/SUSFS/NoMount Image.

This tool is intentionally narrow and fail-closed:
- input template must be the previously tested FASTBOOT-BOOT-ONLY boot-v4 image;
- its embedded kernel must match R62 #7 exactly;
- input must not carry an AVB footer;
- only the kernel payload and kernel_size field are changed;
- ramdisk, cmdline, OS version, boot header and any existing boot-signature bytes
  are preserved byte-for-byte.

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
EXPECTED_TEMPLATE_KERNEL_SHA256 = "f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"
EXPECTED_FEATURE_KERNEL_SHA256 = "f0d842b770d63ef97a633233d1bd2db18228c796e836e77d8c22fc3b9d19a15c"
EXPECTED_TEMPLATE_RELEASE = b"6.12.69-android16-6-os4r62-analysis-4k"
EXPECTED_FEATURE_RELEASE = b"6.12.69-android16-6-os4r62-features-4k"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, size: int = PAGE_SIZE) -> int:
    return (value + size - 1) // size * size


def fail(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("template", type=Path, help="tested R62 #7 FASTBOOT-BOOT-ONLY.img")
    ap.add_argument("image", type=Path, help="R62 #4 BakaSU/SUSFS/NoMount Image")
    ap.add_argument("output", type=Path, help="output temporary boot image")
    args = ap.parse_args()

    template = args.template.read_bytes()
    new_kernel = args.image.read_bytes()

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
    if new_sha != EXPECTED_FEATURE_KERNEL_SHA256:
        fail(f"feature Image SHA256 mismatch: {new_sha}")
    if EXPECTED_FEATURE_RELEASE not in new_kernel:
        fail("feature Image release marker is missing")

    ramdisk = template[ramdisk_off:ramdisk_end]
    suffix = template[suffix_off:]
    if signature_size > len(suffix):
        fail(f"signature_size={signature_size} exceeds preserved suffix={len(suffix)}")

    header_page = bytearray(template[:PAGE_SIZE])
    struct.pack_into("<I", header_page, 8, len(new_kernel))

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
    if sha256(out_kernel) != EXPECTED_FEATURE_KERNEL_SHA256:
        fail("output embedded kernel hash validation failed")
    if bytes(out)[-64:-60] == b"AVBf":
        fail("output unexpectedly contains an AVB footer")

    args.output.write_bytes(out)
    print(f"template_kernel_sha256={old_sha}")
    print(f"feature_kernel_sha256={new_sha}")
    print(f"template_kernel_size={kernel_size}")
    print(f"feature_kernel_size={len(new_kernel)}")
    print(f"ramdisk_size={ramdisk_size}")
    print(f"signature_size={signature_size}")
    print(f"preserved_suffix_bytes={len(suffix)}")
    print(f"output_size={len(out)}")
    print(f"output_sha256={sha256(bytes(out))}")
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")


if __name__ == "__main__":
    main()
