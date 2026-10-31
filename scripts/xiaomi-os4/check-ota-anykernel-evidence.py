#!/usr/bin/env python3
"""Fail-closed metadata gate for an unverified OTA custom AnyKernel3 ZIP.

The original pure GKI baseline was human-attested, NOT the modified kernel.
This validates artifact provenance, never endorses flashing the custom image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit("ERROR: OTA AnyKernel3 evidence rejected: " + message)


def document(path: Path) -> dict:
    item = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(item, dict):
        fail("expected JSON object " + str(path))
    return item


def metadata(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in entries:
            fail("duplicate metadata key: " + key)
        entries[key] = value
    return entries


def require(ok: bool, detail: str) -> None:
    if not ok:
        fail(detail)


def validate(record: dict, fixture: dict, abi: dict, meta: dict,
             image: bytes, build: str, release: str) -> None:
    require(bool(re.fullmatch(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+", build)),
            "invalid build")
    require(bool(re.fullmatch(r"6\.12\.[0-9]+-android16-6-[A-Za-z0-9_.-]+", release)),
            "unsupported GKI/KMI release")
    require(record.get("status") == "HUMAN_ATTESTED_BASELINE_BOOTED"
            and record.get("next_stage") == "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION"
            and record.get("verification_mode") == "USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF"
            and record.get("device") == "pandora"
            and record.get("safe_to_flash") is False
            and record.get("full_parity_lkg_promoted") is False,
            "pure GKI baseline not human-attested")
    require(record.get("stock_build") == build
            and record.get("kernel_release") == release
            and record.get("observed_build") == build
            and record.get("observed_uname") == release,
            "recorded OTA identity disagrees with artifact")
    require(fixture.get("schema") == 2 and fixture.get("safe_to_flash") is False
            and fixture.get("stock_build") == build
            and fixture.get("tested_boot_sha256") == record.get("candidate_boot_sha256")
            and fixture.get("stock_input_sha256") == record.get("stock_input_sha256")
            and fixture.get("baseline_kernel_sha256") == record.get("candidate_image_sha256"),
            "different/unsafe OTA fixture")
    require(abi.get("gate") == "PASS"
            and abi.get("safe_to_flash") is False
            and abi.get("full_parity_lkg_promoted") is False
            and abi.get("missing_or_crc_changed_total") == 0
            and abi.get("build") == build
            and abi.get("kernel_release") == release
            and abi.get("source_commit") == record.get("candidate_gki_commit")
            and abi.get("baseline_symvers_sha256") == record.get("module_symvers_sha256"),
            "custom kernel failed same-OTA core ABI gate")
    expected = {
        "BUILD_KIND": "OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED",
        "SYSTEM_BUILD": build,
        "STOCK_RELEASE": release,
        "KERNEL_RELEASE": release,
        "SOURCE_COMMIT": record.get("candidate_gki_commit"),
        "IMAGE_SHA256": hashlib.sha256(image).hexdigest(),
        "SYMVERS_SHA256": abi.get("feature_symvers_sha256"),
        "NEW_OTA_MODE": "1",
        "SELECTABLE_BUILD": "1",
        "FLASHABLE": "NO",
    }
    for name, value in expected.items():
        require(isinstance(value, str) and meta.get(name) == value,
                "mismatched custom kernel metadata: " + name)
    require(release.encode("ascii") in image, "Image missing expected uname marker")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--abi", type=Path, required=True)
    ap.add_argument("--metadata", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--release", required=True)
    args = ap.parse_args()
    validate(document(args.record), document(args.fixture), document(args.abi),
             metadata(args.metadata), args.image.read_bytes(), args.build, args.release)
    print("OTA_ANYKERNEL3_PROVENANCE=PASS")
    print("FEATURE_KERNEL_RUNTIME_VALIDATION=NOT_DONE")
    print("MANUAL_PERSISTENT_INSTALLATION=EXPERIMENTAL_NOT_LKG")


if __name__ == "__main__":
    main()
