#!/usr/bin/env python3
"""Read-only diagnostic of OEM module ABI data. Never marks a boot image eligible."""
import argparse
import collections
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location(
    "abi", Path(__file__).with_name("check-ota-oem-abi.py"))
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stock-zip", required=True, type=Path)
    p.add_argument("--symvers", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    exports = abi.symvers(args.symvers)
    releases = collections.Counter()
    parse_errors = collections.Counter()
    ext_shapes = collections.Counter()
    candidate_matches = 0
    candidate_mismatches = 0
    external_or_unlisted = 0
    total_imports = 0
    sample_mismatches = []
    sample_unknown = []
    sample_ext = []
    invalid_identifier_examples = []
    duplicate_symbol_examples = []
    duplicate_count = 0
    invalid_identifier_count = 0
    samples_errors = []
    with zipfile.ZipFile(args.stock_zip) as stock:
        with zipfile.ZipFile(io.BytesIO(stock.read("oem-modules.zip"))) as archive:
            members = [x for x in archive.infolist() if not x.is_dir()
                       and abi.KO_NAME.search(x.filename)]
            if not 1 <= len(members) <= abi.MAX_MODULES:
                raise ValueError("invalid module count")
            for member in members:
                name = member.filename
                if ".." in name.split("/") or member.file_size > abi.MAX_MODULE:
                    raise ValueError("unsafe OEM member")
                try:
                    s = abi.elf_sections(abi.unpack_module(archive.read(member), name))
                    releases[abi.module_vermagic(s)] += 1
                    if "__version_ext_names" in s or "__version_ext_crcs" in s:
                        n = s.get("__version_ext_names", b"")
                        c = s.get("__version_ext_crcs", b"")
                        shape = (len(n), n.count(b"\0"), len(c), len(c)//4,
                                 len(n)-len(n.rstrip(b"\0")))
                        ext_shapes[str(shape)] += 1
                        keys = [x.decode("ascii", "replace") for x in
                                n.rstrip(b"\\0").split(b"\\0")]
                        seen = set()
                        for key in keys:
                            if not abi.SYMBOL.fullmatch(key):
                                invalid_identifier_count += 1
                                if len(invalid_identifier_examples) < 25:
                                    invalid_identifier_examples.append(dict(module=name, symbol=key))
                            if key in seen:
                                duplicate_count += 1
                                if len(duplicate_symbol_examples) < 25:
                                    duplicate_symbol_examples.append(dict(module=name, symbol=key))
                            seen.add(key)
                        if len(sample_ext) < 12:
                            sample_ext.append(dict(name=name, names_bytes=len(n),
                              names_nul_count=n.count(b"\0"), crcs_bytes=len(c),
                              crcs_count=len(c)//4,
                              trailing_nuls=len(n)-len(n.rstrip(b"\0")),
                              first_names=[v.decode("ascii", "replace")
                                           for v in n.split(b"\0")[:4]]))
                    try:
                        imported = abi.imported_versions(s)
                    except Exception as exc:
                        parse_errors[str(exc)] += 1
                        if len(samples_errors) < 15:
                            samples_errors.append(dict(name=name,error=str(exc)))
                        continue
                    total_imports += len(imported)
                    for symbol, crc in imported.items():
                        if symbol not in exports:
                            external_or_unlisted += 1
                            if len(sample_unknown) < 10:
                                sample_unknown.append(dict(module=name, symbol=symbol))
                        elif exports[symbol] == crc:
                            candidate_matches += 1
                        else:
                            candidate_mismatches += 1
                            if len(sample_mismatches) < 15:
                                sample_mismatches.append(dict(module=name,symbol=symbol,
                                  OEM=f"{crc:08x}",GKI=f"{exports[symbol]:08x}"))
                except Exception as exc:
                    parse_errors[str(exc)] += 1
                    if len(samples_errors) < 15:
                        samples_errors.append(dict(name=name,error=str(exc)))
    result = dict(kind="DIAGNOSTIC_ONLY_NO_BOOT",module_count=len(members),
                  modules_by_vermagic=releases,parse_errors=parse_errors,
                  extended_shapes=ext_shapes,total_imports_decoded=total_imports,
                  kernel_import_crc_matches=candidate_matches,
                  kernel_import_crc_mismatches=candidate_mismatches,
                  external_or_unlisted_imports=external_or_unlisted,
                  sample_ext=sample_ext,sample_parse_errors=samples_errors,
                  invalid_identifier_count=invalid_identifier_count,
                  duplicate_count=duplicate_count,
                  sample_invalid_identifiers=invalid_identifier_examples,
                  sample_duplicate_symbols=duplicate_symbol_examples,
                  sample_kernel_mismatches=sample_mismatches,
                  sample_external_or_unlisted=sample_unknown)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in result.items()
        if not k.startswith("sample") and k!="extended_shapes"},indent=2,ensure_ascii=False))
    print("DIAGNOSTIC_ONLY_NO_BOOT",flush=True)


if __name__ == "__main__":
    main()
