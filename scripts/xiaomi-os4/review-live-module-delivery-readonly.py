#!/usr/bin/env python3
"""Interpret pandora module-delivery CMD capture without upgrading its evidence.

On-disk SHA and modules.load are NOT proof of an in-memory loaded ELF. This
script is read-only, offline, never changes stock ABI and never grants boot.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

EXPECTED = {
    "system-rust-binder-file-sha.txt": ("system", "rust_binder",
        "ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c",
        "/system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/kernel/drivers/android/binder/rust_binder.ko"),
    "system-zsmalloc-file-sha.txt": ("system", "zsmalloc",
        "b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465",
        "/system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/kernel/mm/zsmalloc.ko"),
    "vendor-zsmalloc-file-sha.txt": ("vendor", "zsmalloc",
        "350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e",
        "/vendor_dlkm/lib/modules/zsmalloc.ko"),
}

def safe_text(folder: Path, name: str, limit: int=100000) -> str | None:
    path = folder / name
    if path.is_symlink() or not path.is_file():
        return None
    if path.stat().st_size > limit:
        raise ValueError("oversized evidence file: " + name)
    return path.read_text(encoding="utf-8-sig", errors="replace").replace("\r", "")


def evaluate(folder: Path) -> dict:
    report = {
        "schema": 1, "gate": "BLOCKED", "flashable": False,
        "eligible_for_fastboot_boot": False,
        "oem_abi_gate_unchanged": True, "zsmalloc_source_separation": True,
        "source": "READ_ONLY_LIVE_FILESYSTEM_SNAPSHOT_NOT_LOADED_ELF_PROOF",
        "runtime_loaded_binary_sha256": "NOT_PROVEN",
        "module_delivery_verified": False,
        "system_dlkm_avb_chain_verified": False,
        "signing_trust_verified": False,
        "overall_status": "PARTIAL",
        "reason": "incomplete or unverified evidence",
    }
    try:
        lines = (safe_text(folder, "identity.txt") or "").splitlines()
        if len(lines) < 5 or lines[:2] != [
                "device=pandora", "build=OS4.0.6.0.XBLCNXM"]:
            raise ValueError("not verified pandora OS4.0.6.0 evidence")
        release = "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
        if lines[2].strip() not in ("_a", "_b") or lines[3].strip() != release:
            raise ValueError("slot or running kernel release differs from stock evidence")
        report["slot"] = lines[2].strip()
        report["boot_completed"] = lines[4].strip() == "1"
        if not report["boot_completed"]:
            raise ValueError("device boot not completed")
        assert folder.is_dir()
        results = {}
        discrepancies = []
        unknown = []
        for filename, (partition, module, expected, exactpath) in EXPECTED.items():
            data = (safe_text(folder, filename) or "").strip()
            scoped = partition + ":" + module
            m = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(/\S+)", data)
            if not m or m.group(2) != exactpath:
                results[scoped] = {"on_disk": "UNKNOWN", "path": exactpath,
                                   "loaded_binary_sha256": "NOT_PROVEN"}
                unknown.append(scoped)
                continue
            actual = m.group(1).lower()
            state = "MATCH_PINNED_STOCK_FILE" if actual == expected else "DIFFERS_FROM_PINNED_STOCK"
            results[scoped] = {"on_disk": state, "path": exactpath,
                               "observed_sha256": actual,
                               "expected_sha256": expected,
                               "loaded_binary_sha256": "NOT_PROVEN"}
            if actual != expected:
                discrepancies.append(scoped)
        loaded = safe_text(folder, "loaded-modules-redacted.txt") or ""
        names = {line.split()[0] for line in loaded.splitlines()
                 if re.fullmatch(r"[A-Za-z0-9_-]+\s+size=\d+\s+users=\d+", line.strip())}
        report["observed_loaded_module_names"] = sorted(
            names & {"rust_binder", "zram", "zsmalloc", "node_cache", "binder_linux"})
        cmd = (safe_text(folder, "binder-impl-cmdline.txt") or "").splitlines()
        binder_tokens = sorted({x.strip() for x in cmd if
                                re.fullmatch(r"binder\.impl=[A-Za-z0-9_-]+", x.strip())})
        report["observed_binder_cmdline_tokens"] = binder_tokens
        report["binder_implementation_verified"] = False
        report["binder_implementation_selection"] = "UNPROVEN"
        report["on_disk_source_qualified_modules"] = results
        report["on_disk_discrepancies"] = discrepancies
        report["on_disk_unknowns"] = unknown
        report["mounts_observed"] = bool((safe_text(folder, "dlkm-mounts.txt") or "").strip())
        report["modules_load_observed"] = {
            "system": bool((safe_text(folder, "system-modules.load") or "").strip()),
            "vendor": bool((safe_text(folder, "vendor-modules.load") or "").strip()),
        }
        report["overall_status"] = ("ON_DISK_PINNED_FILES_MATCH_NO_LOADER_PROOF"
             if not unknown and not discrepancies else
             "ON_DISK_DISCREPANCY_NO_LOADER_PROOF" if discrepancies else "PARTIAL")
        report["reason"] = ("On-disk file SHA is not a loaded-module hash. Runtime "
                            "implementation, kernel signature policy and AVB still unproven.")
    except Exception as exc:
        report["reason"] = str(exc)[:250]
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = evaluate(a.evidence_dir)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n")
    print(report["overall_status"] + " / OEM ABI BLOCKED / NO FLASH")
    return 0 if report["overall_status"] == "ON_DISK_PINNED_FILES_MATCH_NO_LOADER_PROOF" else 1


if __name__ == "__main__":
    raise SystemExit(main())
