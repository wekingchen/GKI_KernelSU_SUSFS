#!/usr/bin/env python3
"""Route one OS4 user-facing LKG promotion to exactly one verified source type.

Pure metadata classifier, never shell-executes Artifact names or release data.
All paths default fail closed; the chosen implementation still independently
re-verifies its own source and immutable provenance.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

REPO = "wekingchen/GKI_KernelSU_SUSFS"
CUSTOM = ".github/workflows/xiaomi-sm8850-os4-custom.yml"
BUILD = re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")


def fail(why: str):
    raise ValueError("LKG route denied: " + why)


def persistent_compat_ok(source_id: str, artifact_name: str, persistent: dict | None) -> bool:
    if not isinstance(persistent, dict):
        return False
    expected = {
        "status": "PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY",
        "device": "pandora",
        "stock_build": "OS4.0.6.0.XBLCNXM",
        "feature_workflow_run_id": int(source_id),
        "feature_image_sha256": "3daba0524738ab872ebf75653f25754433c36a624eb8002198440a4cb1cb1dc0",
        "runtime_selected_oem_gate": "PASS_RUNTIME_SELECTED_EXACT_OS406",
        "persistent_boot_equivalence": "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37",
        "actual_persistent_install_verified": True,
        "lkg_promotion": True,
    }
    for key, value in expected.items():
        if persistent.get(key) != value:
            return False
    if persistent.get("package_run_id") != 45105070444:
        return False
    if persistent.get("package_artifact_id") != 14787211465:
        return False
    if persistent.get("package_sha256") != "44a63799a6dce8b373181029ee2aa2c92340781713fc398c3220b482e88fde8e":
        return False
    return artifact_name == (
        "pandora-OTA-COMPAT-NONFLASH-OS4.0.6.0.XBLCNXM-run-" + str(source_id)
    )


def route(source_id: str, run: dict | None, artifacts: dict | None,
          has_ota_lkg: bool, *, repair: bool = False,
          persistent: dict | None = None) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", str(source_id)):
        fail("invalid source_run_id")
    if repair:
        return "repair"
    if not isinstance(run, dict) or not isinstance(artifacts, dict):
        fail("missing source API response")
    expected = {
        "status": "completed", "conclusion": "success",
        "event": "workflow_dispatch", "head_branch": "dev",
        "path": CUSTOM,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            fail("untrusted source run: " + key)
    if run.get("id") != int(source_id):
        fail("source run identity mismatch")
    if not isinstance(run.get("head_sha"), str) or not SHA40.fullmatch(run["head_sha"]):
        fail("missing original source Git SHA")
    if run.get("repository") and run["repository"].get("full_name") != REPO:
        fail("different repository")
    files = artifacts.get("artifacts")
    if not isinstance(files, list) or artifacts.get("total_count") != len(files) or len(files) > 100:
        fail("ambiguous or truncated artifact listing")
    candidates = []
    for asset in files:
        if not isinstance(asset, dict) or asset.get("expired") is not False:
            continue
        if not isinstance(asset.get("id"), int) or asset["id"] <= 0:
            continue
        name = asset.get("name")
        if not isinstance(name, str):
            continue
        if name.startswith("pandora-OTA-COMPAT-NONFLASH-"):
            if persistent_compat_ok(source_id, name, persistent):
                candidates.append("ota-compat-persistent")
                continue
            fail("compatibility candidate lacks exact two-reboot persistent proof")
        m_compat = re.fullmatch(r"pandora-OTA-COMPAT-CUSTOM-(OS[0-9]+\.[0-9.]+[A-Z0-9]+)-run-([1-9][0-9]*)", name)
        if m_compat and m_compat.group(1) == "OS4.0.6.0.XBLCNXM" and m_compat.group(2) == source_id:
            if not has_ota_lkg:
                fail("compat custom promotion requires a previously validated same-OTA LKG")
            candidates.append("ota-compat-custom")
            continue
        if name == f"pandora-OS4-R62-CUSTOM-run-{source_id}":
            candidates.append("legacy")
        m = re.fullmatch(r"pandora-OTA-CUSTOM-(OS[0-9]+\.[0-9.]+[A-Z0-9]+)-run-([1-9][0-9]*)", name)
        if m and BUILD.fullmatch(m.group(1)) and m.group(2) == source_id:
            candidates.append("ota")
    if len(candidates) != 1:
        fail("require one nonexpired exact R62 / OTA / verified persistent-compat Artifact; no ambiguity")
    if candidates[0] == "legacy" and has_ota_lkg:
        fail("versioned OTA LKG already supersedes legacy R62 promotion")
    return candidates[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-run-id", required=True)
    ap.add_argument("--run-json", type=Path)
    ap.add_argument("--artifacts-json", type=Path)
    ap.add_argument("--pointer", type=Path, required=True)
    ap.add_argument("--persistent-candidate", type=Path)
    ap.add_argument("--repair", action="store_true")
    args = ap.parse_args()
    src = json.loads(args.run_json.read_text()) if args.run_json else None
    arts = json.loads(args.artifacts_json.read_text()) if args.artifacts_json else None
    persistent = (json.loads(args.persistent_candidate.read_text())
                  if args.persistent_candidate and args.persistent_candidate.exists() else None)
    try:
        mode = route(args.source_run_id, src, arts, args.pointer.exists(),
                     repair=args.repair, persistent=persistent)
    except ValueError as exc:
        ap.error(str(exc))
    print("mode=" + mode)


if __name__ == "__main__":
    main()
