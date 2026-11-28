#!/usr/bin/env python3
"""Prepare the real-device-tested pandora OS4.0.6 EEXIST compatibility baseline.

This is a development-only source lock. It never upgrades the formal OEM ABI
gate and never authorizes persistent flashing.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
from pathlib import Path

BUILD = "OS4.0.6.0.XBLCNXM"
BUILD_408 = "OS4.0.8.0.XBLCNXM"
RELEASE = "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
GKI_TAG = "android16-6.12-2026-03_r74"
GKI_COMMIT = "b1d12d482d767c50cb792d988e4479d3f75c342a"
GKI_SELECTION = "SAME_PATCH_LATEST_OFFICIAL_GKI_CANDIDATE"
COMPAT = "PANDORA_RUST_BINDER_EEXIST_SHIM"
PARAM = "pandora_rust_binder_eexist=1"
PATCH_SHA = "5aab8a0a41369829707d6ea5ade437bc91a75dda4a5ac1fb6b1cb60158bef5ee"
BOOT_MAGIC = b"ANDROID!"
PAGE = 4096


def fail(msg: str):
    raise SystemExit("ERROR: " + msg)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("expected JSON object: " + str(path))
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def req(obj: dict, key: str, expected):
    if obj.get(key) != expected:
        fail(f"{key} mismatch: {obj.get(key)!r} != {expected!r}")


def validate_record(rec: dict, build=BUILD):
    req(rec, "schema", 2)
    req(rec, "status", "HUMAN_ATTESTED_COMPAT_BASELINE_BOOTED")
    req(rec, "verification_mode", "USER_ATTESTATION_PLUS_READ_ONLY_RUNTIME_EVIDENCE")
    req(rec, "device", "pandora")
    req(rec, "stock_build", build)
    req(rec, "observed_build", build)
    req(rec, "kernel_release", RELEASE)
    req(rec, "observed_uname", RELEASE)
    req(rec, "candidate_gki_tag", GKI_TAG)
    req(rec, "candidate_gki_commit", GKI_COMMIT)
    req(rec, "candidate_selection_reason", GKI_SELECTION)
    req(rec, "compatibility_kind", COMPAT)
    req(rec, "compatibility_parameter", PARAM)
    req(rec, "compatibility_patch_sha256", PATCH_SHA)
    req(rec, "next_stage", "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION_NONFLASH")
    req(rec, "formal_oem_gate", "BLOCKED")
    req(rec, "safe_to_flash", False)
    req(rec, "persistent_flash", False)
    req(rec, "full_parity_lkg_promoted", False)
    runtime = rec.get("runtime")
    if not isinstance(runtime, dict):
        fail("missing runtime evidence")
    if runtime.get("boot_completed") is not True:
        fail("compatibility baseline was not observed boot-complete")
    if build == BUILD and (runtime.get("rust_binder_loaded") is not False or runtime.get("rust_binder_initstate") != "ABSENT"):
        fail("rust_binder suppression runtime evidence missing")
    if runtime.get("binder_activity_service") != "found" or runtime.get("binder_package_service") != "found":
        fail("Binder liveness evidence missing")
    if build == BUILD and runtime.get("loaded_vendor_memory_stack") != ["node_cache", "zram", "zsmalloc"]:
        fail("vendor memory-stack evidence drift")


def validate_fixture(rec: dict, fx: dict, build=BUILD):
    req(fx, "schema", 2)
    req(fx, "safe_to_flash", False)
    req(fx, "stock_build", build)
    req(fx, "stock_input_sha256", rec["stock_input_sha256"])
    req(fx, "stock_boot_sha256", rec["stock_boot_sha256"])
    req(fx, "baseline_kernel_sha256", rec["compatibility_image_sha256"])
    req(fx, "tested_boot_sha256", rec["compatibility_boot_sha256"])
    req(fx, "compatibility_kind", COMPAT)
    req(fx, "compatibility_parameter", PARAM)
    req(fx, "shim_patch_sha256", PATCH_SHA)
    req(fx, "formal_oem_gate", "BLOCKED")
    if fx.get("header_version") != 4 or fx.get("header_size") != 1584:
        fail("compat fixture is not boot v4")
    if fx.get("ramdisk_size") != 0 or fx.get("signature_size") != 0:
        fail("unexpected ramdisk/signature in compatibility fixture")
    if not isinstance(fx.get("boot_size"), int) or fx["boot_size"] <= PAGE:
        fail("invalid compatibility boot size")
    try:
        if "header_v4" in fx:
            hv4 = fx["header_v4"]
            if not isinstance(hv4, dict) or hv4.get("reserved") != [0, 0, 0, 0]:
                fail("invalid structured compatibility boot-v4 header")
            header = bytearray(PAGE)
            header[:8] = BOOT_MAGIC
            struct.pack_into("<I", header, 8, fx.get("kernel_size", 0))
            struct.pack_into("<I", header, 12, fx.get("ramdisk_size", 0))
            struct.pack_into("<I", header, 16, hv4.get("os_version", -1))
            struct.pack_into("<I", header, 20, 1584)
            struct.pack_into("<4I", header, 24, *hv4["reserved"])
            struct.pack_into("<I", header, 40, 4)
            cmd = hv4.get("cmdline", "").encode("ascii", "strict")
            if not cmd or len(cmd) + 1 > 1536:
                fail("invalid structured compatibility cmdline")
            header[44:44+len(cmd)] = cmd
            struct.pack_into("<I", header, 1580, fx.get("signature_size", 0))
            header = bytes(header)
        elif "header_struct_b64" in fx:
            header_struct = base64.b64decode(fx["header_struct_b64"], validate=True)
            if len(header_struct) != 1584:
                fail("invalid compatibility boot-v4 header struct length")
            header = header_struct + b"\0" * (PAGE - len(header_struct))
        else:
            header = base64.b64decode(fx["header_page_b64"], validate=True)
    except Exception as exc:
        fail("invalid compatibility header: " + str(exc))
    if len(header) != PAGE or header[:8] != BOOT_MAGIC:
        fail("invalid compatibility boot header")
    cmdline = header[44:44+1536].split(b"\0", 1)[0].decode("ascii", "strict").split()
    if PARAM not in cmdline:
        fail("compatibility parameter missing from tested fixture")
    black = [x for x in cmdline if x.startswith("module_blacklist=")]
    if len(black) != 1 or "kernelsu" not in black[0].split("=", 1)[1].split(","):
        fail("KernelSU LKM guard missing from tested fixture")
    if "rust_binder" in black[0].split("=", 1)[1].split(","):
        fail("tested compatibility fixture must not blacklist rust_binder")


def validate_candidate(rec: dict, candidate: Path, build=BUILD):
    required = [
        "Image", "Module.symvers", "gki-candidate.json", "stock-report.json",
        "locked-candidate.env", "build-metadata.txt",
    ]
    for name in required:
        p = candidate / name
        if not p.is_file() or p.stat().st_size == 0:
            fail("missing permanent candidate input: " + name)
    if sha(candidate / "Image") != rec["candidate_gki_image_sha256"]:
        fail("unmodified GKI candidate Image drift")
    if sha(candidate / "Module.symvers") != rec["module_symvers_sha256"]:
        fail("baseline Module.symvers drift")
    gki = load(candidate / "gki-candidate.json")
    req(gki, "candidate_tag", GKI_TAG)
    req(gki, "candidate_commit", GKI_COMMIT)
    req(gki, "selection_reason", GKI_SELECTION)
    req(gki, "not_oem_source_proven", True)
    stock = load(candidate / "stock-report.json")
    req(stock, "build", build)
    req(stock, "uname", RELEASE)
    req(stock, "ota_source_id", rec["stock_input_sha256"])
    req(stock, "stock_boot_sha256", rec["stock_boot_sha256"])
    if str(stock.get("github_asset_id")) != str(rec["stock_release_asset_id"]):
        fail("stock Release asset ID drift")
    meta = dict(
        line.split("=", 1)
        for line in (candidate / "build-metadata.txt").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    for key, expected in {
        "SOURCE_GKI_TAG": GKI_TAG,
        "SOURCE_GKI_COMMIT": GKI_COMMIT,
        "SOURCE_SELECTION": GKI_SELECTION,
        "STOCK_UNAME": RELEASE,
        "KERNEL_RELEASE": RELEASE,
        "IMAGE_SHA256": rec["candidate_gki_image_sha256"],
        "SYMVERS_SHA256": rec["module_symvers_sha256"],
    }.items():
        if meta.get(key) != expected:
            fail("candidate build metadata drift: " + key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--candidate-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rec = load(args.record)
    fx = load(args.fixture)
    build = rec.get("stock_build")
    if build not in (BUILD, BUILD_408):
        fail("unsupported compatibility build")
    if build == BUILD_408:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ota_pointer", Path(__file__).with_name("ota-development-pointer.py"))
        router = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(router)
        router.verified_compatibility(rec, fx)
    validate_record(rec, build)
    validate_fixture(rec, fx, build)
    validate_candidate(rec, args.candidate_dir, build)

    values = {
        "OS4_SYSTEM_BUILD": build,
        "OS4_KERNEL_VERSION": "6.12.69",
        "OS4_STOCK_KERNEL_RELEASE": RELEASE,
        "OS4_STOCK_KMI": "android16-6",
        "OS4_KMI_GENERATION": "6",
        "OS4_GKI_TAG": GKI_TAG,
        "OS4_GKI_COMMON_COMMIT": GKI_COMMIT,
        "OS4_GKI_EXPECTED_CLANG": "r536225",
        "OS4_PANDORA_RUST_BINDER_EEXIST_SHIM": "1",
        "OS4_PANDORA_RUST_BINDER_EEXIST_PATCH_SHA256": PATCH_SHA,
        "OS4_COMPATIBILITY_BASELINE_KIND": COMPAT,
        "OS4_COMPATIBILITY_TESTED_IMAGE_SHA256": rec["compatibility_image_sha256"],
        "OS4_COMPATIBILITY_TESTED_BOOT_SHA256": rec["compatibility_boot_sha256"],
    }
    for k, v in values.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", v):
            fail("unsafe compatibility environment value: " + k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    print("PANDORA_COMPAT_BASELINE=VERIFIED_EEXIST_BOOT_ONLY " + build)
    print("FORMAL_OEM_GATE=BLOCKED")
    print("PERSISTENT_FLASH=FORBIDDEN")


if __name__ == "__main__":
    main()
