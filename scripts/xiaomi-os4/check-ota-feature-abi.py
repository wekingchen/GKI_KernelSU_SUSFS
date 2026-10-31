#!/usr/bin/env python3
"""Fail closed when a custom feature build changes the verified OTA's core ABI."""
import argparse
import hashlib
import json
import re
from pathlib import Path

LINE_SHA = re.compile(r"^0x[0-9a-fA-F]{8}$")


def abort(message):
    raise SystemExit("ERROR: " + message)


def read_exports(path):
    exports = {}
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        row = line.split()
        if len(row) < 4 or not LINE_SHA.fullmatch(row[0]):
            abort(f"bad Module.symvers format at {path}:{n}")
        crc, symbol, provider = row[:3]
        if provider != "vmlinux":
            continue
        if symbol in exports and exports[symbol] != crc.lower():
            abort("duplicate core export: " + symbol)
        exports[symbol] = crc.lower()
    if len(exports) < 100:
        abort("too few core kernel exports")
    return exports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-symvers", type=Path, required=True)
    ap.add_argument("--feature-symvers", type=Path, required=True)
    ap.add_argument("--baseline-record", type=Path, required=True)
    ap.add_argument("--feature-metadata", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()
    rec = json.loads(a.baseline_record.read_text())
    sha = lambda x: hashlib.sha256(x.read_bytes()).hexdigest()
    if rec.get("status") != "HUMAN_ATTESTED_BASELINE_BOOTED" or rec.get("safe_to_flash") is not False:
        abort("base is not the verified, nonflashable OTA")
    if sha(a.baseline_symvers) != rec.get("module_symvers_sha256"):
        abort("baseline Module.symvers changed since verification")
    meta = dict(line.split("=", 1) for line in a.feature_metadata.read_text().splitlines() if "=" in line)
    if meta.get("SOURCE_COMMIT") != rec.get("candidate_gki_commit"):
        abort("custom kernel built from wrong GKI commit")
    if meta.get("STOCK_RELEASE") != rec.get("kernel_release"):
        abort("wrong stock kernel release")
    if meta.get("KERNEL_RELEASE") != rec.get("kernel_release"):
        abort("custom kernel vermagic does not match the verified OEM candidate")
    if meta.get("SYMVERS_SHA256") != sha(a.feature_symvers):
        abort("custom Module.symvers does not match build metadata")
    if meta.get("FLASHABLE") != "NO" or meta.get("SELECTABLE_BUILD") != "1":
        abort("custom mode is not the guarded unverified selectable build")

    ref = read_exports(a.baseline_symvers)
    cur = read_exports(a.feature_symvers)
    changed = [(name, crc, cur.get(name)) for name, crc in ref.items() if cur.get(name) != crc]
    added = sorted(cur.keys() - ref.keys())
    report = {
        "schema": 1,
        "device": "pandora",
        "build": rec["stock_build"],
        "source_commit": rec["candidate_gki_commit"],
        "kernel_release": rec["kernel_release"],
        "baseline_exports": len(ref),
        "feature_exports": len(cur),
        "added_core_exports": added,
        "missing_or_crc_changed": [{"symbol": n, "expected": x, "actual": y} for n, x, y in changed[:100]],
        "missing_or_crc_changed_total": len(changed),
        "baseline_symvers_sha256": sha(a.baseline_symvers),
        "feature_symvers_sha256": sha(a.feature_symvers),
        "gate": "PASS" if not changed else "BLOCKED",
        "safe_to_flash": False,
        "full_parity_lkg_promoted": False,
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if changed:
        abort(f"OEM/GKI ABI lock changed {len(changed)} pre-existing vmlinux CRCs or exports")
    print(f"OTA_CUSTOM_ABI=PASS; {len(ref)} baseline exports preserved; {len(added)} new exports")
    print("OTA_CUSTOM_FLASHABLE=NO")


if __name__ == "__main__":
    main()
