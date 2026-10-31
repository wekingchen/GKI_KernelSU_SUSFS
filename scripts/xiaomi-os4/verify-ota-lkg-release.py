#!/usr/bin/env python3
"""Verify an exact, complete immutable OTA LKG Release payload offline."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

TAG = re.compile(r"pandora-os4-lkg-gen([1-9][0-9]*)\Z")
LINE = re.compile(r"([a-f0-9]{64})  ([A-Za-z0-9._+-]+)\Z")


def verify(folder: Path, tag: str) -> dict:
    m = TAG.fullmatch(tag)
    if not m:
        raise ValueError("invalid immutable LKG release tag")
    manifest = folder / ("SHA256SUMS-" + tag + ".txt")
    if not manifest.is_file():
        raise ValueError("missing SHA256 manifest")
    expected = {}
    for row in manifest.read_text(encoding="ascii").splitlines():
        found = LINE.fullmatch(row)
        if not found:
            raise ValueError("malformed SHA256 manifest entry")
        digest, name = found.groups()
        if name in expected or name == manifest.name:
            raise ValueError("duplicate or self-listed SHA manifest entry")
        expected[name] = digest
    actual = {f.name for f in folder.iterdir() if f.is_file() and f.name != manifest.name}
    if not expected or set(expected) != actual:
        raise ValueError("Release asset set differs from SHA256 manifest")
    for name, digest in expected.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("SHA256 mismatch for " + name)
    record = json.loads((folder / "ota-lkg-promotion-record.json").read_text())
    if record.get("schema") != 1 or record.get("status") != "USER_PROMOTED_OTA_LKG":
        raise ValueError("invalid promotion record")
    if record.get("generation") != int(m.group(1)) or record.get("archive_tag") != tag:
        raise ValueError("promotion record differs from Release generation")
    build = record.get("stock_build")
    if not isinstance(build, str) or not re.fullmatch(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+", build):
        raise ValueError("invalid OTA build in record")
    names = tuple(expected.keys())
    for target in (f"{build}-Gen{m.group(1)}-ORIGINAL-USER-ATTESTED-boot.img",
                   f"{build}-Gen{m.group(1)}-ORIGINAL-USER-ATTESTED-AnyKernel3.zip",
                   f"{build}-Gen{m.group(1)}-REBUILT-CI-ONLY-boot.img",
                   f"{build}-Gen{m.group(1)}-REBUILT-CI-ONLY-AnyKernel3.zip",
                   f"{build}-Gen{m.group(1)}-original-evidence.tar.zst",
                   f"{build}-Gen{m.group(1)}-rebuilt-evidence.tar.zst",
                   "README-RECOVERY.md", "ota-lkg-promotion-record.json"):
        if target not in expected:
            raise ValueError("incomplete original/rebuilt archival evidence: " + target)
    if record.get("selections", {}).get("ROOT_MODE") != "none":
        if f"{build}-Gen{m.group(1)}-manager-evidence.tar.zst" not in expected:
            raise ValueError("enabled BakaSU Manager evidence missing")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    r = verify(a.dir, a.tag)
    print("OTA_LKG_RELEASE_COMPLETE=PASS")
    print("OTA_LKG_RELEASE_GENERATION=" + str(r["generation"]))
    print("OTA_LKG_RELEASE_SOURCE_RUN=" + str(r["source_run_id"]))


if __name__ == "__main__":
    main()
