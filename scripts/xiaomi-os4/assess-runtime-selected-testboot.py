#!/usr/bin/env python3
"""Fail-closed shadow gate for one pandora OS4.0.6 boot-only experiment.

This never upgrades the formal OEM ABI gate. It only proves that the exact
remaining blockers are the already-measured stock runtime-selection cases.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

def digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()

def fail(report: dict, reason: str) -> dict:
    report["reason"] = reason
    return report

def assess(abi: dict, runtime: dict) -> dict:
    out = {
        "schema": 1,
        "formal_oem_gate": abi.get("gate", "UNKNOWN"),
        "formal_oem_gate_unchanged": True,
        "experimental_gate": "BLOCKED",
        "eligible_for_fastboot_boot_experiment": False,
        "flashable": False,
        "eligible_for_persistent_flash": False,
        "lkg_promotion": False,
        "reason": "unverified",
    }
    c = runtime["shadow_blocker_contract"]
    rs = runtime["runtime_selection"]
    if abi.get("gate") != runtime["safety"]["formal_oem_gate_must_remain"]:
        return fail(out, "formal OEM gate unexpectedly changed")
    exact = {
        "stock_build": runtime["stock_build"],
        "stock_input_sha256": runtime["stock_input_sha256"],
        "kernel_release": runtime["stock_uname"],
        "candidate_commit": runtime["candidate_gki_commit"],
    }
    for key, value in exact.items():
        if abi.get(key) != value:
            return fail(out, f"{key} drift")
    if abi.get("failed_modules") != [] or abi.get("crc_mismatches") != []:
        return fail(out, "unexpected failed module or CRC mismatch")
    unresolved = abi.get("unresolved_kernel_imports", [])
    if len(unresolved) != c["unresolved_kernel_imports"]:
        return fail(out, "unresolved import count drift")
    if digest(unresolved) != c["unresolved_sorted_sha256"]:
        return fail(out, "unresolved import identity drift")
    prefix = c["rust_binder_path"] + ":"
    if not all(x.startswith(prefix) and x.rsplit(":",1)[-1].startswith("_R")
               for x in unresolved):
        return fail(out, "unresolved imports are not exclusively Rust Binder mangled symbols")
    if abi.get("unresolved_rust_binder") != c["unresolved_rust_binder"] or \
       abi.get("unresolved_rust_mangled") != c["unresolved_rust_mangled"]:
        return fail(out, "Rust Binder unresolved counters drift")
    ambiguous = abi.get("ambiguous_providers", [])
    if len(ambiguous) != c["ambiguous_providers"] or digest(ambiguous) != c["ambiguous_sorted_sha256"]:
        return fail(out, "ambiguous provider identity drift")
    if abi.get("ambiguous_same_crc") != c["ambiguous_same_crc"] or \
       abi.get("ambiguous_split_crc") != c["ambiguous_split_crc"]:
        return fail(out, "zsmalloc ambiguity counters drift")
    details = abi.get("ambiguous_provider_details", [])
    expected_providers = set(c["zsmalloc_providers"])
    expected_consumers = set(c["zsmalloc_consumers"])
    if len(details) != c["ambiguous_providers"]:
        return fail(out, "ambiguous detail count drift")
    for d in details:
        if d.get("consumer") not in expected_consumers or not str(d.get("symbol","")).startswith("zs_"):
            return fail(out, "unexpected ambiguous consumer/symbol")
        providers = {x.get("module") for x in d.get("providers", [])}
        if providers != expected_providers:
            return fail(out, "unexpected ambiguous provider set")
        matches = [x for x in d.get("providers", []) if x.get("crc_matches") is True]
        if len(matches) < 1:
            return fail(out, "no CRC-compatible zsmalloc provider")
    required_runtime = {
        "binder_requested_impl": "c",
        "binder_active_impl_direct": "UNAVAILABLE",
        "rust_binder_module_loaded_stock": True,
        "rust_binder_source": "system",
        "rust_binder_system_manifest": True,
        "rust_binder_hard_dependencies": 0,
        "zsmalloc_source": "vendor",
        "zram_source": "vendor",
        "node_cache_source": "vendor",
        "stock_same_name_system_zsmalloc_requested_but_vendor_loaded": True,
        "stock_same_name_system_zram_requested_but_vendor_loaded": True,
    }
    for key, value in required_runtime.items():
        if rs.get(key) != value:
            return fail(out, "runtime selection evidence drift: " + key)
    out.update(
        experimental_gate="RUNTIME_SELECTED_EEXIST_SHIM_TEST_ELIGIBLE",
        eligible_for_fastboot_boot_experiment=True,
        reason=("Formal gate remains BLOCKED; exact residual set is limited to "
                "inert stock rust_binder plus runtime-resolved zsmalloc provider selection."),
        expected_shim_parameter="pandora_rust_binder_eexist=1",
        expected_skipped_module="rust_binder",
        runtime_zsmalloc_provider="vendor",
        binder_main_impl_evidence="C_STRONGLY_SUPPORTED",
    )
    return out

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--abi-report",required=True,type=Path)
    ap.add_argument("--runtime-selection",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    result=assess(json.loads(a.abi_report.read_text()),
                  json.loads(a.runtime_selection.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(result["experimental_gate"])
    return 0 if result["eligible_for_fastboot_boot_experiment"] else 1

if __name__=="__main__":
    raise SystemExit(main())
