#!/usr/bin/env python3
"""Read-only OTA V2 ABI evidence interpreter and immutable-case replay comparator.

A successful *execution* of the OEM checker can legitimately report BLOCKED.
This tool never converts BLOCKED into a flashable/testable result. It classifies
what is actually present in the checker JSON and, optionally, verifies a pinned
historical case. It neither patches the kernel nor downloads/unpacks anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class EvidenceError(ValueError):
    """Malformed, incomplete or inconsistent audit evidence."""


def nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise EvidenceError(f"invalid nonnegative integer: {label}")
    return value


def read_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise EvidenceError("unsupported or malformed OEM ABI report")
    for key in ("failed_modules", "unresolved_kernel_imports",
                "ambiguous_providers", "crc_mismatches"):
        if not isinstance(data.get(key), list):
            raise EvidenceError(f"OEM ABI report missing array: {key}")
    if data.get("gate") not in (
        "BLOCKED", "CRC_AND_VERMAGIC_MATCH_CANDIDATE",
        "CRC_VERMAGIC_AND_RUNTIME_SELECTION_MATCH_CANDIDATE"
    ):
        raise EvidenceError("unrecognized ABI gate")
    if type(data.get("eligible_for_fastboot_boot")) is not bool:
        raise EvidenceError("missing explicit fastboot boot eligibility")
    if data["gate"] == "BLOCKED" and data["eligible_for_fastboot_boot"]:
        raise EvidenceError("blocked ABI report claims boot eligibility")
    if data["gate"] != "BLOCKED" and not data["eligible_for_fastboot_boot"]:
        raise EvidenceError("passed ABI report lacks boot eligibility")
    if data.get("flashable") is not False:
        raise EvidenceError("OEM ABI report must not claim flashability")
    return data


def interpret(report: dict) -> dict:
    """Produce conservative, machine-readable reasons, not a waiver policy."""
    failed = len(report["failed_modules"])
    unresolved = len(report["unresolved_kernel_imports"])
    ambiguous = len(report["ambiguous_providers"])
    crc = len(report["crc_mismatches"])
    rust = nonnegative_int(report.get("unresolved_rust_binder", 0),
                           "unresolved_rust_binder")
    if rust > unresolved:
        raise EvidenceError("rust_binder unresolved count exceeds all unresolved imports")
    same = nonnegative_int(report.get("ambiguous_same_crc", 0), "ambiguous_same_crc")
    split = nonnegative_int(report.get("ambiguous_split_crc", 0), "ambiguous_split_crc")
    if same + split > ambiguous:
        raise EvidenceError("provider ambiguity subcounts exceed total ambiguity")
    reasons = []
    if failed:
        reasons.append({
            "code": "OEM_MODULE_PARSE_OR_IDENTITY_FAILURE",
            "count": failed,
            "next_evidence": "Inspect exact SHA-bound module path, ELF format, vermagic and archive integrity",
        })
    if rust:
        reasons.append({
            "code": "STOCK_RUST_BINDER_ABI_UNRESOLVED",
            "count": rust,
            "next_evidence": "Compare Rust source/toolchain ABI; collect read-only Binder active_impl and module loader evidence",
        })
    if unresolved > rust:
        reasons.append({
            "code": "OTHER_UNRESOLVED_IMPORTS",
            "count": unresolved - rust,
            "next_evidence": "Audit vendor_boot early providers and complete OEM module import/export graph",
        })
    if ambiguous:
        reasons.append({
            "code": "AMBIGUOUS_MODULE_PROVIDERS",
            "count": ambiguous,
            "same_crc": same,
            "split_crc": split,
            "next_evidence": "Identify the runtime-selected binary with stock SHA and loaded GNU Note; keep vendor/system separate",
        })
    if crc:
        reasons.append({
            "code": "MODULE_CRC_MISMATCH",
            "count": crc,
            "next_evidence": "Verify exact GKI source commit, Module.symvers and OEM binary export/import CRC",
        })

    passed = report["gate"] != "BLOCKED"
    if passed and (failed or unresolved or ambiguous or crc):
        raise EvidenceError("passing ABI gate contains unresolved module failures")
    if passed and report["gate"] == "CRC_VERMAGIC_AND_RUNTIME_SELECTION_MATCH_CANDIDATE":
        if report.get("runtime_selection_status") != "APPLIED_FAIL_CLOSED":
            raise EvidenceError("runtime-selected PASS missing fail-closed evidence")
    if passed:
        status = "STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST"
    elif reasons:
        status = "ABI_BLOCKED_DIAGNOSABLE"
    else:
        status = "AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW"
        reasons.append({
            "code": "INPUT_OR_PROVENANCE_BLOCKED",
            "count": 1,
            "next_evidence": "Review original checker reason and SHA-bound stock/GKI inputs; no module graph conclusion",
        })

    return {
        "schema": 1,
        "status": status,
        "stock_build": report.get("stock_build"),
        "candidate_commit": report.get("candidate_commit"),
        "stock_input_sha256": report.get("stock_input_sha256"),
        "evidence": {
            "inventory_imports": report.get("inventory_imports_before_runtime_selection"),
            "imports_checked": report.get("imports_checked"),
            "dlkm_modules": report.get("module_count"),
            "vendor_boot_modules": report.get("vendor_boot_modules_seen"),
            "vendor_boot_independent_modules": report.get("vendor_boot_modules_in_graph"),
            "failed_modules": failed,
            "unresolved_imports": unresolved,
            "unresolved_rust_binder": rust,
            "ambiguous_providers": ambiguous,
            "crc_mismatches": crc,
        },
        "diagnoses": reasons,
        "oem_gate": report["gate"],
        "fastboot_boot_eligible": bool(report["eligible_for_fastboot_boot"]),
        "persistent_install_authorized": False,
        "lkg_promotion_authorized": False,
        "auto_waiver_applied": False,
        "checker_reason": report.get("reason"),
    }


def verify_reference(report: dict, reference: dict) -> dict:
    """A replay must match every pinned, real historical measurement exactly.

    Historical raw stock ABI was BLOCKED. Matching that result is *successfully
    replaying a blocked gate*, never a newly passed compatibility certificate.
    """
    if (not isinstance(reference, dict) or reference.get("schema") != 1
            or reference.get("case") != "pandora-os4-406-raw-oem-abi"):
        raise EvidenceError("unsupported replay reference")
    expected = reference.get("expected_report")
    if not isinstance(expected, dict) or not expected:
        raise EvidenceError("empty replay expected report")
    values = dict(report)
    values["unresolved_kernel_imports_count"] = len(report["unresolved_kernel_imports"])
    values["ambiguous_providers_count"] = len(report["ambiguous_providers"])
    values["crc_mismatches_count"] = len(report["crc_mismatches"])
    values["failed_modules_count"] = len(report["failed_modules"])
    diffs = {key: {"expected": value, "actual": values.get(key, "<missing>")}
             for key, value in expected.items() if values.get(key) != value}
    if diffs:
        raise EvidenceError("pinned historical ABI replay drift: "
                            + json.dumps(diffs, ensure_ascii=False, sort_keys=True))
    if report["gate"] != "BLOCKED" or report["eligible_for_fastboot_boot"]:
        raise EvidenceError("historical raw stock ABI must remain blocked")
    return {
        "case": reference["case"],
        "matched": True,
        "expected_status": "ABI_BLOCKED_DIAGNOSABLE",
        "expected_fields_checked": len(expected),
        "historical_gate_still_blocked": True,
    }


def markdown(data: dict) -> str:
    e = data["evidence"]
    rows = [
        "## Pandora OTA V2 · 只读兼容性诊断",
        "",
        f"- 诊断状态：\u0060{data['status']}\u0060",
        f"- OEM Gate：\u0060{data['oem_gate']}\u0060",
        f"- OTA：\u0060{data['stock_build']}\u0060",
        f"- GKI Commit：\u0060{data['candidate_commit']}\u0060",
        f"- OEM 模块：DLKM {e['dlkm_modules']} / vendor_boot {e['vendor_boot_modules']}",
        f"- 模块导入：{e['inventory_imports']}（参与检查 {e['imports_checked']}）",
        f"- 未解析导入：{e['unresolved_imports']}（Rust Binder {e['unresolved_rust_binder']}）",
        f"- 提供者歧义：{e['ambiguous_providers']}；CRC 不匹配：{e['crc_mismatches']}",
        "- 不允许自动刷机、持久安装或 LKG 晋升；BLOCKED 不能生成待测 boot。",
        "",
        "### 诊断与下一步证据",
    ]
    for reason in data["diagnoses"]:
        rows.append(f"- \u0060{reason['code']}\u0060 × {reason['count']}：{reason['next_evidence']}")
    if "reference_replay" in data:
        rows.extend(["", "### OS4.0.6 历史案例回放",
                     "- SHA 绑定原始归档重新审计后的结果与固定参考完全一致。",
                     "- **回放通过只代表成功复现 BLOCKED，并不代表内核兼容或可以刷机。**"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--abi-report", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    try:
        report = read_report(args.abi_report)
        interpreted = interpret(report)
        if args.reference:
            ref = json.loads(args.reference.read_text(encoding="utf-8"))
            interpreted["reference_replay"] = verify_reference(report, ref)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(interpreted, sort_keys=True, indent=2,
                                           ensure_ascii=False) + "\n", encoding="utf-8")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown(interpreted), encoding="utf-8")
        print("OTA_V2_DIAGNOSTIC_STATUS=" + interpreted["status"])
        print("OTA_V2_REFERENCE_REPLAY=" +
              ("MATCHED_BLOCKED" if args.reference else "NOT_REQUESTED"))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("::error::OTA V2 evidence replay blocked: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
