#!/usr/bin/env python3
"""Rebuild the exact tested R62 #7 boot from a compact boot-v4 fixture + Image."""
from __future__ import annotations
import argparse, base64, hashlib, json, struct
from pathlib import Path

PAGE=4096
EXPECTED_TESTED_BOOT_SHA256="3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_BASELINE_KERNEL_SHA256="f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"

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
