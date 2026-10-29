#!/usr/bin/env python3
"""Recreate the exact previously-tested R62 #7 temporary boot from stock boot v4."""
from __future__ import annotations
import argparse, hashlib, struct
from pathlib import Path

PAGE=4096
MAGIC=b"ANDROID!"
EXPECTED_STOCK_BOOT_SHA="4f873abec68220c0028c11c8833e7ec8b9652f263e850f1ddb76d19913374653"
EXPECTED_STOCK_KERNEL_SHA="ed9e27aa606772d058684e023fcb2d3dca876505be90227cc8ca5e5d5b95622b"
EXPECTED_R62_KERNEL_SHA="f02d7b150783d4fcfd7271fb1d1b85b9effd211609a59b008c67527c685725f8"
EXPECTED_TESTED_BOOT_SHA="3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0"
EXPECTED_RELEASE=b"6.12.69-android16-6-os4r62-analysis-4k"

def sha(b): return hashlib.sha256(b).hexdigest()
def align(n): return (n+PAGE-1)//PAGE*PAGE

ap=argparse.ArgumentParser()
ap.add_argument("stock",type=Path)
ap.add_argument("kernel",type=Path)
ap.add_argument("output",type=Path)
a=ap.parse_args()
stock=a.stock.read_bytes(); new=a.kernel.read_bytes()
if sha(stock)!=EXPECTED_STOCK_BOOT_SHA: raise SystemExit("ERROR: wrong stock boot")
if stock[:8]!=MAGIC or len(stock)<PAGE: raise SystemExit("ERROR: invalid stock boot")
kernel_size,ramdisk_size,_os_version,header_size=struct.unpack_from("<IIII",stock,8)
header_version=struct.unpack_from("<I",stock,40)[0]
sig_size=struct.unpack_from("<I",stock,1580)[0]
if header_version!=4 or header_size!=1584: raise SystemExit("ERROR: expected boot header v4")
ko=PAGE; ke=ko+kernel_size
ro=ko+align(kernel_size); re=ro+ramdisk_size
so=ro+align(ramdisk_size); se=so+sig_size
if se>len(stock): raise SystemExit("ERROR: stock boot layout truncated")
oldk=stock[ko:ke]
if sha(oldk)!=EXPECTED_STOCK_KERNEL_SHA: raise SystemExit("ERROR: stock kernel mismatch")
if sha(new)!=EXPECTED_R62_KERNEL_SHA: raise SystemExit("ERROR: R62 #7 Image mismatch")
if EXPECTED_RELEASE not in new: raise SystemExit("ERROR: R62 #7 release marker missing")
header=bytearray(stock[:PAGE]); struct.pack_into("<I",header,8,len(new))
ramdisk=stock[ro:re]; signature=stock[so:se]
out=bytearray(header)
out+=new; out+=b"\0"*(align(len(new))-len(new))
out+=ramdisk; out+=b"\0"*(align(len(ramdisk))-len(ramdisk))
out+=signature
a.output.write_bytes(out)
got=sha(out)
print(f"stock_kernel_size={kernel_size}")
print(f"stock_ramdisk_size={ramdisk_size}")
print(f"stock_signature_size={sig_size}")
print(f"rebuilt_baseline_size={len(out)}")
print(f"rebuilt_baseline_sha256={got}")
if got!=EXPECTED_TESTED_BOOT_SHA:
    raise SystemExit("ERROR: reconstructed baseline is not byte-identical to the real-device-tested #7 temporary boot")
print("REAL_DEVICE_TESTED_TEMPLATE_REPRODUCED=YES")
