#!/usr/bin/env python3
"""Rebuild the exact tested R62 #7 boot from a compact boot-v4 fixture + Image."""
from __future__ import annotations
import argparse, base64, hashlib, json, struct
from pathlib import Path

PAGE=4096
EXPECTED_TESTED_BOOT_SHA256="3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_BASELINE_KERNEL_SHA256="f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"
EXPECTED_STOCK_BOOT_SHA256="4f873abec68220c0028c11c8833e7ec8b9652f263e850f1ddb76d19913374653"
EXPECTED_STOCK_HEADER_SHA256="946575ca66cdc3ede85ce96c59a2a75a286335d4cf5e47f9541a28244d567d90"
EXPECTED_STOCK_KERNEL_SIZE=41511424
EXPECTED_BUILD="OS4.0.5.0.XBLCNXM"

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def align(n: int) -> int:
    return (n + PAGE - 1) // PAGE * PAGE

ap=argparse.ArgumentParser()
ap.add_argument("fixture_json", type=Path)
ap.add_argument("baseline_image", type=Path)
ap.add_argument("output", type=Path)
a=ap.parse_args()

f=json.loads(a.fixture_json.read_text(encoding="utf-8"))
if f.get("schema") != 1:
    raise SystemExit("ERROR: unsupported fixture schema")
if f.get("tested_boot_sha256") != EXPECTED_TESTED_BOOT_SHA256:
    raise SystemExit("ERROR: fixture tested boot hash mismatch")
if f.get("baseline_kernel_sha256") != EXPECTED_BASELINE_KERNEL_SHA256:
    raise SystemExit("ERROR: fixture baseline kernel hash mismatch")
if f.get("stock_build") != EXPECTED_BUILD or f.get("stock_boot_sha256") != EXPECTED_STOCK_BOOT_SHA256:
    raise SystemExit("ERROR: stock version or full stock boot provenance mismatch")
if f.get("stock_header_sha256") != EXPECTED_STOCK_HEADER_SHA256 or f.get("stock_kernel_size") != EXPECTED_STOCK_KERNEL_SIZE:
    raise SystemExit("ERROR: stock header provenance mismatch")
if f.get("safe_to_flash") is not False:
    raise SystemExit("ERROR: fixture must explicitly remain non-flashable")

header=bytearray(base64.b64decode(f["header_page_b64"]))
ramdisk_region=base64.b64decode(f["ramdisk_region_b64"])
suffix=base64.b64decode(f["suffix_b64"])
kernel=a.baseline_image.read_bytes()

if len(header) != PAGE or header[:8] != b"ANDROID!":
    raise SystemExit("ERROR: invalid fixture header")
if struct.unpack_from("<I",header,40)[0] != 4 or struct.unpack_from("<I",header,36)[0] != 1584:
    raise SystemExit("ERROR: fixture is not Android boot v4")
if sha(kernel) != EXPECTED_BASELINE_KERNEL_SHA256:
    raise SystemExit("ERROR: baseline Image hash mismatch")
if len(kernel) != f.get("kernel_size") or f.get("ramdisk_size") != 0 or f.get("signature_size") != 0:
    raise SystemExit("ERROR: unexpected tested boot-v4 layout")
if ramdisk_region or suffix:
    raise SystemExit("ERROR: this verified R62 #7 fixture must have no ramdisk or suffix")
if struct.unpack_from("<I",header,8)[0] != len(kernel):
    raise SystemExit("ERROR: fixture kernel_size does not match baseline")
stock_header=bytearray(header)
struct.pack_into("<I",stock_header,8,EXPECTED_STOCK_KERNEL_SIZE)
if sha(bytes(stock_header)) != EXPECTED_STOCK_HEADER_SHA256:
    raise SystemExit("ERROR: tested template header differs from verified stock boot (except kernel_size)")
print("STOCK_BOOT_HEADER_CACHE=VERIFIED")
print("STOCK_BOOT_SHA256_PIN="+EXPECTED_STOCK_BOOT_SHA256)

struct.pack_into("<I",header,8,len(kernel))
out=bytearray(header)
out += kernel
out += b"\0"*(align(len(kernel))-len(kernel))
out += ramdisk_region
out += suffix

got=sha(bytes(out))
print(f"rebuilt_tested_boot_sha256={got}")
print(f"rebuilt_tested_boot_size={len(out)}")
if got != EXPECTED_TESTED_BOOT_SHA256:
    raise SystemExit("ERROR: fixture reconstruction is not byte-identical to tested #7 boot")
a.output.write_bytes(out)
print("REAL_DEVICE_TESTED_TEMPLATE_REPRODUCED=YES")
