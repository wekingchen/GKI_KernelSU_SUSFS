#!/usr/bin/env python3
"""Guarded decision for K50 Pro to return from private fork to native upstream.

Compilation success is sufficient for retirement of unattended fork sync.
No on-device flashing or human confirmation is required.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

UPSTREAM = "zzh20188/GKI_KernelSU_SUSFS"
VALID_MODES = ("fork", "upstream")


def validate_route(route: dict) -> None:
    if route.get("schema") != 1 or route.get("mode") not in VALID_MODES:
        raise ValueError("untrusted or invalid K50Pro route state")
    for key in ("upstream_build_blob", "upstream_custom_blob"):
        if not re.fullmatch(r"[a-f0-9]{40}", str(route.get(key, ""))):
            raise ValueError("route state has an invalid upstream SHA: " + key)


def needs_test(route: dict, build_blob: str, custom_blob: str) -> bool:
    validate_route(route)
    return (route["upstream_build_blob"] != build_blob or
            route["upstream_custom_blob"] != custom_blob)


def validate_native_source(build: str, custom: str) -> None:
    # The *original* upstream action calls its *original* reusable build.
    if "workflow_call:" not in build or "workflow_dispatch:" not in custom:
        raise ValueError("upstream native workflow no longer supports both entrypoints")
    if "uses: ./.github/workflows/build.yml" not in custom:
        raise ValueError("upstream native caller no longer uses native build.yml")
    # Never accidentally test a simplified configuration in lieu of
    # the proven K50 Pro full-feature selectable workflow.
    # A feature must still be both selectable and forwarded to build.yml;
    # finding a duplicate "use_bbg:" only in the with: map is not enough.
    for option, forwarded in (
        ("use_bbg", "use_bbg"), ("use_nomount", "use_nomount"),
        ("use_networking", "use_networking"), ("use_rekernel", "use_rekernel"),
        ("use_zram", "use_zram"), ("kernelsu_variant", "ksu_variant"),
        ("droidspaces", "droidspaces"),
        ("cve_2026_43499_patch", "cve_2026_43499_patch"),
    ):
        definition = rf"(?m)^      {option}:\\s*$"
        mapping = rf"(?m)^      {forwarded}:\\s*\\$\\{{\\{{\\s*inputs\\.{option}\\b"
        if not re.search(definition, custom) or not re.search(mapping, custom):
            raise ValueError("upstream native menu removed or stopped forwarding K50 Pro option: " + option)
    for expected in ("nick-fields/retry", "enable_susfs", "BBG", "AnyKernel3"):
        if expected not in build:
            raise ValueError("upstream native build lacks required feature: " + expected)
    # The known bootable K50 Pro kernel was compiled with Clang FULL LTO.
    # The old upstream build forced THIN LTO, and does not qualify as a
    # safe unattended replacement just because its CI happens to pass.
    if re.search(r"(?m)^\s*(?:LTO=thin\b|LTO_FLAG=.--lto=thin)", build):
        raise ValueError("upstream still forces Thin LTO; preserve known-good FULL LTO")
    if "prepare-host-linker.sh" in build or "gki-generic-build.swap" in build:
        raise ValueError("native upstream source unexpectedly contains private fallback fixes")


def promoted_state(route: dict, *, build_blob: str, custom_blob: str,
                   commit: str, run_id: int) -> dict:
    validate_route(route)
    for sha in (build_blob, custom_blob, commit):
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("invalid upstream SHA for auto-promotion")
    if run_id <= 0:
        raise ValueError("unverified real kernel build run")
    return {
        "schema": 1, "mode": "upstream",
        "upstream_repository": UPSTREAM,
        "upstream_commit": commit,
        "upstream_build_blob": build_blob,
        "upstream_custom_blob": custom_blob,
        "validated_kernel_run_id": run_id,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--route", type=Path, required=True)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--custom", type=Path, required=True)
    p.add_argument("--build-blob", required=True)
    p.add_argument("--custom-blob", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--run-id", type=int, default=0)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    route = json.loads(args.route.read_text())
    validate_route(route)
    changed = needs_test(route, args.build_blob, args.custom_blob)
    if not changed:
        print("UPSTREAM_NATIVE_CHANGED=false")
        return
    validate_native_source(args.build.read_text(), args.custom.read_text())
    print("UPSTREAM_NATIVE_CHANGED=true")
    if not args.check_only:
        if not args.output:
            raise ValueError("missing promoted state output")
        next_state = promoted_state(route, build_blob=args.build_blob,
                                    custom_blob=args.custom_blob,
                                    commit=args.commit, run_id=args.run_id)
        args.output.write_text(json.dumps(next_state, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        sys.exit("UPSTREAM_NATIVE_REJECTED: " + str(e))
