#!/usr/bin/env python3
"""Create a compact boot-v4 fixture from the already-tested temporary boot image.

The fixture intentionally excludes the kernel payload. It stores only bytes that
must be preserved around a future kernel replacement: the 4 KiB header page,
ramdisk (if any), aligned ramdisk padding, and post-ramdisk suffix/signature.

The resulting JSON is small enough to keep in git and lets CI reproduce the
exact real-device-tested R62 #7 temporary boot before swapping in a feature
kernel.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, struct, zipfile
from pathlib import Path

PAGE = 4096
MAGIC = b"ANDROID!"
EXPECTED_TESTED_BOOT_SHA256 = "3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_BASELINE_KERNEL_SHA256 = "f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def align(n: int) -> int:
    return (n + PAGE - 1) // PAGE * PAGE

def read_img(path: Path) -> bytes:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            imgs=[n for n in z.namelist() if n.lower().endswith(".img")]
            if len(imgs) != 1:
                raise SystemExit(f"ERROR: expected exactly one .img in ZIP, found {len(imgs)}")
            print(f"zip_member={imgs[0]}")
            return z.read(imgs[0])
    return path.read_bytes()

ap=argparse.ArgumentParser()
ap.add_argument("tested_boot_or_zip", type=Path)
ap.add_argument("output_json", type=Path)
a=ap.parse_args()

data=read_img(a.tested_boot_or_zip)
got=sha(data)
print(f"tested_boot_sha256={got}")
if got != EXPECTED_TESTED_BOOT_SHA256:
    raise SystemExit("ERROR: not the real-device-tested R62 #7 temporary boot")

if len(data) < PAGE or data[:8] != MAGIC:
    raise SystemExit("ERROR: invalid Android boot image")
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", data, 8)
header_version = struct.unpack_from("<I", data, 40)[0]
signature_size = struct.unpack_from("<I", data, 1580)[0]
if header_version != 4 or header_size != 1584:
    raise SystemExit(f"ERROR: expected boot v4/header_size 1584, got v{header_version}/{header_size}")

ko=PAGE
ke=ko+kernel_size
ro=ko+align(kernel_size)
re=ro+ramdisk_size
so=ro+align(ramdisk_size)
if so > len(data):
    raise SystemExit("ERROR: truncated boot-v4 layout")
kernel=data[ko:ke]
if sha(kernel) != EXPECTED_BASELINE_KERNEL_SHA256:
    raise SystemExit("ERROR: embedded kernel is not the tested R62 #7 Image")

fixture={
    "schema": 1,
    "source": "pandora OS4 R62 #7 real-device-tested FASTBOOT-BOOT-ONLY",
    "tested_boot_sha256": got,
    "baseline_kernel_sha256": sha(kernel),
    "header_version": header_version,
    "header_size": header_size,
    "kernel_size": kernel_size,
    "ramdisk_size": ramdisk_size,
    "os_version": os_version,
    "signature_size": signature_size,
    "header_page_b64": base64.b64encode(data[:PAGE]).decode(),
    "ramdisk_region_b64": base64.b64encode(data[ro:so]).decode(),
    "suffix_b64": base64.b64encode(data[so:]).decode(),
}
a.output_json.parent.mkdir(parents=True, exist_ok=True)
a.output_json.write_text(json.dumps(fixture, indent=2, sort_keys=True)+"\n", encoding="utf-8")
print(f"ramdisk_region_bytes={so-ro}")
print(f"suffix_bytes={len(data)-so}")
print(f"fixture_json_bytes={a.output_json.stat().st_size}")
print("FIXTURE=PASS")
