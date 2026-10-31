#!/usr/bin/env python3
"""Select a human-verified OTA for OS4 custom builds, never silently downgrade."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

BUILD = re.compile(r"^OS[0-9]+\.[0-9.]+[A-Z0-9]+$")
RELEASE = re.compile(r"^(6\.12\.[0-9]+)-android16-6-[A-Za-z0-9_.-]+$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
TAG = re.compile(r"^android16-6\.12-[0-9]{4}-[0-9]{2}_r[1-9][0-9]*$")


def fail(message):
    raise SystemExit("ERROR: " + message)


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("expected JSON object: " + str(path))
    return value


def h(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def keys_equal(a, b, key):
    if a.get(key) != b.get(key):
        fail("identity mismatch: " + key)


def verified(record, fixture):
    if record.get("schema") != 1 or record.get("status") != "HUMAN_ATTESTED_BASELINE_BOOTED":
        fail("no accepted human boot attestation")
    if record.get("next_stage") != "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION":
        fail("candidate is not allowed for feature development")
    if record.get("verification_mode") != "USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF":
        fail("unexpected verification evidence mode")
    if record.get("safe_to_flash") is not False or record.get("full_parity_lkg_promoted") is not False:
        fail("verified GKI baseline is not persistent or a feature LKG")
    build = record.get("stock_build", "")
    if not BUILD.fullmatch(build):
        fail("unexpected build identity")
    uname = record.get("kernel_release", "")
    if not RELEASE.fullmatch(uname):
        fail("unsupported kernel/KMI; needs new implementation")
    if record.get("observed_build") != build or record.get("observed_uname") != uname:
        fail("reported true-device build/uname mismatch")
    for field in ("stock_input_sha256", "stock_boot_sha256", "candidate_image_sha256",
                  "module_symvers_sha256", "candidate_boot_sha256"):
        if not SHA64.fullmatch(record.get(field, "")):
            fail("invalid recorded hash: " + field)
    if not SHA40.fullmatch(record.get("candidate_gki_commit", "")):
        fail("GKI commit not pinned")
    if not isinstance(record.get("stock_release_asset_id"), int) or record["stock_release_asset_id"] < 1:
        fail("missing stock Release asset ID")
    if fixture.get("schema") != 2 or fixture.get("safe_to_flash") is not False:
        fail("not a safe schema2 OTA fixture")
    for a, b in (
        ("stock_build", "stock_build"),
        ("stock_boot_sha256", "stock_boot_sha256"),
        ("stock_input_sha256", "stock_input_sha256"),
        ("tested_boot_sha256", "candidate_boot_sha256"),
        ("baseline_kernel_sha256", "candidate_image_sha256"),
    ):
        if fixture.get(a) != record.get(b):
            fail("fixture and user verification differ: " + a)
    return build, uname


def pointer_check(pointer, record, fixture):
    build, uname = verified(record, fixture)
    if pointer.get("schema") != 1 or pointer.get("status") != "VERIFIED_OTA_DEVELOPMENT_ONLY":
        fail("invalid current OTA development pointer")
    expected = {
        "build": build, "kernel_release": uname,
        "stock_input_sha256": record["stock_input_sha256"],
        "stock_release_asset_id": record["stock_release_asset_id"],
        "candidate_gki_commit": record["candidate_gki_commit"],
        "candidate_boot_sha256": record["candidate_boot_sha256"],
        "verification_run_id": record["verification_run_id"],
        "fixture_path": f".github/config/ota-verified/{build}/fixture.json",
        "record_path": f".github/config/ota-verified/{build}/verification.json",
        "full_parity_lkg_promoted": False,
    }
    for k, v in expected.items():
        if pointer.get(k) != v:
            fail("development pointer does not match its source: " + k)
    return build, uname


def project_paths(pointer, root):
    for k in ("record_path", "fixture_path"):
        value = pointer.get(k, "")
        if not isinstance(value, str) or ".." in value or value.startswith("/"):
            fail("unsafe path in pointer: " + k)
        if not re.fullmatch(r"\.github/config/ota-verified/OS[0-9]+\.[0-9.]+[A-Z0-9]+/(verification|fixture)\.json", value):
            fail("unexpected versioned path: " + k)
    return load(root / pointer["record_path"]), load(root / pointer["fixture_path"])


def stock_check(stock, pointer, record, fixture):
    build, uname = pointer_check(pointer, record, fixture)
    if stock.get("status") != "NEW_OTA_CANDIDATE":
        fail("current stock input is not an OTA candidate")
    if stock.get("kernel_marker_verified") is not True or stock.get("may_build_gki_candidate") is not True:
        fail("new OTA identity not verified")
    expected = {
        "device": "pandora", "build": build, "uname": uname,
        "ota_source_id": record["stock_input_sha256"],
        "stock_boot_sha256": record["stock_boot_sha256"],
        "github_asset_id": str(record["stock_release_asset_id"]),
    }
    for k, v in expected.items():
        if str(stock.get(k, "")) != str(v):
            fail("stock Release no longer matches verified development target: " + k)


def cmd_create(a):
    record = load(a.record)
    fixture = load(a.fixture)
    build, uname = verified(record, fixture)
    if a.record != Path(f".github/config/ota-verified/{build}/verification.json"):
        fail("verification record must be in its version directory")
    if a.fixture != Path(f".github/config/ota-verified/{build}/fixture.json"):
        fail("fixture must be in its version directory")
    pointer = {
        "schema": 1,
        "status": "VERIFIED_OTA_DEVELOPMENT_ONLY",
        "build": build,
        "kernel_release": uname,
        "stock_input_sha256": record["stock_input_sha256"],
        "stock_release_asset_id": record["stock_release_asset_id"],
        "candidate_gki_commit": record["candidate_gki_commit"],
        "candidate_boot_sha256": record["candidate_boot_sha256"],
        "verification_run_id": record["verification_run_id"],
        "fixture_path": a.fixture.as_posix(),
        "record_path": a.record.as_posix(),
        "full_parity_lkg_promoted": False,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DEV_BASELINE_UPDATED_NOT_LKG=" + build)


def cmd_select(a):
    stock = load(a.stock_report)
    mode = "legacy"
    build = stock.get("build", "")
    if a.pointer.exists():
        pointer = load(a.pointer)
        record, fixture = project_paths(pointer, a.root)
        stock_check(stock, pointer, record, fixture)
        mode = "ota"
        build = pointer["build"]
    elif stock.get("status") != "SAME_PINNED_BUILD":
        fail("new OTA stock uploaded but not real-device verified: refusing old R62 fallback")
    if not BUILD.fullmatch(build):
        fail("invalid selected build")
    if mode == "legacy" and build != "OS4.0.5.0.XBLCNXM":
        fail("legacy mode cannot build a different HyperOS version")
    a.output.write_text(f"mode={mode}\nbuild={build}\n", encoding="utf-8")
    print(f"CUSTOM_BUILD_MODE={mode} BUILD={build}")


def cmd_prepare(a):
    pointer = load(a.pointer)
    record, fixture = project_paths(pointer, a.root)
    stock_check(load(a.stock_report), pointer, record, fixture)
    build = pointer["build"]
    cd = a.candidate_dir
    for file in ("Image", "Module.symvers", "final.config", "build-metadata.txt",
                 "locked-candidate.env", "gki-candidate.json", "stock-report.json"):
        if not (cd / file).is_file() or (cd / file).stat().st_size == 0:
            fail("missing permanent OTA baseline input: " + file)
    if h(cd / "Image") != record["candidate_image_sha256"]:
        fail("candidate Image changed since human verification")
    if h(cd / "Module.symvers") != record["module_symvers_sha256"]:
        fail("candidate Module.symvers changed since human verification")
    gki = load(cd / "gki-candidate.json")
    original_stock = load(cd / "stock-report.json")
    if gki.get("candidate_commit") != record["candidate_gki_commit"]:
        fail("candidate GKI commit changed")
    for key in ("ota_source_id", "stock_boot_sha256", "build", "uname"):
        if original_stock.get(key) != load(a.stock_report).get(key):
            fail("permanent candidate refers to a different stock ZIP: " + key)
    env = {}
    for line in (cd / "locked-candidate.env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k in env:
                fail("duplicate locked candidate field")
            env[k] = v.strip("'\"")
    tag = env.get("OTA_GKI_TAG", "")
    commit = env.get("OTA_GKI_COMMIT", "")
    kernel_version = RELEASE.fullmatch(pointer["kernel_release"]).group(1)
    if not TAG.fullmatch(tag) or commit != record["candidate_gki_commit"]:
        fail("GKI release tag/commit in lock file is invalid")
    if env.get("OTA_KERNEL_VERSION") != kernel_version or env.get("OTA_KMI") != "android16-6":
        fail("GKI family/KMI changed")
    if env.get("OTA_BUILD") != build or env.get("OTA_INPUT_SHA256") != pointer["stock_input_sha256"]:
        fail("locked OTA build/input mismatch")
    md = {}
    for line in (cd / "build-metadata.txt").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            md[k] = v
    if (md.get("SOURCE_GKI_COMMIT") != commit or md.get("SOURCE_GKI_TAG") != tag
        or md.get("KERNEL_RELEASE") != pointer["kernel_release"]
        or md.get("IMAGE_SHA256") != record["candidate_image_sha256"]
        or md.get("SYMVERS_SHA256") != record["module_symvers_sha256"]):
        fail("permanent GKI build metadata differs from verification")
    # All values are validated and shell-quoted; no arbitrary source code from ZIP
    # or user-controlled fields is allowed into this Bash env file.
    values = {
        "XIAOMI_OS4_NEW_OTA": "1",
        "OS4_SYSTEM_BUILD": build,
        "OS4_KERNEL_VERSION": kernel_version,
        "OS4_STOCK_KERNEL_RELEASE": pointer["kernel_release"],
        "OS4_STOCK_KMI": "android16-6",
        "OS4_KMI_GENERATION": "6",
        "OS4_GKI_TAG": tag,
        "OS4_GKI_COMMON_COMMIT": commit,
        "OS4_GKI_EXPECTED_CLANG": "r536225",
    }
    for k, v in values.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", v):
            fail("unsafe GKI override: " + k)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    print("VERIFIED_OTA_SOURCE_LOCK=PASS")
    print("CUSTOM_BASELINE=" + build)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create")
    create.add_argument("--record", type=Path, required=True)
    create.add_argument("--fixture", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    select = sub.add_parser("select")
    select.add_argument("--stock-report", type=Path, required=True)
    select.add_argument("--pointer", type=Path, default=Path(".github/config/ota-development-current.json"))
    select.add_argument("--root", type=Path, default=Path("."))
    select.add_argument("--output", type=Path, required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--stock-report", type=Path, required=True)
    prep.add_argument("--pointer", type=Path, default=Path(".github/config/ota-development-current.json"))
    prep.add_argument("--root", type=Path, default=Path("."))
    prep.add_argument("--candidate-dir", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    {"create": cmd_create, "select": cmd_select, "prepare": cmd_prepare}[args.cmd](args)


if __name__ == "__main__":
    main()
