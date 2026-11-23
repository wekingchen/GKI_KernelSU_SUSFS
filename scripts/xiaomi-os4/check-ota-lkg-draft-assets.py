#!/usr/bin/env python3
"""Validate exact draft Release asset identities before authenticated ID downloads.

Unlike the release-by-tag endpoint, numeric release IDs expose the owner's
unpublished drafts. This produces only inert, validated TSV records.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TAG = re.compile(r"pandora-os4-lkg-gen([1-9][0-9]*)\Z")
BUILD = re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
SHA = re.compile(r"sha256:([a-f0-9]{64})\Z")


def verify_assets(release: dict, tag: str, build: str) -> list[tuple[int, str, str, int]]:
    m = TAG.fullmatch(tag)
    if not m or not BUILD.fullmatch(build):
        raise ValueError("invalid draft tag or OTA build")
    if (release.get("tag_name") != tag or release.get("draft") is not True
            or not isinstance(release.get("id"), int) or release["id"] < 1):
        raise ValueError("not the exact unpublished draft Release")
    gen = m.group(1)
    stem = f"{build}-Gen{gen}-"
    expected = {
        stem + "original-evidence.tar.zst",
        stem + "rebuilt-evidence.tar.zst",
        stem + "ORIGINAL-USER-ATTESTED-boot.img",
        stem + "ORIGINAL-USER-ATTESTED-AnyKernel3.zip",
        stem + "REBUILT-CI-ONLY-boot.img",
        stem + "REBUILT-CI-ONLY-AnyKernel3.zip",
        "README-RECOVERY.md",
        "ota-lkg-promotion-record.json",
        f"SHA256SUMS-{tag}.txt",
    }
    optional_manager = stem + "manager-evidence.tar.zst"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("draft assets missing")
    names = [x.get("name") for x in assets if isinstance(x, dict)]
    if len(names) != len(assets) or len(set(names)) != len(names):
        raise ValueError("duplicate or malformed draft asset")
    actual = set(names)
    if actual != expected and actual != expected | {optional_manager}:
        raise ValueError("incomplete or unexpected draft asset set")
    rows = []
    ids = set()
    for asset in assets:
        aid = asset.get("id")
        name = asset["name"]
        size = asset.get("size")
        digest = SHA.fullmatch(asset.get("digest") or "")
        if (not isinstance(aid, int) or isinstance(aid, bool) or aid <= 0
                or aid in ids or asset.get("state") != "uploaded"
                or not isinstance(size, int) or isinstance(size, bool)
                or size <= 0 or size > 1024 * 1024 * 1024
                or digest is None):
            raise ValueError("invalid asset ID, state, size, or SHA256: " + name)
        ids.add(aid)
        rows.append((aid, name, digest.group(1), size))
    return sorted(rows, key=lambda x: x[1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--release", required=True, type=Path)
    p.add_argument("--tag", required=True)
    p.add_argument("--build", required=True)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    rows = verify_assets(json.loads(a.release.read_text()),
                         a.tag, a.build)
    a.output.write_text("".join(f"{aid}\t{name}\t{digest}\t{size}\n"
                                for aid, name, digest, size in rows))
    print(f"LKG_DRAFT_ASSET_METADATA=PASS count={len(rows)}")


if __name__ == "__main__":
    main()
