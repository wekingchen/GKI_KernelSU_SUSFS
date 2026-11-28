#!/usr/bin/env python3
"""Read-only cross-OTA binary inventory comparison; never authorizes boot."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("oem_abi", Path(__file__).with_name("check-ota-oem-abi.py"))
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(path, expected_sha):
    if digest(path.read_bytes()) != expected_sha:
        raise ValueError("stock archive SHA mismatch")
    result, partitions = {}, {}
    with zipfile.ZipFile(path) as stock:
        def one(name, maximum):
            matches = [x for x in stock.infolist() if not x.is_dir() and x.filename.rsplit("/", 1)[-1] == name]
            if len(matches) != 1 or matches[0].file_size > maximum:
                raise ValueError("missing, duplicate or oversized: " + name)
            return stock.read(matches[0])
        count = int(one("oem-modules-count.txt", 4096).decode("ascii").strip().split("=", 1)[1])
        if not 1 <= count <= abi.MAX_MODULES:
            raise ValueError("invalid module count")
        for name in ("boot.img", "vendor_boot.img", "dtbo.img"):
            partitions[name] = digest(one(name, 128 * 1024 * 1024))
        raw = one("oem-modules.zip", abi.MAX_COMPRESSED_ARCHIVE)
        def add(name, data):
            if name in result or ".." in name.split("/") or len(data) > abi.MAX_MODULE:
                raise ValueError("unsafe or duplicate module " + name)
            sections = abi.elf_sections(data)
            row = abi.module_identity(name, data, sections)
            row.update(imports=abi.imported_versions(sections), exports=abi.module_export_crcs(data))
            result[name] = row
        with zipfile.ZipFile(io.BytesIO(raw)) as modules:
            members = [x for x in modules.infolist() if not x.is_dir() and abi.KO_NAME.search(x.filename)]
            if len(members) != count:
                raise ValueError("module count mismatch")
            for member in members:
                if member.file_size > abi.MAX_MODULE:
                    raise ValueError("oversized module")
                add(member.filename, abi.unpack_module(modules.read(member), member.filename))
        for name, data in abi.extract_vendor_boot_modules(one("vendor_boot.img", 128 * 1024 * 1024)):
            add("vendor_boot/" + name, data)
    return result, partitions


def delta(left, right):
    return {"added": {k: right[k] for k in sorted(right.keys()-left.keys())},
            "removed": {k: left[k] for k in sorted(left.keys()-right.keys())},
            "changed": {k: {"old": left[k], "new": right[k]} for k in sorted(left.keys() & right.keys()) if left[k] != right[k]}}


def compare(old, new, notes):
    changed = []
    for path in sorted(old.keys() & new.keys()):
        a, b = old[path], new[path]
        if a["sha256"] != b["sha256"]:
            changed.append({"path": path, "old_sha256": a["sha256"], "new_sha256": b["sha256"],
                            "old_note_sha256": a["note_sha256"], "new_note_sha256": b["note_sha256"],
                            "imports": delta(a["imports"], b["imports"]),
                            "exports": delta(a["exports"], b["exports"])})
    matched = {}
    for name, note in notes.items():
        variants = [dict(path=x["path"], sha256=x["sha256"], note_sha256=x["note_sha256"])
                    for x in new.values() if x["module_name"] == name]
        matches = [x for x in variants if x["note_sha256"] == note]
        matched[name] = {"variants": variants, "matching_paths": matches,
                         "unique_binary_match": len({x["sha256"] for x in matches}) == 1}
    return {"old_inventory_count": len(old), "new_inventory_count": len(new),
            "unchanged_module_count": sum(old[p]["sha256"] == new[p]["sha256"] for p in old.keys() & new.keys()),
            "added_paths": sorted(new.keys()-old.keys()), "removed_paths": sorted(old.keys()-new.keys()),
            "changed_modules": changed, "runtime_note_comparison": matched}


def main():
    p = argparse.ArgumentParser()
    for name in ("old", "new", "evidence", "output"):
        p.add_argument("--"+name, required=True, type=Path)
    for name in ("old-sha", "new-sha", "evidence-sha"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    evidence = a.evidence.read_bytes()
    if digest(evidence) != a.evidence_sha:
        raise ValueError("evidence SHA mismatch")
    e = json.loads(evidence)
    if e["stock_input_sha256"] != a.new_sha or e["stock_build"] != "OS4.0.8.0.XBLCNXM" or e["source_run_id"] != 46148429897 or e["safe_to_flash"] is not False:
        raise ValueError("unexpected evidence identity")
    obs = e["observations"]["loaded_module_identity"]
    notes = {}
    for name in ("node_cache", "zram", "zsmalloc"):
        note = obs[name]["gnu_note_sha256"]
        if obs[name]["loaded"] is not True or not abi.HEX64.fullmatch(note):
            raise ValueError("missing runtime note: "+name)
        notes[name] = note
    old, op = inventory(a.old, a.old_sha)
    new, np = inventory(a.new, a.new_sha)
    report = compare(old, new, notes)
    report.update(schema="pandora-stock-abi-delta-v1", old_stock_sha256=a.old_sha,
                  new_stock_sha256=a.new_sha, evidence_sha256=a.evidence_sha,
                  partition_hashes={"old": op, "new": np}, safe_to_flash=False,
                  oem_gate_unlocked=False, lkg_promotion=False)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("Read-only inventory comparison completed; no ABI waiver or boot authorization.")


if __name__ == "__main__":
    main()
