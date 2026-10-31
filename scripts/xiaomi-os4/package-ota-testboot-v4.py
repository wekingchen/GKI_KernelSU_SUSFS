#!/usr/bin/env python3
"""Create a NO-FLASH, user-test-only Android boot v4 from SAME-OTA stock boot.
Never use old LKG templates, never build if any gate fails. No device writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path

PAGE = 4096
CMD = 44
CMD_LEN = 1536
MAX_BOOT = 200 * 1024 * 1024
BOOT_RE = re.compile(r"boot(?:_[^/]*)?\.img$", re.I)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fail(text):
    raise SystemExit("ERROR: " + text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-zip", required=True, type=Path)
    ap.add_argument("--stock-report", required=True, type=Path)
    ap.add_argument("--abi-report", required=True, type=Path)
    ap.add_argument("--metadata", required=True, type=Path)
    ap.add_argument("--candidate-image", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    stock = json.loads(args.stock_report.read_text())
    gate = json.loads(args.abi_report.read_text())
    meta = dict(line.split("=", 1) for line in args.metadata.read_text().splitlines() if "=" in line)
    if gate.get("gate") != "CRC_AND_VERMAGIC_MATCH_CANDIDATE" or gate.get("eligible_for_fastboot_boot") is not True:
        fail("OEM ABI report does not permit temporary boot candidate")
    if stock.get("status") != "NEW_OTA_CANDIDATE" or not stock.get("kernel_marker_verified"):
        fail("not a verified new-OTA stock boot identity")
    if gate.get("stock_input_sha256") != stock.get("ota_source_id") or gate.get("stock_build") != stock.get("build"):
        fail("ABI evidence does not refer to exact same OTA")
    if meta.get("STOCK_INPUT_SHA256") != stock.get("ota_source_id"):
        fail("candidate compiled from different OTA")
    if meta.get("KERNEL_RELEASE") != stock.get("uname") or meta.get("KERNEL_RELEASE") != gate.get("kernel_release"):
        fail("kernel release/KO vermagic mismatch")
    with zipfile.ZipFile(args.stock_zip) as z:
        names = [f for f in z.infolist() if not f.is_dir() and BOOT_RE.fullmatch(f.filename.rsplit("/",1)[-1])]
        if len(names) != 1 or names[0].file_size > MAX_BOOT:
            fail("requires one same-OTA boot image")
        stock_boot = z.read(names[0])
    if sha(args.stock_zip.read_bytes()) != stock["ota_source_id"] or sha(stock_boot) != stock["stock_boot_sha256"]:
        fail("stock ZIP / boot SHA256 changed")
    if len(stock_boot) < PAGE or stock_boot[:8] != b"ANDROID!":
        fail("stock boot is invalid")
    ks, rs, _, header_size = struct.unpack_from("<IIII", stock_boot, 8)
    header_version = struct.unpack_from("<I", stock_boot, 40)[0]
    signature_size = struct.unpack_from("<I", stock_boot, 1580)[0]
    if header_version != 4 or header_size != 1584 or rs != 0 or signature_size != 0:
        fail("unsupported boot v4 layout (ramdisk or signature present): human review")
    if PAGE + ks > len(stock_boot) or len(stock_boot) > MAX_BOOT:
        fail("stock boot kernel out of bounds")
    stock_suffix = stock_boot[PAGE + ((ks + PAGE-1)//PAGE)*PAGE:]
    if stock_suffix.strip(b"\0"):
        fail("stock boot has nonzero trailing data or AVB footer; refuse repack")
    image = args.candidate_image.read_bytes()
    if not image or sha(image) != meta.get("IMAGE_SHA256"):
        fail("candidate Image hash mismatch")
    if stock["uname"].encode("ascii") not in image:
        fail("candidate Image is missing expected kernel release marker")
    if PAGE + ((len(image)+PAGE-1)//PAGE)*PAGE > len(stock_boot):
        fail("new Image is larger than same-OTA boot partition")
    header = bytearray(stock_boot[:PAGE])
    raw = bytes(header[CMD:CMD+CMD_LEN])
    if b"\0" not in raw:
        fail("boot cmdline not NUL terminated")
    cmdline = raw.split(b"\0",1)[0]
    toks = cmdline.split()
    existing = [x for x in toks if x.startswith(b"module_blacklist=")]
    if len(existing) > 1:
        fail("ambiguous module blacklist flags")
    if existing:
        old = existing[0]
        values = old.split(b"=",1)[1].split(b",")
        if b"kernelsu" not in values:
            toks = [x + b",kernelsu" if x == old else x for x in toks]
        cmdline = b" ".join(toks)
    else:
        cmdline += (b" " if cmdline else b"") + b"module_blacklist=kernelsu"
    if len(cmdline) >= CMD_LEN:
        fail("no space for LKM guard")
    header[CMD:CMD+CMD_LEN] = b"\0"*CMD_LEN
    header[CMD:CMD+len(cmdline)] = cmdline
    struct.pack_into("<I", header, 8, len(image))
    out = bytearray(header)
    out += image
    out += b"\0" * (len(stock_boot)-len(out))
    if len(out) != len(stock_boot) or sha(out[PAGE:PAGE+len(image)]) != sha(image):
        fail("internal output size/kernel identity mismatch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    print("OTA_TEST_BOOT_PACKAGING=PASS_NOT_REAL_DEVICE_TESTED")
    print("USE=fastboot boot ONLY; NEVER fastboot flash")
    print("BOOT_SHA256="+sha(out))


if __name__ == "__main__":
    main()
