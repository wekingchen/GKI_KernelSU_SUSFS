#!/usr/bin/env python3
"""Issue-scoped, non-executable diagnostic tasks for the Pandora OTA companion.

No shell commands are sent to the device. Task types are allowlisted in the
installed Android app; a task is a request for local READ-ONLY observations.
"""
import argparse
import json
import re
from pathlib import Path

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEAD = re.compile(r"[0-9a-f]{40}\Z")
BUILD = re.compile(r"OS[0-9]+\.[0-9.]+[A-Z0-9]+\Z")
ISSUES = {
    "STOCK_RUST_BINDER_ABI_UNRESOLVED": "binder_runtime",
    "AMBIGUOUS_MODULE_PROVIDERS": "loaded_module_identity",
    "OTHER_UNRESOLVED_IMPORTS": "loaded_module_identity",
    "MODULE_CRC_MISMATCH": "loaded_module_identity",
    "OEM_MODULE_PARSE_OR_IDENTITY_FAILURE": "loaded_module_identity",
}
LABELS = {
    "binder_runtime": "确认实际 Binder 实现及 Rust Binder 加载情况",
    "loaded_module_identity": "确认已加载模块的身份与来源",
}


def build_task(diagnostic, run, head):
    if diagnostic.get("schema") != 1 or diagnostic.get("status") != "ABI_BLOCKED_DIAGNOSABLE":
        raise ValueError("Only diagnosable OEM ABI BLOCKED reports may create a mobile task")
    if diagnostic.get("oem_gate") != "BLOCKED" or diagnostic.get("fastboot_boot_eligible") is not False:
        raise ValueError("OEM gate did not remain BLOCKED")
    if diagnostic.get("persistent_install_authorized") is not False or diagnostic.get("lkg_promotion_authorized") is not False:
        raise ValueError("Unexpected privileged diagnostic state")
    if diagnostic.get("auto_waiver_applied") is not False:
        raise ValueError("Automatic ABI waiver is forbidden")
    if type(run) is not int or run <= 0 or not HEAD.fullmatch(head):
        raise ValueError("Invalid source run/head")
    build = diagnostic.get("stock_build")
    stock_sha = diagnostic.get("stock_input_sha256")
    candidate_commit = diagnostic.get("candidate_commit")
    if not isinstance(build, str) or not BUILD.fullmatch(build):
        raise ValueError("Missing recognized stock build")
    if not isinstance(stock_sha, str) or not HEX64.fullmatch(stock_sha):
        raise ValueError("Missing SHA-bound OTA input")
    if not isinstance(candidate_commit, str) or not HEAD.fullmatch(candidate_commit):
        raise ValueError("Missing candidate GKI commit")
    diagnoses = diagnostic.get("diagnoses")
    if not isinstance(diagnoses, list) or not 1 <= len(diagnoses) <= 5:
        raise ValueError("Missing diagnosis list")
    seen = set()
    observations = []
    reasons = []
    for item in diagnoses:
        if not isinstance(item, dict):
            raise ValueError("Invalid diagnosis record")
        code, count = item.get("code"), item.get("count")
        if code not in ISSUES or code in seen or type(count) is not int or count <= 0:
            raise ValueError("Unknown/duplicated/nonpositive issue")
        seen.add(code)
        observations.append(dict(code=code, count=count))
        task_type = ISSUES[code]
        if task_type not in reasons:
            reasons.append(task_type)
    return {
        "schema": "pandora-ota-diagnostic-task-v1",
        "repository": "wekingchen/GKI_KernelSU_SUSFS",
        "device": "pandora",
        "source_run_id": run,
        "source_head_sha": head,
        "stock_build": build,
        "stock_input_sha256": stock_sha,
        "candidate_commit": candidate_commit,
        "status": "ABI_BLOCKED_DIAGNOSABLE",
        "issues": observations,
        "checks": [{"id": item, "label": LABELS[item]} for item in reasons],
        "requires_manual_review": True,
        "commands": [],
        "device_write_allowed": False,
        "upload_requires_confirmation": True,
        "safe_to_flash": False,
        "promote_lkg": False,
        "note": "Read-only device observations are diagnostic clues, not a verified OEM ABI compatibility proof.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--diagnostic", type=Path, required=True)
    p.add_argument("--source-run", type=int, required=True)
    p.add_argument("--source-head", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    task = build_task(json.loads(a.diagnostic.read_text(encoding="utf-8")), a.source_run, a.source_head)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
