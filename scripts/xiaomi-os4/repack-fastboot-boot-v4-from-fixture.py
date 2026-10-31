#!/usr/bin/env python3
"""Build a fastboot-boot-only Android boot v4 image directly from the
real-device-tested pandora fixture plus a candidate kernel Image.

The fixture contains the exact tested 4096-byte header and preserved
ramdisk/suffix regions, so a baseline kernel rebuild is not required.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
from pathlib import Path
from typing import NoReturn

BOOT_MAGIC = b"ANDROID!"
PAGE_SIZE = 4096
HEADER_V4_SIZE = 1584
CMDLINE_OFFSET = 44
CMDLINE_SIZE = 1536
LKM_GUARD = b"module_blacklist=kernelsu"


def fail(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int) -> int:
    return (value + PAGE_SIZE - 1) // PAGE_SIZE * PAGE_SIZE


def add_lkm_guard(header_page: bytearray) -> bytes:
    raw = bytes(header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE])
    nul = raw.find(b"\0")
    if nul < 0:
        fail("boot-v4 cmdline field is not NUL-terminated")
    original = raw[:nul]
    tokens = original.split()
    blacklist = [t for t in tokens if t.startswith(b"module_blacklist=")]
    if blacklist:
        values = blacklist[0].split(b"=", 1)[1].split(b",")
        if b"kernelsu" not in values:
            replacement = blacklist[0] + b",kernelsu"
            tokens = [replacement if t == blacklist[0] else t for t in tokens]
            guarded = b" ".join(tokens)
        else:
            guarded = original
    else:
        guarded = original + (b" " if original else b"") + LKM_GUARD

    if len(guarded) + 1 > CMDLINE_SIZE:
        fail("boot-v4 cmdline has no room for kernelsu LKM guard")
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE] = b"\0" * CMDLINE_SIZE
    header_page[CMDLINE_OFFSET:CMDLINE_OFFSET + len(guarded)] = guarded
    return guarded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", type=Path)
    ap.add_argument("image", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--expected-image-sha256", required=True)
    ap.add_argument("--expected-release", required=True)
    ap.add_argument("--expected-build", required=True)
    ap.add_argument("--expected-output-sha256")
    args = ap.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    schema = fixture.get("schema")
    if schema not in (1, 2):
        fail("unsupported fixture schema")
    if fixture.get("safe_to_flash") is not False:
        fail("fixture must remain fastboot-boot-only")
    if fixture.get("stock_build") != args.expected_build:
        fail("fixture build mismatch")
    if fixture.get("header_version") != 4 or fixture.get("header_size") != HEADER_V4_SIZE:
        fail("fixture is not the expected boot-v4 layout")

    try:
        header = bytearray(base64.b64decode(fixture["header_page_b64"], validate=True))
        ramdisk_region = base64.b64decode(fixture["ramdisk_region_b64"], validate=True)
        suffix = base64.b64decode(fixture["suffix_b64"], validate=True)
    except Exception as exc:
        fail(f"invalid fixture base64: {exc}")

    if len(header) != PAGE_SIZE or header[:8] != BOOT_MAGIC:
        fail("fixture header page invalid")

    header_version = struct.unpack_from("<I", header, 40)[0]
    header_size = struct.unpack_from("<I", header, 20)[0]
    if header_version != 4 or header_size != HEADER_V4_SIZE:
        fail("decoded fixture header does not match metadata")

    ramdisk_size = struct.unpack_from("<I", header, 12)[0]
    if ramdisk_size != fixture.get("ramdisk_size"):
        fail("fixture ramdisk metadata mismatch")
    if len(ramdisk_region) != align(ramdisk_size):
        fail("fixture ramdisk region length mismatch")

    image = args.image.read_bytes()
    image_sha = sha256(image)
    if image_sha != args.expected_image_sha256:
        fail(f"candidate Image SHA256 mismatch: {image_sha}")
    if args.expected_release.encode() not in image:
        fail("candidate kernel release marker missing")

    struct.pack_into("<I", header, 8, len(image))
    guarded_cmdline = add_lkm_guard(header)

    out = bytearray(header)
    out += image
    if schema == 2:
        # New OTA fixtures preserve the fixed same-OTA stock boot partition
        # length as a compact integer instead of embedding megabytes of NULs.
        target_size = fixture.get("boot_size")
        if (not isinstance(target_size, int) or
            target_size < PAGE_SIZE + align(len(image)) or
            target_size > 200 * 1024 * 1024):
            fail("candidate cannot fit in this OTA's recorded boot image")
        if (ramdisk_size != 0 or fixture.get("signature_size") != 0
            or ramdisk_region or suffix):
            fail("schema 2 only supports zero-ramdisk/zero-signature/zero-suffix boot")
        out += b"\0" * (target_size - len(out))
    else:
        out += b"\0" * (align(len(image)) - len(image))
        out += ramdisk_region
        out += suffix

    if out[:8] != BOOT_MAGIC or struct.unpack_from("<I", out, 40)[0] != 4:
        fail("output boot-v4 validation failed")
    if sha256(bytes(out[PAGE_SIZE:PAGE_SIZE + len(image)])) != image_sha:
        fail("embedded candidate Image hash mismatch")
    if bytes(out)[-64:-60] == b"AVBf":
        fail("output unexpectedly contains an AVB footer")

    out_sha = sha256(bytes(out))
    if schema == 2 and image_sha == fixture.get("baseline_kernel_sha256"):
        if out_sha != fixture.get("tested_boot_sha256"):
            fail("recorded human-tested baseline cannot be reconstructed byte-for-byte")
    if args.expected_output_sha256 and out_sha != args.expected_output_sha256:
        fail(f"output SHA256 mismatch: {out_sha}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)

    print(f"fixture_tested_boot_sha256={fixture.get('tested_boot_sha256','UNKNOWN')}")
    print(f"candidate_kernel_sha256={image_sha}")
    print(f"candidate_release={args.expected_release}")
    print(f"guarded_cmdline={guarded_cmdline.decode('ascii', errors='replace')}")
    print(f"output_sha256={out_sha}")
    print("FINAL_BOOT_V4_AUDIT=PASS")
    print("FLASHABLE=NO")
    print("USE=fastboot boot ONLY")


if __name__ == "__main__":
    main()
