#!/usr/bin/env python3
"""Create a compact, version-scoped boot-v4 fixture from the tested temporary boot.

The fixture preserves only the bytes required to recreate the exact real-device-
tested R62 temporary boot around a future kernel replacement, plus provenance
metadata from the matching stock boot extracted from xm.zip.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import zipfile
from pathlib import Path

PAGE = 4096
MAGIC = b"ANDROID!"
EXPECTED_TESTED_BOOT_SHA256 = "3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_BASELINE_KERNEL_SHA256 = "f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(n: int) -> int:
    return (n + PAGE - 1) // PAGE * PAGE


def read_img(path: Path) -> bytes:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            imgs = [n for n in z.namelist() if n.lower().endswith(".img")]
            if len(imgs) != 1:
                raise SystemExit(
                    f"ERROR: expected exactly one .img in tested-boot ZIP, found {len(imgs)}"
                )
            print(f"zip_member={imgs[0]}")
            return z.read(imgs[0])
    return path.read_bytes()


def parse_boot_v4(data: bytes, label: str) -> dict[str, int]:
    if len(data) < PAGE or data[:8] != MAGIC:
        raise SystemExit(f"ERROR: {label} is not an Android boot image")
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from(
        "<IIII", data, 8
    )
    header_version = struct.unpack_from("<I", data, 40)[0]
    signature_size = struct.unpack_from("<I", data, 1580)[0]
    if header_version != 4 or header_size != 1584:
        raise SystemExit(
            f"ERROR: {label} expected boot v4/header_size 1584, "
            f"got v{header_version}/{header_size}"
        )
    return {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version": os_version,
        "header_size": header_size,
        "header_version": header_version,
        "signature_size": signature_size,
    }


ap = argparse.ArgumentParser()
ap.add_argument("tested_boot_or_zip", type=Path)
ap.add_argument("output_json", type=Path)
ap.add_argument(
    "--stock-boot",
    type=Path,
    required=True,
    help="Matching stock boot.img extracted from the versioned xm.zip",
)
ap.add_argument(
    "--stock-build",
    required=True,
    help="Exact HyperOS build, e.g. OS4.0.5.0.XBLCNXM",
)
a = ap.parse_args()

tested = read_img(a.tested_boot_or_zip)
tested_sha = sha(tested)
print(f"tested_boot_sha256={tested_sha}")
if tested_sha != EXPECTED_TESTED_BOOT_SHA256:
    raise SystemExit("ERROR: not the real-device-tested R62 #7 temporary boot")

tested_meta = parse_boot_v4(tested, "tested boot")
kernel_size = tested_meta["kernel_size"]
ramdisk_size = tested_meta["ramdisk_size"]

ko = PAGE
ke = ko + kernel_size
ro = ko + align(kernel_size)
re = ro + ramdisk_size
so = ro + align(ramdisk_size)
if so > len(tested):
    raise SystemExit("ERROR: truncated tested boot-v4 layout")

tested_kernel = tested[ko:ke]
if sha(tested_kernel) != EXPECTED_BASELINE_KERNEL_SHA256:
    raise SystemExit("ERROR: embedded kernel is not the tested R62 #7 Image")

stock = a.stock_boot.read_bytes()
stock_meta = parse_boot_v4(stock, "stock boot")
stock_kernel_size = stock_meta["kernel_size"]
stock_kernel = stock[PAGE : PAGE + stock_kernel_size]
if len(stock_kernel) != stock_kernel_size:
    raise SystemExit("ERROR: truncated stock boot kernel payload")

fixture = {
    "schema": 1,
    "source": "pandora OS4 R62 #7 real-device-tested FASTBOOT-BOOT-ONLY",
    "stock_build": a.stock_build,
    "stock_boot_sha256": sha(stock),
    "stock_header_sha256": sha(stock[:PAGE]),
    "stock_kernel_sha256": sha(stock_kernel),
    "stock_kernel_size": stock_kernel_size,
    "safe_to_flash": False,
    "tested_boot_sha256": tested_sha,
    "baseline_kernel_sha256": sha(tested_kernel),
    "header_version": tested_meta["header_version"],
    "header_size": tested_meta["header_size"],
    "kernel_size": tested_meta["kernel_size"],
    "ramdisk_size": tested_meta["ramdisk_size"],
    "os_version": tested_meta["os_version"],
    "signature_size": tested_meta["signature_size"],
    "header_page_b64": base64.b64encode(tested[:PAGE]).decode(),
    "ramdisk_region_b64": base64.b64encode(tested[ro:so]).decode(),
    "suffix_b64": base64.b64encode(tested[so:]).decode(),
}

a.output_json.parent.mkdir(parents=True, exist_ok=True)
a.output_json.write_text(
    json.dumps(fixture, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

print(f"stock_build={a.stock_build}")
print(f"stock_boot_sha256={fixture['stock_boot_sha256']}")
print(f"stock_header_sha256={fixture['stock_header_sha256']}")
print(f"stock_kernel_sha256={fixture['stock_kernel_sha256']}")
print(f"stock_kernel_size={fixture['stock_kernel_size']}")
print(f"ramdisk_region_bytes={so-ro}")
print(f"suffix_bytes={len(tested)-so}")
print(f"fixture_json_bytes={a.output_json.stat().st_size}")
print("safe_to_flash=false")
print("FIXTURE=PASS")
