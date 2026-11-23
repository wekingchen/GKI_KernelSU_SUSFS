#!/usr/bin/env python3
"""Build the exact boot-v4 image semantics intended for persistent AnyKernel3.

READ-ONLY host-side tool. It starts from the exact OS4.0.6 stock boot image,
replaces only the kernel payload, and applies the same cmdline changes that the
persistent installer must make:
  - module_blacklist contains kernelsu
  - pandora_rust_binder_eexist=1

The output is still NONFLASH until boot partition capacity and installer
repack semantics are separately certified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path
from typing import NoReturn

PAGE = 4096
HEADER_V4_SIZE = 1584
CMDLINE_OFFSET = 44
CMDLINE_SIZE = 1536
BOOT_MAGIC = b"ANDROID!"
BOOT_RE = re.compile(r"boot(?:_[^/]*)?\.img$", re.I)
MAX_BOOT = 200 * 1024 * 1024
EEXIST = b"pandora_rust_binder_eexist=1"


def fail(message: str) -> NoReturn:
    raise SystemExit("ERROR: " + message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int) -> int:
    return (value + PAGE - 1) // PAGE * PAGE


def metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in result:
            fail("duplicate feature metadata key: " + key)
        result[key] = value
    return result


def patch_persistent_cmdline(original: bytes) -> bytes:
    try:
        original.decode("ascii", "strict")
    except UnicodeDecodeError:
        fail("stock boot cmdline is not ASCII")
    tokens = original.split()

    blacklists = [x for x in tokens if x.startswith(b"module_blacklist=")]
    if len(blacklists) > 1:
        fail("ambiguous module_blacklist flags")
    if blacklists:
        old = blacklists[0]
        values = [x for x in old.split(b"=", 1)[1].split(b",") if x]
        if b"kernelsu" not in values:
            replacement = old + (b"," if values else b"") + b"kernelsu"
            tokens = [replacement if x == old else x for x in tokens]
    else:
        tokens.append(b"module_blacklist=kernelsu")

    eexist = [x for x in tokens if x.startswith(b"pandora_rust_binder_eexist=")]
    if len(eexist) > 1:
        fail("ambiguous pandora_rust_binder_eexist flags")
    if eexist:
        if eexist[0] != EEXIST:
            fail("conflicting pandora_rust_binder_eexist value")
    else:
        tokens.append(EEXIST)

    patched = b" ".join(tokens)
    if len(patched) + 1 > CMDLINE_SIZE:
        fail("boot-v4 cmdline has no room for persistent compatibility guard")
    return patched


def extract_stock_boot(stock_zip: Path) -> bytes:
    with zipfile.ZipFile(stock_zip) as z:
        matches = [i for i in z.infolist()
                   if not i.is_dir()
                   and BOOT_RE.fullmatch(i.filename.rsplit("/", 1)[-1])]
        if len(matches) != 1 or matches[0].file_size > MAX_BOOT:
            fail("stock ZIP must contain exactly one bounded boot image")
        return z.read(matches[0])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-zip", type=Path, required=True)
    ap.add_argument("--compat-fixture", type=Path, required=True)
    ap.add_argument("--runtime-gate", type=Path, required=True)
    ap.add_argument("--feature-metadata", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--expected-output-sha256")
    args = ap.parse_args()

    fixture = json.loads(args.compat_fixture.read_text(encoding="utf-8"))
    gate = json.loads(args.runtime_gate.read_text(encoding="utf-8"))
    meta = metadata(args.feature_metadata)

    if gate.get("status") != "PASS_RUNTIME_SELECTED_EXACT_OS406":
        fail("runtime-selected OEM gate is not PASS")
    if gate.get("eligible_for_persistent_kernel_payload") is not False:
        fail("runtime gate must still be pre-persistent")
    if gate.get("stock_build") != fixture.get("stock_build"):
        fail("runtime gate/fixture build mismatch")
    if gate.get("stock_input_sha256") != fixture.get("stock_input_sha256"):
        fail("runtime gate/fixture stock input mismatch")
    if fixture.get("schema") != 2 or fixture.get("safe_to_flash") is not False:
        fail("compatibility fixture is not the exact nonflash boot-v4 fixture")
    if fixture.get("compatibility_kind") != "PANDORA_RUST_BINDER_EEXIST_SHIM":
        fail("wrong compatibility fixture kind")

    stock_zip_bytes = args.stock_zip.read_bytes()
    if sha256(stock_zip_bytes) != fixture.get("stock_input_sha256"):
        fail("stock ZIP hash mismatch")
    stock_boot = extract_stock_boot(args.stock_zip)
    if sha256(stock_boot) != fixture.get("stock_boot_sha256"):
        fail("stock boot hash mismatch")
    if len(stock_boot) < PAGE or stock_boot[:8] != BOOT_MAGIC:
        fail("invalid stock boot image")

    kernel_size, ramdisk_size, _os_version, header_size = struct.unpack_from("<IIII", stock_boot, 8)
    header_version = struct.unpack_from("<I", stock_boot, 40)[0]
    signature_size = struct.unpack_from("<I", stock_boot, 1580)[0]
    if header_version != 4 or header_size != HEADER_V4_SIZE:
        fail("stock boot is not Android boot v4")
    if kernel_size <= 0 or PAGE + align(kernel_size) > len(stock_boot):
        fail("stock kernel is out of bounds")
    if ramdisk_size != 0 or signature_size != 0:
        fail("OS4.0.6 persistent-equivalence proof expects zero ramdisk/signature")

    raw_cmdline = stock_boot[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE]
    nul = raw_cmdline.find(b"\0")
    if nul < 0:
        fail("stock boot cmdline is not NUL terminated")
    original_cmdline = raw_cmdline[:nul]
    patched_cmdline = patch_persistent_cmdline(original_cmdline)

    stock_payload_end = PAGE + align(kernel_size) + align(ramdisk_size)
    suffix = stock_boot[stock_payload_end:]
    if suffix.strip(b"\0"):
        fail("stock boot has nonzero suffix/AVB footer; persistent equivalence needs review")

    image = args.image.read_bytes()
    image_sha = sha256(image)
    if image_sha != gate.get("feature_image_sha256"):
        fail("feature Image does not match runtime-selected OEM gate")
    if meta.get("IMAGE_SHA256") != image_sha:
        fail("feature metadata Image SHA mismatch")
    if meta.get("SYSTEM_BUILD") != gate.get("stock_build"):
        fail("feature metadata build mismatch")
    if meta.get("KERNEL_RELEASE") != gate.get("kernel_release"):
        fail("feature metadata kernel release mismatch")
    if meta.get("PANDORA_RUST_BINDER_EEXIST_SHIM") != "1":
        fail("feature metadata does not contain exact EEXIST shim")
    if meta.get("COMPATIBILITY_PATCH_SHA256") != "5aab8a0a41369829707d6ea5ade437bc91a75dda4a5ac1fb6b1cb60158bef5ee":
        fail("feature metadata EEXIST patch identity drift")
    if gate["kernel_release"].encode("ascii") not in image:
        fail("feature Image missing expected uname marker")

    header = bytearray(stock_boot[:PAGE])
    struct.pack_into("<I", header, 8, len(image))
    header[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE] = b"\0" * CMDLINE_SIZE
    header[CMDLINE_OFFSET:CMDLINE_OFFSET + len(patched_cmdline)] = patched_cmdline

    out = bytearray(header)
    out += image
    out += b"\0" * (align(len(image)) - len(image))
    # ramdisk_size is zero for this exact stock build. Keep the general order.
    out += suffix

    if sha256(bytes(out[PAGE:PAGE + len(image)])) != image_sha:
        fail("embedded feature Image identity mismatch")
    if struct.unpack_from("<I", out, 40)[0] != 4:
        fail("output header version changed")
    if struct.unpack_from("<I", out, 12)[0] != 0 or struct.unpack_from("<I", out, 1580)[0] != 0:
        fail("output ramdisk/signature changed")
    out_sha = sha256(bytes(out))
    if args.expected_output_sha256 and out_sha != args.expected_output_sha256:
        fail("persistent-equivalent output differs from expected tested boot: " + out_sha)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)

    print("PERSISTENT_EQUIVALENT_BOOT_BUILD=PASS")
    print("STOCK_BOOT_SHA256=" + sha256(stock_boot))
    print("FEATURE_IMAGE_SHA256=" + image_sha)
    print("ORIGINAL_CMDLINE=" + original_cmdline.decode("ascii"))
    print("PATCHED_CMDLINE=" + patched_cmdline.decode("ascii"))
    print("OUTPUT_SHA256=" + out_sha)
    print("OUTPUT_SIZE=" + str(len(out)))
    print("STOCK_LOGICAL_BOOT_SIZE=" + str(len(stock_boot)))
    print("LOGICAL_GROWTH=" + str(max(0, len(out) - len(stock_boot))))
    if args.expected_output_sha256:
        print("PERSISTENT_BOOT_EQUIVALENCE=BYTE_EXACT_MATCH_TO_TRUE_DEVICE_TESTED_BOOT")
    else:
        print("PERSISTENT_BOOT_EQUIVALENCE=OUTPUT_BUILT_NOT_YET_MATCHED")
    print("FLASHABLE=NO_PARTITION_CAPACITY_NOT_YET_ATTESTED")
    print("USE=fastboot boot ONLY")


if __name__ == "__main__":
    main()
