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


def route(source_id: str, run: dict | None, artifacts: dict | None,
          has_ota_lkg: bool, *, repair: bool = False) -> str:
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
        if name == f"pandora-OS4-R62-CUSTOM-run-{source_id}":
            candidates.append("legacy")
        m = re.fullmatch(r"pandora-OTA-CUSTOM-(OS[0-9]+\.[0-9.]+[A-Z0-9]+)-run-([1-9][0-9]*)", name)
        if m and BUILD.fullmatch(m.group(1)) and m.group(2) == source_id:
            candidates.append("ota")
    if len(candidates) != 1:
        fail("require one nonexpired exact R62 or OTA Artifact; no ambiguity")
    if candidates[0] == "legacy" and has_ota_lkg:
        fail("versioned OTA LKG already supersedes legacy R62 promotion")
    return candidates[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-run-id", required=True)
    ap.add_argument("--run-json", type=Path)
    ap.add_argument("--artifacts-json", type=Path)
    ap.add_argument("--pointer", type=Path, required=True)
    ap.add_argument("--repair", action="store_true")
    args = ap.parse_args()
    src = json.loads(args.run_json.read_text()) if args.run_json else None
    arts = json.loads(args.artifacts_json.read_text()) if args.artifacts_json else None
    try:
        mode = route(args.source_run_id, src, arts, args.pointer.exists(), repair=args.repair)
    except ValueError as exc:
        ap.error(str(exc))
    print("mode=" + mode)


if __name__ == "__main__":
    main()
