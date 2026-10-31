#!/usr/bin/env python3
"""Version-scoped Xiaomi pandora OTA LKG evidence gate.

No phone is controlled here. Real-device stable use is explicitly attested by
the owner; CI verifies provenance, immutability, source and rebuild equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{64}\Z")
GIT = re.compile(r"[a-f0-9]{40}\Z")
BUILD = re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
RELEASE = re.compile(r"6\.12\.[0-9]+-android16-6-[A-Za-z0-9_.-]+\Z")
COMPONENTS = ("BAKASU", "SUSFS", "NOMOUNT", "DROIDSPACES", "NTSYNC", "BBG", "REKERNEL")
FLAGS = ("ROOT_MODE", "SUSFS_EXTRA_FEATURES", "USE_NOMOUNT", "DROIDSPACES_ENABLED",
         "USE_NTSYNC", "USE_BBG", "USE_REKERNEL", "USE_NETWORKING", "USE_CVE")
FILES = ("Image", "Module.symvers", "final.config", "build-metadata.txt",
         "ota-custom-abi-report.json", "verified-baseline.json", "fixture.json",
         "locked-upstreams.env")


def fail(s):
    raise ValueError("OTA LKG DENIED: " + str(s))


def required(ok, message):
    if not ok:
        fail(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    x = json.loads(Path(path).read_text(encoding="utf-8"))
    required(isinstance(x, dict), "non-object JSON: " + str(path))
    return x


def env(path):
    result = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        required("=" in line, "malformed env")
        k, v = line.split("=", 1)
        required(re.fullmatch(r"[A-Z0-9_]+", k) is not None and k not in result,
                 "bad/duplicate env field: " + k)
        required(re.fullmatch(r"[A-Za-z0-9_./+-]*", v) is not None,
                 "unsafe env value " + k)
        result[k] = v
    return result


def identify(folder, run_id, source_sha):
    folder = Path(folder)
    rec = load(folder / "verified-baseline.json")
    fix = load(folder / "fixture.json")
    abi = load(folder / "ota-custom-abi-report.json")
    md = env(folder / "build-metadata.txt")
    pins = env(folder / "locked-upstreams.env")
    build, release = rec.get("stock_build"), rec.get("kernel_release")
    required(isinstance(build, str) and BUILD.fullmatch(build), "bad OS build")
    required(isinstance(release, str) and RELEASE.fullmatch(release), "bad kernel release")
    required(rec.get("device") == "pandora"
             and rec.get("status") == "HUMAN_ATTESTED_BASELINE_BOOTED"
             and rec.get("next_stage") == "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION"
             and rec.get("safe_to_flash") is False
             and rec.get("full_parity_lkg_promoted") is False, "unverified OTA GKI base")
    required(rec.get("observed_build") == build and rec.get("observed_uname") == release,
             "GKI baseline human report mismatch")
    required(fix.get("schema") == 2 and fix.get("safe_to_flash") is False
             and fix.get("stock_build") == build
             and fix.get("tested_boot_sha256") == rec.get("candidate_boot_sha256")
             and fix.get("stock_input_sha256") == rec.get("stock_input_sha256")
             and fix.get("baseline_kernel_sha256") == rec.get("candidate_image_sha256"),
             "wrong same-OTA boot fixture")
    required(abi.get("gate") == "PASS" and abi.get("safe_to_flash") is False
             and abi.get("full_parity_lkg_promoted") is False
             and abi.get("missing_or_crc_changed_total") == 0
             and abi.get("build") == build and abi.get("kernel_release") == release
             and abi.get("source_commit") == rec.get("candidate_gki_commit")
             and abi.get("baseline_symvers_sha256") == rec.get("module_symvers_sha256")
             and abi.get("feature_symvers_sha256") == sha(folder / "Module.symvers"),
             "custom core ABI no longer matches OTA source")
    for k, v in {
        "BUILD_KIND": "OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED",
        "NEW_OTA_MODE": "1", "SYSTEM_BUILD": build,
        "STOCK_RELEASE": release, "KERNEL_RELEASE": release,
        "SOURCE_COMMIT": rec.get("candidate_gki_commit"),
        "SELECTABLE_BUILD": "1", "FLASHABLE": "NO",
        "IMAGE_SHA256": sha(folder / "Image"),
        "SYMVERS_SHA256": sha(folder / "Module.symvers"),
    }.items():
        required(md.get(k) == v, "feature build metadata mismatch: " + k)
    required(re.fullmatch(r"[1-9][0-9]*", str(run_id)) is not None,
             "invalid source run ID")
    required(isinstance(source_sha, str) and GIT.fullmatch(source_sha),
             "invalid originating source commit")
    for c in COMPONENTS:
        commit = pins.get("RESOLVED_" + c + "_COMMIT")
        required(isinstance(commit, str) and GIT.fullmatch(commit),
                 "unpinned upstream: " + c)
    upstream_refs = {}
    for c in COMPONENTS:
        kind, ref = pins.get("RESOLVED_" + c + "_KIND"), pins.get("RESOLVED_" + c + "_REF")
        required(kind in ("branch", "tag") and isinstance(ref, str)
                 and re.fullmatch(r"[A-Za-z0-9._/+-]+", ref) is not None,
                 "missing pinned upstream kind/ref: " + c)
        upstream_refs[c] = {"kind": kind, "ref": ref}
    for c in ("BAKASU", "SUSFS", "NOMOUNT", "DROIDSPACES"):
        required(pins["RESOLVED_" + c + "_COMMIT"] == md.get(c + "_COMMIT"),
                 "upstream snapshot differs from actual build: " + c)
    for c, prefix in (("BAKASU", "BAKASU"), ("SUSFS", "SUSFS"),
                      ("NOMOUNT", "NOMOUNT"), ("DROIDSPACES", "DROIDSPACES"),
                      ("NTSYNC", "NTSYNC"), ("BBG", "BBG"),
                      ("REKERNEL", "REKERNEL")):
        required(md.get(prefix + "_REF_KIND") == upstream_refs[c]["kind"] and
                 md.get(prefix + "_REF") == upstream_refs[c]["ref"],
                 "upstream source kind/ref differs from the built kernel: " + c)
    for c in ("NTSYNC", "BBG", "REKERNEL"):
        switch = {"NTSYNC": "USE_NTSYNC", "BBG": "USE_BBG",
                  "REKERNEL": "USE_REKERNEL"}[c]
        if md.get(switch) == "1":
            actual = (md.get(c + "_COMMIT") or md.get("OS3_PARITY_" + c + "_COMMIT")
                      or md.get("OS3_PARITY_" + c + "_PATCH_COMMIT"))
            required(actual == pins["RESOLVED_" + c + "_COMMIT"],
                     "enabled upstream commit differs from applied extras: " + c)
    required(md.get("ROOT_MODE") in ("bakasu-susfs", "bakasu", "none"),
             "unsupported root mode")
    for k in FLAGS[1:]:
        required(md.get(k) in ("0", "1"), "missing feature selection: " + k)
    image = (folder / "Image").read_bytes()
    required(release.encode() in image, "compiled Image release marker absent")
    boots = list(folder.glob("*-UNVERIFIED-FASTBOOT-BOOT-ONLY.img"))
    zips = list(folder.glob("*-UNVERIFIED-AnyKernel3.zip"))
    required(len(boots) == len(zips) == 1, "must have exactly one boot and one AnyKernel3")
    boot, zipfile = boots[0], zips[0]
    required(f"pandora-{build}-CUSTOM-run-{run_id}-" in boot.name
             and build in zipfile.name and f"run-{run_id}-" in zipfile.name,
             "wrong build/run in package name")
    import zipfile as z
    with z.ZipFile(zipfile) as archive:
        required(archive.testzip() is None, "AnyKernel3 archive CRC error")
        required(archive.namelist().count("Image") == 1, "ZIP Image missing or duplicated")
        required(hashlib.sha256(archive.read("Image")).hexdigest() == sha(folder / "Image"),
                 "AnyKernel3 contains another kernel")
    from subprocess import run
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        output = Path(t) / "source.img"
        cmd = [sys.executable, str(Path(__file__).with_name("repack-fastboot-boot-v4-from-fixture.py")),
               str(folder / "fixture.json"), str(folder / "Image"), str(output),
               "--expected-image-sha256", sha(folder / "Image"),
               "--expected-release", release, "--expected-build", build,
               "--expected-output-sha256", sha(boot)]
        process = run(cmd, capture_output=True, text=True)
        required(process.returncode == 0,
                 "source boot cannot be reproduced from same-OTA fixture: " + process.stderr[-500:])
    hashes = {p.name: sha(p) for p in (folder / n for n in FILES)}
    if (folder / "image-reproducibility.env").exists():
        hashes["image-reproducibility.env"] = sha(folder / "image-reproducibility.env")
    hashes[boot.name] = sha(boot)
    hashes[zipfile.name] = sha(zipfile)
    manifest = {
        "schema": 1, "kind": "PANDORA_OS4_OTA_CUSTOM_SOURCE",
        "source_run_id": int(run_id), "source_head_sha": source_sha,
        "device": "pandora", "stock_build": build, "kernel_release": release,
        "stock_release_asset_id": rec.get("stock_release_asset_id"),
        "stock_input_sha256": rec.get("stock_input_sha256"),
        "gki_commit": rec.get("candidate_gki_commit"),
        "baseline_verification_run_id": rec.get("verification_run_id"),
        "image_sha256": sha(folder / "Image"),
        "boot_name": boot.name, "boot_sha256": sha(boot),
        "anykernel_name": zipfile.name, "anykernel_sha256": sha(zipfile),
        "files": dict(sorted(hashes.items())),
        "selections": {k: md[k] for k in FLAGS},
        "upstream_commits": {k: pins["RESOLVED_" + k + "_COMMIT"] for k in COMPONENTS},
        "upstream_refs": upstream_refs,
        "real_device_feature_test": "NOT_ATTESTED_AT_BUILD_TIME",
        "full_parity_lkg_promoted": False,
    }
    return manifest


def manifest_verify(folder, run_id, source_sha):
    actual = identify(folder, run_id, source_sha)
    stored = load(Path(folder) / "ota-custom-source.json")
    required(stored == actual, "source manifest changed after upload")
    return actual


def compare_rebuild(original, rebuild, manifest):
    original, rebuild = Path(original), Path(rebuild)
    for name in ("Module.symvers", "final.config"):
        required(sha(original / name) == sha(rebuild / name),
                 "rebuild bytewise changed " + name)
    src = env(original / "build-metadata.txt")
    rebuilt = env(rebuild / "build-metadata.txt")
    for key in ("SOURCE_COMMIT", "SYSTEM_BUILD", "STOCK_RELEASE", "KERNEL_RELEASE",
                "ROOT_MODE", "SUSFS_EXTRA_FEATURES", "USE_NOMOUNT",
                "DROIDSPACES_ENABLED", "USE_NTSYNC", "USE_BBG", "USE_REKERNEL",
                "USE_NETWORKING", "USE_CVE", "BAKASU_COMMIT", "SUSFS_COMMIT",
                "NOMOUNT_COMMIT", "DROIDSPACES_COMMIT",
                "BAKASU_REF_KIND", "BAKASU_REF", "SUSFS_REF_KIND", "SUSFS_REF",
                "NOMOUNT_REF_KIND", "NOMOUNT_REF", "DROIDSPACES_REF_KIND",
                "DROIDSPACES_REF", "NTSYNC_REF_KIND", "NTSYNC_REF",
                "BBG_REF_KIND", "BBG_REF", "REKERNEL_REF_KIND", "REKERNEL_REF"):
        required(src.get(key) and src[key] == rebuilt.get(key), "rebuild drift: " + key)
    source_repro = env(original / "image-reproducibility.env")
    rebuilt_repro = env(rebuild / "image-reproducibility.env")
    required(sha(original / "Image") == manifest["image_sha256"],
             "source Image hash changed")
    for key in ("IMAGE_SIZE", "NORMALIZED_IMAGE_SHA256"):
        required(source_repro.get(key) == rebuilt_repro.get(key),
                 "rebuild normalized kernel drift: " + key)
    required(rebuilt_repro["IMAGE_SHA256"] == sha(rebuild / "Image"),
             "rebuild Image manifest mismatch")
    return {"source_image_sha256": sha(original / "Image"),
            "rebuilt_image_sha256": sha(rebuild / "Image"),
            "normalized_image_sha256": source_repro["NORMALIZED_IMAGE_SHA256"],
            "symvers_sha256": sha(original / "Module.symvers"),
            "config_sha256": sha(original / "final.config"),
            "rebuild_verification": "NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS",
            "rebuild_device_tested": False}


def promotion_record(source, rebuilt, current, promotion_run_id, note):
    required(re.fullmatch(r"[1-9][0-9]*", str(promotion_run_id)) is not None,
             "invalid promoting run ID")
    previous = current or None
    if previous:
        required(previous.get("schema") == 1 and previous.get("status") == "USER_PROMOTED_OTA_LKG"
                 and isinstance(previous.get("generation"), int)
                 and previous["generation"] >= 4, "invalid previous OTA LKG pointer")
        required(previous["source_run_id"] != source["source_run_id"],
                 "source run already promoted")
        gen = previous["generation"] + 1
    else:
        gen = 4  # Existing R62 Gen 3 is maintained in its original immutable env.
    note = re.sub(r"[^A-Za-z0-9_.:+-]", "_", note)[:160] or "user-confirmed-stable"
    return {
        "schema": 1, "status": "USER_PROMOTED_OTA_LKG",
        "device": "pandora", "generation": gen,
        "stock_build": source["stock_build"],
        "kernel_release": source["kernel_release"],
        "source_run_id": source["source_run_id"],
        "source_head_sha": source["source_head_sha"],
        "promotion_run_id": int(promotion_run_id),
        "baseline_verification_run_id": source["baseline_verification_run_id"],
        "stock_input_sha256": source["stock_input_sha256"],
        "stock_release_asset_id": source["stock_release_asset_id"],
        "gki_commit": source["gki_commit"],
        "source_manifest_sha256": source["source_manifest_sha256"],
        "image_sha256": source["image_sha256"],
        "boot_sha256": source["boot_sha256"],
        "anykernel_sha256": source["anykernel_sha256"],
        "selections": source["selections"],
        "upstream_commits": source["upstream_commits"],
        "reproduction": rebuilt,
        "attestation": "USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF",
        "note": note,
        "archive_tag": f"pandora-os4-lkg-gen{gen}",
        "legacy_r62_lkg_unchanged": True,
    }


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture")
    verify = sub.add_parser("verify")
    for cmd in (capture, verify):
        cmd.add_argument("--artifact-dir", type=Path, required=True)
        cmd.add_argument("--run-id", required=True)
        cmd.add_argument("--head-sha", required=True)
    cmp = sub.add_parser("compare")
    cmp.add_argument("--source-dir", type=Path, required=True)
    cmp.add_argument("--rebuild-dir", type=Path, required=True)
    cmp.add_argument("--run-id", required=True)
    cmp.add_argument("--head-sha", required=True)
    cmp.add_argument("--output", type=Path, required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--source-dir", type=Path, required=True)
    promote.add_argument("--rebuild-report", type=Path, required=True)
    promote.add_argument("--current", type=Path, required=True)
    promote.add_argument("--run-id", required=True)
    promote.add_argument("--head-sha", required=True)
    promote.add_argument("--promotion-run-id", required=True)
    promote.add_argument("--note", default="")
    promote.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.action == "capture":
        result = identify(args.artifact_dir, args.run_id, args.head_sha)
        (args.artifact_dir / "ota-custom-source.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("OTA_CUSTOM_SOURCE_MANIFEST=PASS")
    elif args.action == "verify":
        result = manifest_verify(args.artifact_dir, args.run_id, args.head_sha)
        print("OTA_CUSTOM_SOURCE=PASS build=" + result["stock_build"])
    elif args.action == "compare":
        source = manifest_verify(args.source_dir, args.run_id, args.head_sha)
        result = compare_rebuild(args.source_dir, args.rebuild_dir, source)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("OTA_LKG_REPRODUCTION=PASS")
    else:
        source = manifest_verify(args.source_dir, args.run_id, args.head_sha)
        source["source_manifest_sha256"] = sha(args.source_dir / "ota-custom-source.json")
        rebuilt = load(args.rebuild_report)
        required(rebuilt.get("rebuild_verification") ==
                 "NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS"
                 and rebuilt.get("rebuild_device_tested") is False,
                 "rebuild lacks strict reproducibility report")
        current = load(args.current) if args.current.exists() else None
        result = promotion_record(source, rebuilt, current,
                                  args.promotion_run_id, args.note)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("OTA_LKG_GENERATION=" + str(result["generation"]))
        print("OTA_LKG_ARCHIVE_TAG=" + result["archive_tag"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
