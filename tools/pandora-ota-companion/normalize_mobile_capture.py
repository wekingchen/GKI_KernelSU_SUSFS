#!/usr/bin/env python3
"""Convert read-only pandora mobile capture into existing fixed Release *xm.zip contract.

This is a strict file-format normalizer, NOT evidence that active boot is pristine OEM.
No shell commands, no archive extraction onto the host, no flash operations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

MAX_CAPTURE = 950 * 1024 * 1024
MAX_OUTER_FILE = 650 * 1024 * 1024
MAX_MODULE_BYTES = 500 * 1024 * 1024
MAX_MODULES = 4096
MAX_ENTRY = 40 * 1024 * 1024
ROOTS = (
    "vendor_dlkm/lib/modules/",
    "vendor/lib/modules/",
    "odm_dlkm/lib/modules/",
    "system_dlkm/lib/modules/",
)
BOOT_PARTS = ("boot", "init_boot", "vendor_boot", "dtbo")
BUILD_PATTERN = re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
KO_PATTERN = re.compile(r"\.ko(?:\.(?:zst|xz|gz))?\Z", re.I)
UNAME_PATTERN = re.compile(r"6\.12\.[0-9]+-android16-6-[A-Za-z0-9_.-]+\Z")


def fail(reason: str) -> None:
    raise ValueError(reason)


def parse_manifest(content: bytes) -> dict[str, str]:
    if len(content) > 8192:
        fail("oversized manifest")
    result: dict[str, str] = {}
    for line in content.decode("utf-8", "strict").splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            fail("invalid manifest record")
        key, value = line.split("=", 1)
        if not key or key in result or len(value) > 250:
            fail("invalid or duplicated manifest field")
        result[key] = value.strip()
    if result.get("schema") != "pandora-ota-capture-v1":
        fail("unsupported mobile capture schema")
    if result.get("source") != "ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK":
        fail("unknown data origin")
    if result.get("device") != "pandora" or result.get("ro.product.device") != "pandora":
        fail("device is not pandora")
    return result


def copy_hash(src: BinaryIO, dst: BinaryIO, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = src.read(256 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            fail("archive member exceeds allowed size")
        dst.write(chunk)
        digest.update(chunk)
    return digest.hexdigest(), total


def normalize(source: Path, output: Path) -> dict:
    if output.exists() or not source.is_file() or source.stat().st_size > MAX_CAPTURE:
        fail("missing, oversized or existing destination archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as capture:
        files = [info for info in capture.infolist() if not info.is_dir()]
        if len(files) > 30 or len({f.filename for f in files}) != len(files):
            fail("unexpected capture entries or duplicates")
        if sum(f.file_size for f in files) > 1900 * 1024 * 1024:
            fail("capture expands beyond allowed size")
        if any(f.file_size > MAX_OUTER_FILE or f.flag_bits & 1 or
               "/" in f.filename or "\\" in f.filename for f in files):
            fail("invalid capture member")
        by_name = {i.filename: i for i in files}
        for needed in ("manifest.txt", "kernel-release.txt", "oem-modules.tar"):
            if needed not in by_name:
                fail("missing " + needed)
        meta = parse_manifest(capture.read("manifest.txt"))
        build = meta.get("ro.mi.os.version.incremental", "")
        if not BUILD_PATTERN.fullmatch(build):
            fail("invalid HyperOS build: " + build)
        slot = meta.get("slot", "")
        if slot not in ("_a", "_b") or meta.get("ro.boot.slot_suffix") != slot:
            fail("slot mismatch")
        uname = meta.get("uname", "")
        if not UNAME_PATTERN.fullmatch(uname) or uname != capture.read(
                "kernel-release.txt").decode("utf-8", "strict").strip():
            fail("kernel release mismatch")
        for part in BOOT_PARTS:
            member = part + slot + ".img"
            if member not in by_name or by_name[member].file_size < 4096:
                fail("missing or too-small device partition: " + member)

        # Root tar -chf follows OEM links. Inspect only regular .ko entries;
        # a symlink surviving the capture is rejected rather than guessed.
        with tempfile.TemporaryDirectory(prefix="pandora-mobile-") as td:
            nested = Path(td, "oem-modules.zip")
            seen: set[str] = set()
            count = 0
            bytes_total = 0
            with capture.open("oem-modules.tar") as tar_input:
                with tarfile.open(fileobj=tar_input, mode="r|*") as archive:
                    with zipfile.ZipFile(
                            nested, "w", compression=zipfile.ZIP_DEFLATED,
                            compresslevel=6, allowZip64=True) as oem:
                        visited = 0
                        for member in archive:
                            visited += 1
                            if visited > 15000:
                                fail("too many TAR entries")
                            name = member.name.removeprefix("./").lstrip("/")
                            if not name or member.isdir():
                                continue
                            if member.issym() or member.islnk():
                                fail("module capture contains unexpected symlink")
                            if not member.isfile():
                                fail("unexpected special file in module TAR")
                            if ".." in name.split("/") or not any(
                                    name.startswith(prefix) for prefix in ROOTS):
                                fail("module path outside allowed OEM roots")
                            if not KO_PATTERN.search(name):
                                continue
                            if name in seen:
                                fail("duplicated OEM kernel module")
                            seen.add(name)
                            count += 1
                            bytes_total += member.size
                            if (count > MAX_MODULES or bytes_total > MAX_MODULE_BYTES
                                    or member.size < 64 or member.size > MAX_ENTRY):
                                fail("invalid OEM kernel module count/size")
                            input_file = archive.extractfile(member)
                            if input_file is None:
                                fail("unreadable OEM module in TAR")
                            with input_file, oem.open(name, "w", force_zip64=True) as target:
                                _, copied = copy_hash(input_file, target, MAX_ENTRY)
                            if copied != member.size:
                                fail("truncated OEM module")
            if count == 0:
                fail("no OEM kernel modules found")
            if nested.stat().st_size > 600 * 1024 * 1024:
                fail("OEM modules ZIP too large")
            readme = (
                f"device=pandora\nbuild={build}\nuname={uname}\nslot={slot}\n"
                "collected_from_live_device=YES\noperation=READ_ONLY\n"
                "note=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK; boot may be modified\n"
                "note2=init_boot may include Root modifications; never assume factory original\n"
            ).encode("utf-8")
            count_text = f"MODULE_COUNT={count}\n".encode("ascii")
            hashes: dict[str, str] = {}
            with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as final:
                for part in BOOT_PARTS:
                    name = part + ".img"
                    with capture.open(part + slot + ".img") as input_file:
                        with final.open(name, "w", force_zip64=True) as target:
                            sha, copied = copy_hash(input_file, target, MAX_OUTER_FILE)
                    if copied != by_name[part + slot + ".img"].file_size:
                        fail("truncated " + part)
                    hashes[name] = sha
                with nested.open("rb") as input_file, final.open(
                        "oem-modules.zip", "w", force_zip64=True) as target:
                    sha, copied = copy_hash(input_file, target, 600 * 1024 * 1024)
                hashes["oem-modules.zip"] = sha
                final.writestr("oem-modules-count.txt", count_text)
                final.writestr("README.txt", readme)
                final.writestr("SHA256SUMS.txt", "".join(
                    f"{hashes[name]}  {name}\n"
                    for name in (*[p + ".img" for p in BOOT_PARTS],
                                 "oem-modules.zip")).encode("ascii"))
    if output.stat().st_size < 4096 or output.stat().st_size > MAX_CAPTURE:
        output.unlink(missing_ok=True)
        fail("normalized xm.zip size out of bounds")
    digest = hashlib.file_digest(output.open("rb"), "sha256").hexdigest()
    return dict(build=build, slot=slot, uname=uname, modules=count,
                sha256=digest, bytes=output.stat().st_size, filename=output.name,
                provenance="ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        import json
        print(json.dumps(normalize(args.input, args.output),
                         sort_keys=True, ensure_ascii=False))
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
