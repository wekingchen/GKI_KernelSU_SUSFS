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
COMPAT_CUSTOM_PROOF = "compat-custom-previous-lkg.json"
ROOT = Path(__file__).resolve().parents[2]
PERSISTENT_FILES = ("persistent-candidate.json", "runtime-selected-oem-gate.json",
                    "persistent-boot-equivalence.json")


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


def env(path, *, strict=False):
    result = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        required("=" in line, "malformed env")
        k, v = line.split("=", 1)
        required(re.fullmatch(r"[A-Z0-9_]+", k) is not None and k not in result,
                 "bad/duplicate env field: " + k)
        # Metadata is parsed as inert text, never shell-executed: timestamps,
        # comma-separated feature lists and other documented values are valid.
        # Source pins remain a much narrower input class.
        if strict:
            required(re.fullmatch(r"[A-Za-z0-9_./+-]*", v) is not None,
                     "unsafe pinned value " + k)
        result[k] = v
    return result


def identify(folder, run_id, source_sha):
    folder = Path(folder)
    rec = load(folder / "verified-baseline.json")
    fix = load(folder / "fixture.json")
    abi = load(folder / "ota-custom-abi-report.json")
    md = env(folder / "build-metadata.txt")
    pins = env(folder / "locked-upstreams.env", strict=True)
    build, release = rec.get("stock_build"), rec.get("kernel_release")
    required(isinstance(build, str) and BUILD.fullmatch(build), "bad OS build")
    required(isinstance(release, str) and RELEASE.fullmatch(release), "bad kernel release")
    compat = rec.get("status") == "HUMAN_ATTESTED_COMPAT_BASELINE_BOOTED"
    compat_custom = compat and (folder / COMPAT_CUSTOM_PROOF).is_file()
    required(compat or not (folder / COMPAT_CUSTOM_PROOF).exists(),
             "compat-custom proof on non-compat baseline")
    if compat:
        required(rec.get("schema") == 2 and rec.get("device") == "pandora"
                 and rec.get("next_stage") == "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION_NONFLASH"
                 and rec.get("safe_to_flash") is False
                 and rec.get("persistent_flash") is False
                 and rec.get("full_parity_lkg_promoted") is False,
                 "unverified compatibility GKI base")
        required(rec.get("observed_build") == build and rec.get("observed_uname") == release,
                 "compatibility baseline human report mismatch")
        required(rec.get("compatibility_kind") == "PANDORA_RUST_BINDER_EEXIST_SHIM"
                 and rec.get("compatibility_parameter") == "pandora_rust_binder_eexist=1",
                 "wrong compatibility baseline kind")
        required(fix.get("schema") == 2 and fix.get("safe_to_flash") is False
                 and fix.get("stock_build") == build
                 and fix.get("tested_boot_sha256") == rec.get("compatibility_boot_sha256")
                 and fix.get("stock_input_sha256") == rec.get("stock_input_sha256")
                 and fix.get("baseline_kernel_sha256") == rec.get("compatibility_image_sha256")
                 and fix.get("compatibility_kind") == rec.get("compatibility_kind"),
                 "wrong compatibility boot fixture")
        required(abi.get("gate") == "PASS" and abi.get("compatibility_baseline") is True
                 and abi.get("safe_to_flash") is False
                 and abi.get("full_parity_lkg_promoted") is False
                 and abi.get("missing_or_crc_changed_total") == 0
                 and abi.get("build") == build and abi.get("kernel_release") == release
                 and abi.get("source_commit") == rec.get("candidate_gki_commit")
                 and abi.get("baseline_symvers_sha256") == rec.get("module_symvers_sha256")
                 and abi.get("feature_symvers_sha256") == sha(folder / "Module.symvers"),
                 "compatibility custom core ABI no longer matches OTA source")
        if compat_custom:
            # A previously verified LKG proves the C Binder / EEXIST mechanism
            # and OEM ABI only. The new Image needs its own real-device attestation.
            previous = load(folder / COMPAT_CUSTOM_PROOF)
            live = load(ROOT / ".github/config/ota-lkg-current.json")
            previous_gen = previous.get("generation")
            archive = ROOT / ".github/config/ota-lkg-history" / f"gen{previous_gen}.json"
            required(previous == live or (archive.is_file() and previous == load(archive)),
                     "previous LKG proof is not in trusted pointer/history")
            evidence = ROOT / ".github/config/ota-verified" / build
            persistent = load(evidence / "persistent-candidate.json")
            runtime = load(evidence / "runtime-selected-oem-gate.json")
            persistent_boot = load(evidence / "persistent-boot-equivalence.json")
            source_lkg = previous.get("source_run_id")
            source_image = previous.get("image_sha256")
            required(previous.get("schema") == 1
                     and previous.get("status") == "USER_PROMOTED_OTA_LKG"
                     and previous.get("attestation") ==
                     "USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF"
                     and isinstance(previous_gen, int) and previous_gen >= 6
                     and previous.get("stock_build") == build
                     and previous.get("kernel_release") == release
                     and previous.get("gki_commit") == rec.get("candidate_gki_commit")
                     and source_lkg != int(run_id)
                     and previous.get("reproduction", {}).get("symvers_sha256") == sha(folder / "Module.symvers")
                     and persistent.get("status") == "PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY"
                     and persistent.get("feature_workflow_run_id") == source_lkg
                     and persistent.get("feature_image_sha256") == source_image
                     and persistent.get("actual_persistent_install_verified") is True
                     and persistent.get("lkg_promotion") is True
                     and runtime.get("status") == "PASS_RUNTIME_SELECTED_EXACT_OS406"
                     and runtime.get("feature_workflow_run_id") == source_lkg
                     and runtime.get("feature_image_sha256") == source_image
                     and runtime.get("feature_module_symvers_sha256") == sha(folder / "Module.symvers")
                     and runtime.get("unresolved_kernel_imports") == 0
                     and runtime.get("ambiguous_providers") == 0
                     and runtime.get("crc_mismatches") == 0
                     and runtime.get("failed_modules") == 0
                     and persistent_boot.get("status") == "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37"
                     and persistent_boot.get("feature_workflow_run_id") == source_lkg
                     and persistent_boot.get("feature_image_sha256") == source_image
                     and md.get("PANDORA_RUST_BINDER_EEXIST_SHIM") == "1"
                     and md.get("COMPATIBILITY_BASELINE_KIND") == "PANDORA_RUST_BINDER_EEXIST_SHIM",
                     "COMPAT-CUSTOM requires same-OTA trusted persistent LKG, GKI and OEM ABI")
        else:
            persistent = load(folder / "persistent-candidate.json")
            runtime = load(folder / "runtime-selected-oem-gate.json")
            persistent_boot = load(folder / "persistent-boot-equivalence.json")
            required(persistent.get("status") == "PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY"
                     and persistent.get("actual_persistent_install_verified") is True
                     and persistent.get("lkg_promotion") is True
                     and persistent.get("feature_workflow_run_id") == int(run_id)
                     and persistent.get("feature_image_sha256") == sha(folder / "Image"),
                     "persistent candidate lacks exact two-reboot proof")
            required(runtime.get("status") == "PASS_RUNTIME_SELECTED_EXACT_OS406"
                     and runtime.get("feature_workflow_run_id") == int(run_id)
                     and runtime.get("feature_image_sha256") == sha(folder / "Image")
                     and runtime.get("unresolved_kernel_imports") == 0
                     and runtime.get("ambiguous_providers") == 0
                     and runtime.get("crc_mismatches") == 0
                     and runtime.get("failed_modules") == 0
                     and runtime.get("actual_persistent_install_verified") is True
                     and runtime.get("lkg_promotion") is True,
                     "runtime-selected OEM gate is not persistent-LKG ready")
            required(persistent_boot.get("status") == "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37"
                     and persistent_boot.get("feature_workflow_run_id") == int(run_id)
                     and persistent_boot.get("feature_image_sha256") == sha(folder / "Image")
                     and persistent_boot.get("actual_persistent_install_verified") is True
                     and persistent_boot.get("lkg_promotion") is True,
                     "persistent boot equivalence is not LKG ready")
    else:
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
    enabled = {"BAKASU": md.get("ROOT_MODE") != "none",
               "SUSFS": md.get("ROOT_MODE") == "bakasu-susfs",
               "NOMOUNT": md.get("USE_NOMOUNT") == "1",
               "DROIDSPACES": md.get("DROIDSPACES_ENABLED") == "1"}
    for c, is_on in enabled.items():
        if is_on:
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
    zips = (list(folder.glob("*-PERSISTENT-CANDIDATE-AnyKernel3.zip"))
            if compat and not compat_custom else list(folder.glob("*-UNVERIFIED-AnyKernel3.zip")))
    required(len(boots) == len(zips) == 1, "must have exactly one boot and one AnyKernel3")
    boot, zipfile = boots[0], zips[0]
    if compat and not compat_custom:
        required(f"pandora-{build}-CUSTOM-run-{run_id}-" in boot.name
                 and zipfile.name == "Xiaomi17Pro-pandora-OS4.0.6.0-run37-PERSISTENT-CANDIDATE-AnyKernel3.zip",
                 "wrong persistent compatibility package identity")
        required(sha(zipfile) == persistent.get("package_sha256"),
                 "persistent AnyKernel3 hash differs from two-reboot evidence")
    elif compat_custom:
        required(f"pandora-{build}-CUSTOM-run-{run_id}-" in boot.name
                 and zipfile.name == f"Xiaomi17Pro-pandora-{build}-COMPAT-CUSTOM-run-{run_id}-UNVERIFIED-AnyKernel3.zip",
                 "wrong exact COMPAT-CUSTOM package identity")
    else:
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
        if compat:
            cmd.append("--fastboot-boot-only-allow-growth")
        process = run(cmd, capture_output=True, text=True)
        required(process.returncode == 0,
                 "source boot cannot be reproduced from same-OTA fixture: " + process.stderr[-500:])
    hashes = {p.name: sha(p) for p in (folder / n for n in FILES)}
    if compat_custom:
        hashes[COMPAT_CUSTOM_PROOF] = sha(folder / COMPAT_CUSTOM_PROOF)
    elif compat:
        for name in PERSISTENT_FILES:
            hashes[name] = sha(folder / name)
    if (folder / "image-reproducibility.env").exists():
        hashes["image-reproducibility.env"] = sha(folder / "image-reproducibility.env")
    hashes[boot.name] = sha(boot)
    hashes[zipfile.name] = sha(zipfile)
    manifest = {
        "schema": 1, "kind": ("PANDORA_OS4_OTA_COMPAT_CUSTOM_SOURCE" if compat_custom else
                               "PANDORA_OS4_OTA_COMPAT_PERSISTENT_SOURCE" if compat else
                               "PANDORA_OS4_OTA_CUSTOM_SOURCE"),
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
        "real_device_feature_test": ("TWO_PERSISTENT_REBOOTS_PASS" if compat and not compat_custom
                                     else "USER_ATTESTED_AT_PROMOTION" if compat_custom
                                     else "NOT_ATTESTED_AT_BUILD_TIME"),
        "persistent_compatibility_source": compat and not compat_custom,
        "compat_custom_promotion": compat_custom,
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


def promotion_record(source, rebuilt, current, promotion_run_id, note, *, legacy_generation=3):
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
        required(isinstance(legacy_generation, int) and 3 <= legacy_generation <= 100000,
                 "invalid existing R62 LKG generation")
        gen = legacy_generation + 1  # Existing R62 can itself advance before the first OTA.
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
    promote.add_argument("--legacy-current", type=Path, required=True)
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
        # Parse the historical R62 env as inert data, not shell code: it
        # legitimately contains timestamps and user-readable punctuation.
        # Only the numeric generation is used and validated strictly below.
        legacy = env(args.legacy_current)
        required(re.fullmatch(r"[1-9][0-9]*", legacy.get("LKG_PROMOTION_GENERATION", "")) is not None,
                 "missing trusted legacy LKG generation")
        legacy_generation = int(legacy["LKG_PROMOTION_GENERATION"])
        result = promotion_record(source, rebuilt, current,
                                  args.promotion_run_id, args.note,
                                  legacy_generation=legacy_generation)
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
