#!/usr/bin/env python3
"""Finalize a *human-attested* same-OTA temporary-boot baseline.

Recreates the EXACT candidate boot from original, immutable inputs before
recording an OTA-specific fixture. This does not prove device behavior, enable
persistent flashing, or promote a Full Parity LKG.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PAGE = 4096
BUILD = re.compile(r"^OS[0-9]+\.[0-9.]+[A-Z0-9]+$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
HEX40 = re.compile(r"^[a-f0-9]{40}$")
BOOT = re.compile(r"boot(?:_[^/]*)?\.img$", re.I)


def stop(message: str) -> None:
    raise SystemExit("ERROR: " + message)


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        stop("expected JSON object: " + str(path))
    return data


def metadata(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if "=" in line and not line.startswith("#"))


def main() -> None:
    parser = argparse.ArgumentParser()
    for key in ("stock-zip", "stock-report", "gki-candidate", "abi-report",
                "metadata", "image", "testboot", "output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("source-run-id", "source-head-sha", "asset-id", "tested-sha256",
                "observed-uname", "observed-build", "actor",
                "verification-run-id", "verified-at"):
        parser.add_argument("--" + key, required=True)
    a = parser.parse_args()
    source = read_json(a.stock_report)
    gki = read_json(a.gki_candidate)
    abi = read_json(a.abi_report)
    meta = metadata(a.metadata)
    build = source.get("build", "")
    if not BUILD.fullmatch(build) or source.get("device") != "pandora":
        stop("not a pandora HyperOS OTA")
    if source.get("status") != "NEW_OTA_CANDIDATE" or source.get("kernel_marker_verified") is not True:
        stop("stock input was not a new OTA with a verified kernel marker")
    if source.get("may_build_gki_candidate") is not True or source.get("safe_to_flash") is not False:
        stop("stock input is not a no-flash GKI candidate")
    if a.observed_build != build or a.observed_uname != source.get("uname"):
        stop("actual booted build / uname does not match candidate input")
    if a.source_run_id == a.verification_run_id or not (
        a.source_run_id.isdecimal() and int(a.source_run_id) > 0
        and a.verification_run_id.isdecimal() and int(a.verification_run_id) > 0
    ):
        stop("invalid / self-referencing workflow run identity")
    if not HEX40.fullmatch(a.source_head_sha):
        stop("invalid source commit")
    if not a.asset_id.isdecimal() or str(source.get("github_asset_id")) != a.asset_id:
        stop("original Release asset identity mismatch")
    if not HEX64.fullmatch(a.tested_sha256):
        stop("invalid tested boot SHA256")
    if digest(a.stock_zip.read_bytes()) != source.get("ota_source_id"):
        stop("source xm.zip was replaced")
    if gki.get("ota_source_id") != source["ota_source_id"]:
        stop("GKI candidate source ZIP mismatch")
    if meta.get("STOCK_INPUT_SHA256") != source["ota_source_id"]:
        stop("candidate build metadata source mismatch")
    if meta.get("SOURCE_GKI_COMMIT") != gki.get("candidate_commit"):
        stop("candidate git commit mismatch")
    if meta.get("STOCK_BUILD") != build or meta.get("KERNEL_RELEASE") != source.get("uname"):
        stop("candidate build / kernel release mismatch")
    if (abi.get("eligible_for_fastboot_boot") is not True
        or abi.get("gate") != "CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        or abi.get("stock_input_sha256") != source["ota_source_id"]
        or abi.get("stock_build") != build
        or abi.get("kernel_release") != source["uname"]
        or abi.get("candidate_commit") != gki.get("candidate_commit")):
        stop("OEM static CRC/KMI gate not satisfied for exact candidate")
    image = a.image.read_bytes()
    if not image or digest(image) != meta.get("IMAGE_SHA256"):
        stop("candidate Image hash mismatch")
    tested = a.testboot.read_bytes()
    if digest(tested) != a.tested_sha256:
        stop("provided SHA256 is not the exact candidate boot in the source run")
    if not 4096 < len(tested) <= 200 * 1024 * 1024:
        stop("unexpected temporary boot length")
    if tested[:8] != b"ANDROID!":
        stop("bad Android boot magic")

    # Re-run the existing fail-closed OTA packer and require byte-for-byte
    # equivalence, rather than trusting an artifact's filename or metadata.
    with tempfile.TemporaryDirectory() as temp:
        regenerated = Path(temp) / "independent-repacked.img"
        packer = Path(__file__).with_name("package-ota-testboot-v4.py")
        run = subprocess.run(
            [sys.executable, str(packer),
             "--stock-zip", str(a.stock_zip),
             "--stock-report", str(a.stock_report),
             "--abi-report", str(a.abi_report),
             "--metadata", str(a.metadata),
             "--candidate-image", str(a.image),
             "--output", str(regenerated)],
            capture_output=True, text=True, check=False,
        )
        if run.returncode != 0:
            stop("independent package guard failed: " + (run.stderr + run.stdout)[-800:])
        if regenerated.read_bytes() != tested:
            stop("candidate boot is not byte-identical to independent repack")
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<IIII", tested, 8)
    version = struct.unpack_from("<I", tested, 40)[0]
    signature_size = struct.unpack_from("<I", tested, 1580)[0]
    if version != 4 or header_size != 1584 or ramdisk_size != 0 or signature_size != 0:
        stop("fixture supports only zero-ramdisk, zero-signature Android boot v4")
    if kernel_size != len(image) or tested[PAGE:PAGE + kernel_size] != image:
        stop("embedded baseline Image differs from candidate")
    if tested[PAGE + kernel_size:].strip(b"\0"):
        stop("unexpected nonzero suffix in temporary boot")

    with zipfile.ZipFile(a.stock_zip) as z:
        matches = [m for m in z.infolist() if not m.is_dir()
                   and BOOT.fullmatch(m.filename.replace("\\", "/").rsplit("/", 1)[-1])]
        if len(matches) != 1 or matches[0].file_size > 200 * 1024 * 1024:
            stop("source ZIP needs exactly one bounded boot.img")
        stock_boot = z.read(matches[0])
    if digest(stock_boot) != source.get("stock_boot_sha256"):
        stop("stock boot mismatch")
    stock_kernel_size = struct.unpack_from("<I", stock_boot, 8)[0]
    if PAGE + stock_kernel_size > len(stock_boot):
        stop("stock boot kernel truncated")
    if len(stock_boot) != len(tested):
        stop("candidate boot partition size differs from same-OTA stock boot")

    fixture = {
        "schema": 2,
        "source": "pandora human-attested same-OTA GKI temporary boot",
        "stock_build": build,
        "stock_boot_sha256": digest(stock_boot),
        "stock_header_sha256": digest(stock_boot[:PAGE]),
        "stock_kernel_sha256": digest(stock_boot[PAGE:PAGE + stock_kernel_size]),
        "stock_kernel_size": stock_kernel_size,
        "stock_input_sha256": source["ota_source_id"],
        "tested_boot_sha256": digest(tested),
        "baseline_kernel_sha256": digest(image),
        "boot_size": len(tested),
        "header_version": version,
        "header_size": header_size,
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version": os_version,
        "signature_size": signature_size,
        "safe_to_flash": False,
        "header_page_b64": base64.b64encode(tested[:PAGE]).decode("ascii"),
        "ramdisk_region_b64": "",
        "suffix_b64": "",
    }
    record = {
        "schema": 1,
        "status": "HUMAN_ATTESTED_BASELINE_BOOTED",
        "next_stage": "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION",
        "device": "pandora",
        "stock_build": build,
        "kernel_release": source["uname"],
        "kmi": source["kmi"],
        "source_ota_run_id": int(a.source_run_id),
        "source_ota_head_sha": a.source_head_sha,
        "stock_release_asset_id": int(a.asset_id),
        "stock_input_sha256": source["ota_source_id"],
        "stock_boot_sha256": fixture["stock_boot_sha256"],
        "candidate_gki_commit": gki["candidate_commit"],
        "candidate_image_sha256": fixture["baseline_kernel_sha256"],
        "module_symvers_sha256": digest(a.output_dir.joinpath("Module.symvers").read_bytes()) if a.output_dir.joinpath("Module.symvers").is_file() else meta.get("SYMVERS_SHA256", ""),
        "candidate_boot_sha256": fixture["tested_boot_sha256"],
        "abi_gate": abi["gate"],
        "abi_modules_checked": abi.get("module_count"),
        "observed_device": "pandora",
        "observed_build": a.observed_build,
        "observed_uname": a.observed_uname,
        "observed_boot_completed": "1",
        "modules_basic_check": "PASS_HUMAN_ATTESTED",
        "verification_mode": "USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF",
        "verified_by": a.actor,
        "verified_at_utc": a.verified_at,
        "verification_run_id": int(a.verification_run_id),
        "fixture_schema": 2,
        "safe_to_flash": False,
        "full_parity_lkg_promoted": False,
    }

    # Rebuild the exact observed candidate with the fixture intended for
    # future OTA feature kernels, before creating any tracked record.
    a.output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = a.output_dir / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    with tempfile.TemporaryDirectory() as temp:
        rebuilt = Path(temp) / "reconstructed.img"
        repack = Path(__file__).with_name("repack-fastboot-boot-v4-from-fixture.py")
        result = subprocess.run(
            [sys.executable, str(repack), str(fixture_path), str(a.image),
             str(rebuilt), "--expected-image-sha256", digest(image),
             "--expected-release", a.observed_uname, "--expected-build", build,
             "--expected-output-sha256", digest(tested)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode or rebuilt.read_bytes() != tested:
            fixture_path.unlink(missing_ok=True)
            stop("fixture round-trip test failed: " + (result.stderr + result.stdout)[-700:])
    (a.output_dir / "verification.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("VERIFIED_BASELINE=HUMAN_ATTESTED_AND_BYTE_REPRODUCED")
    print("READY_FOR_FEATURE_ADAPTATION=YES_NOT_YET_BUILT")
    print("FLASHABLE=NO")
    print("GEN3_LKG_UNCHANGED=YES")


if __name__ == "__main__":
    main()
