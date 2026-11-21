#!/usr/bin/env python3
"""Read-only diagnostic; never alters the OEM ABI gate or creates boot images."""
import argparse
import collections
import importlib.util
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("abi", ROOT / "check-ota-oem-abi.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stock-zip", type=Path, required=True)
    p.add_argument("--candidate-symvers", type=Path, required=True)
    p.add_argument("--abi-report", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = json.loads(args.abi_report.read_text())
    if report["eligible_for_fastboot_boot"] or report["gate"] != "BLOCKED":
        raise ValueError("diagnostic is valid only for confirmed BLOCKED baseline")
    expected = report["unresolved_kernel_imports"]
    ambiguous = report["ambiguous_providers"]
    expected_counts = (923, 27)
    if (len(expected), len(ambiguous)) != expected_counts:
        raise ValueError("input ABI evidence unexpectedly changed; re-audit the version")

    with zipfile.ZipFile(args.stock_zip) as outer:
        nested = outer.read("oem-modules.zip")
    modules = {}
    exports = {}
    with zipfile.ZipFile(io.BytesIO(nested)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not abi.KO_NAME.search(info.filename):
                continue
            data = abi.unpack_module(archive.read(info), info.filename)
            sections = abi.elf_sections(data)
            imports = abi.imported_versions(sections)
            module_exports = abi.module_export_crcs(data)
            modinfo = sections.get(".modinfo", b"").split(b"\x00")
            attrs = {}
            for field in modinfo:
                if b"=" in field:
                    k, val = field.split(b"=", 1)
                    if k in (b"depends", b"name", b"srcversion"):
                        attrs[k.decode()] = val.decode("ascii", "replace")
            modules[info.filename] = dict(imports=imports, exported=module_exports, modinfo=attrs)
            for symbol, crc in module_exports.items():
                exports.setdefault(symbol, []).append(dict(name=info.filename, crc=f"0x{crc:08x}",
                                                              srcversion=attrs.get("srcversion"),
                                                              module_name=attrs.get("name")))
    candidates = collections.defaultdict(list)
    for line in args.candidate_symvers.read_text().splitlines():
        cols = line.split()
        if len(cols) >= 4:
            crc, symbol, provider = cols[:3]
            if provider != "vmlinux":
                candidates[symbol].append(dict(provider=provider, crc=crc))
    missing_by_symbol = collections.defaultdict(list)
    missing_by_module = collections.Counter()
    cross_gki_modules = []
    for item in expected:
        module, sym = item.rsplit(":", 1)
        missing_by_symbol[sym].append(module)
        missing_by_module[module] += 1
        if sym in candidates:
            cross_gki_modules.append(dict(module=module, symbol=sym, candidate_providers=candidates[sym],
                                          consumer_crc=f"0x{modules[module]['imports'][sym]:08x}"))
    duplicates = []
    for item in ambiguous:
        module, sym, reason = item.rsplit(":", 2)
        details = exports.get(sym, [])
        duplicates.append(dict(consumer=module, symbol=sym, reason=reason,
                               consumer_crc=f"0x{modules[module]['imports'][sym]:08x}",
                               providers=details,
                               identical_crc=(len(set(e["crc"] for e in details)) == 1)))
    missing_ranked = sorted(
        (dict(symbol=symbol, import_count=len(consumers),
              modules=sorted(set(consumers))[:6],
              rust_symbol=symbol.startswith(("_R", "_ZN"))) 
         for symbol, consumers in missing_by_symbol.items()),
        key=lambda x: (-x["import_count"], x["symbol"])
    )
    summary = dict(
        status="READ_ONLY_DIAGNOSIS_NO_ABI_OVERRIDE",
        input_blocked=True,
        unresolved_imports=len(expected),
        unresolved_unique_symbols=len(missing_ranked),
        unresolved_consumer_modules=len(missing_by_module),
        rust_binder_missing=missing_by_module.get(next((k for k in modules if k.endswith("/rust_binder.ko")), ""), 0),
        gki_non_vmlinux_possible_provider_imports=len(cross_gki_modules),
        ambiguous_imports=len(duplicates),
        ambiguous_identical_crc_count=sum(x["identical_crc"] for x in duplicates),
        ambiguous_conflicting_crc_count=sum(not x["identical_crc"] for x in duplicates),
        candidate_non_vmlinux_provider_symbols=len(candidates),
        ambiguity_details=duplicates,
        missing_candidate_module_providers=cross_gki_modules[:80],
        top_missing_symbols=missing_ranked[:70],
        top_missing_consumer_modules=[dict(module=m, import_count=c) for m, c in missing_by_module.most_common(25)],
        all_unresolved_symbols=missing_ranked,
    )
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n")
    printable = {k:v for k,v in summary.items() if not isinstance(v, list)}
    printable["ambiguous_sample"] = duplicates[:8]
    printable["candidate_module_provider_sample"] = cross_gki_modules[:10]
    print(json.dumps(printable,indent=2,ensure_ascii=False))
    print("READ_ONLY: no eligibility, no boot, no stock mutation")

if __name__ == "__main__":
    main()
