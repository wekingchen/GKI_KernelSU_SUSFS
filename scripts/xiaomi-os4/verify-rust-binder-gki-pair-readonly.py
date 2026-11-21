#!/usr/bin/env python3
"""Read-only Rust Binder -> GKI export audit. Never grants flash eligibility.

The stock OEM graph and its zsmalloc ambiguities remain authoritative. A
matching candidate rust_binder.ko ONLY proves consistency with its paired,
SHA-locked GKI Module.symvers, not a working Android Binder implementation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "pandora_oem_abi", Path(__file__).with_name("check-ota-oem-abi.py"))
_abi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_abi)


def analyze(candidate: bytes, symvers: Path, config: str,
            metadata: dict[str, str], stock: dict) -> dict:
    report = {
        "schema": 1,
        "gate": "BLOCKED",
        "flashable": False,
        "eligible_for_fastboot_boot": False,
        "stock_oem_abi_gate_unchanged": True,
        "zsmalloc_vendor_system_separate": True,
        "rust_gki_pair": "BLOCKED",
        "reason": "not checked",
    }
    try:
        expected_build = "OS4.0.6.0.XBLCNXM"
        expected_stock_sha = "bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8"
        if (metadata.get("STOCK_BUILD") != expected_build or
                stock.get("stock_build") != expected_build or
                stock.get("stock_input_sha256") != expected_stock_sha or
                metadata.get("STOCK_INPUT_SHA256") != expected_stock_sha):
            raise ValueError("stock 4.0.6 provenance mismatch")
        if (stock.get("gate") != "BLOCKED" or
                stock.get("eligible_for_fastboot_boot") is not False or
                stock.get("unresolved_rust_binder") != 71 or
                stock.get("stock_rust_binder_imports") != 240 or
                stock.get("ambiguous_same_crc") != 24 or
                stock.get("ambiguous_split_crc") != 3 or
                stock.get("stock_rust_binder_sha256") !=
                "ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c"):
            raise ValueError("actual blocked stock Binder/zsmalloc evidence missing")
        if (config.splitlines().count("CONFIG_ANDROID_BINDER_IPC_RUST=m") != 1 or
                config.splitlines().count("CONFIG_RUST=y") != 1 or
                config.splitlines().count("CONFIG_MODVERSIONS=y") != 1):
            raise ValueError("candidate config does not enable modular Rust Binder")
        commit = metadata.get("SOURCE_GKI_COMMIT", "")
        if (not re.fullmatch(r"[0-9a-f]{40}", commit) or
                metadata.get("SOURCE_GKI_TAG") != "android16-6.12-2026-03_r74" or
                metadata.get("FLASHABLE") != "NO" or
                metadata.get("FASTBOOT_BOOT") != "NOT_BUILT" or
                metadata.get("ANYKERNEL3") != "NOT_BUILT" or
                metadata.get("LKG_PROMOTION") != "FORBIDDEN"):
            raise ValueError("GKI commit/tag or no-flash provenance is invalid")
        release = metadata.get("KERNEL_RELEASE")
        if not release or release != stock.get("kernel_release"):
            raise ValueError("stock/GKI kernel release mismatch")
        if _abi.sha(symvers.read_bytes()) != metadata.get("SYMVERS_SHA256"):
            raise ValueError("GKI Module.symvers SHA256 differs from build metadata")
        sections = _abi.elf_sections(candidate)
        if _abi.module_vermagic(sections) != release:
            raise ValueError("candidate Binder vermagic differs from paired GKI")
        imported = _abi.imported_versions(sections)
        exports = _abi.symvers(symvers)  # Only actual vmlinux exports, not OEM names.
        unresolved = sorted(name for name in imported if name not in exports)
        mismatches = sorted(name for name, crc in imported.items()
                            if name in exports and crc != exports[name])
        report.update(
            gki_commit=commit,
            gki_tag=metadata["SOURCE_GKI_TAG"],
            kernel_release=release,
            candidate_rust_binder_sha256=_abi.sha(candidate),
            candidate_rust_binder_imports=len(imported),
            candidate_rust_mangled_imports=sum(x.startswith("_R") for x in imported),
            candidate_vmlinux_exports=len(exports),
            unresolved_candidate_imports=unresolved,
            mismatched_candidate_imports=mismatches,
            stock_unresolved_rust_binder=71,
            stock_zsmalloc_ambiguous_same_crc=24,
            stock_zsmalloc_ambiguous_split_crc=3,
            stock_rust_binder_sha256=stock["stock_rust_binder_sha256"],
        )
        if not imported or unresolved or mismatches:
            raise ValueError("candidate Binder imports are not fully compatible with paired GKI exports")
        report["rust_gki_pair"] = "PASS_GKI_PAIR_ONLY"
        report["reason"] = (
            "Candidate rust_binder.ko import CRCs match paired GKI vmlinux. "
            "OEM Rust Binder remains incompatible; 27 vendor/system zsmalloc "
            "ambiguities and runtime module-delivery evidence remain BLOCKED."
        )
    except Exception as exc:
        report["reason"] = str(exc)[:350]
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-module", required=True, type=Path)
    p.add_argument("--symvers", required=True, type=Path)
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--metadata", required=True, type=Path)
    p.add_argument("--stock-abi-report", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    try:
        metadata = dict(line.split("=", 1) for line in a.metadata.read_text().splitlines() if "=" in line)
        result = analyze(a.candidate_module.read_bytes(), a.symvers,
                         a.config.read_text(), metadata,
                         json.loads(a.stock_abi_report.read_text()))
    except Exception as exc:
        result = {
            "schema": 1, "gate": "BLOCKED", "flashable": False,
            "eligible_for_fastboot_boot": False,
            "stock_oem_abi_gate_unchanged": True,
            "zsmalloc_vendor_system_separate": True,
            "rust_gki_pair": "BLOCKED",
            "reason": "input audit failed: " + str(exc)[:250],
        }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False,
                                   indent=2, sort_keys=True) + "\n")
    print("RUST_BINDER_NONFLASH=" + result["rust_gki_pair"])
    print("OEM_ABI_GATE=BLOCKED (never changed by this script)")
    print("NO_FLASH=YES")
    return 0 if result["rust_gki_pair"] == "PASS_GKI_PAIR_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
