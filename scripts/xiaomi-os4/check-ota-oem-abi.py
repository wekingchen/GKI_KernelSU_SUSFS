#!/usr/bin/env python3
"""Fail-closed, READ-ONLY OEM .ko import CRC/vermagic audit against GKI Module.symvers.
Does not claim full ABI or boot compatibility: users must still fastboot boot to test.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import lzma
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

KO_NAME = re.compile(r"\.ko(?:\.zst|\.xz|\.gz)?$", re.I)
ELF64_HDR = struct.Struct("<16sHHIQQQIHHHHHH")
SHDR = struct.Struct("<IIQQQQIIQQ")
MAX_MODULE = 40 * 1024 * 1024
MAX_COMPRESSED_ARCHIVE = 600 * 1024 * 1024
MAX_MODULES = 4096
SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unpack_module(data: bytes, name: str) -> bytes:
    if name.endswith(".xz"):
        data = lzma.decompress(data, format=lzma.FORMAT_XZ, memlimit=250 * 1024 * 1024)
    elif name.endswith(".gz"):
        import gzip
        data = gzip.decompress(data)
    elif name.endswith(".zst"):
        proc = subprocess.run(["zstd", "-q", "-d", "-c", "--"], input=data,
                              capture_output=True, check=False)
        if proc.returncode:
            raise ValueError("zstd decompression failed")
        data = proc.stdout
    if len(data) > MAX_MODULE:
        raise ValueError("decompressed .ko exceeds 40 MiB")
    return data


def elf_sections(data: bytes) -> dict[str, bytes]:
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ValueError("requires ELF64 little-endian kernel module")
    fields = ELF64_HDR.unpack_from(data)
    e_machine, off, entsize, count, stridx = fields[2], fields[6], fields[11], fields[12], fields[13]
    if e_machine != 183 or entsize != 64 or count < 1 or count > 4096 or stridx >= count:
        raise ValueError("unexpected ELF arm64 section header")
    if off + count * entsize > len(data):
        raise ValueError("truncated section header table")
    sections = [SHDR.unpack_from(data, off + i * entsize) for i in range(count)]
    def block(header):
        offset, length = header[4], header[5]
        if offset + length > len(data):
            raise ValueError("section extends past end of ELF")
        return data[offset:offset+length]
    names = block(sections[stridx])
    result = {}
    for h in sections:
        name_off = h[0]
        if name_off >= len(names):
            raise ValueError("bad ELF string table index")
        end = names.find(b"\0", name_off)
        if end < 0:
            raise ValueError("unterminated ELF section name")
        name = names[name_off:end].decode("ascii", "strict")
        if name in result:
            raise ValueError("duplicate ELF section")
        if h[1] != 8:  # SHT_NOBITS doesn't occupy file bytes
            result[name] = block(h)
    return result


def imported_versions(sections: dict[str, bytes]) -> dict[str, int]:
    found = {}
    if "__versions" in sections:
        data = sections["__versions"]
        if len(data) % 64:
            raise ValueError("basic modversions records not 64 bytes")
        for off in range(0, len(data), 64):
            crc = struct.unpack_from("<I", data, off)[0]
            name = data[off+8:off+64].split(b"\0", 1)[0].decode("ascii", "strict")
            if not SYMBOL.fullmatch(name) or name in found:
                raise ValueError("invalid or duplicate basic CRC symbol")
            found[name] = crc
    if "__version_ext_names" in sections or "__version_ext_crcs" in sections:
        if "__version_ext_names" not in sections or "__version_ext_crcs" not in sections:
            raise ValueError("incomplete extended modversions sections")
        names = sections["__version_ext_names"]
        raw = sections["__version_ext_crcs"]
        if not names.endswith(b"\0") or len(raw) % 4:
            raise ValueError("invalid extended modversions data")
        # The extended names section may include NUL alignment padding after
        # its final terminated name. Padding is not a phantom CRC symbol.
        unpadded = names.rstrip(b"\0")
        padding = len(names) - len(unpadded)
        if not unpadded or not 1 <= padding <= 8:
            raise ValueError("invalid extended modversions names padding")
        fields = unpadded.split(b"\0")
        if not all(fields):
            raise ValueError("empty extended CRC symbol")
        keys = [n.decode("ascii", "strict") for n in fields]
        if len(keys) != len(raw) // 4:
            raise ValueError("extended names and CRC counts differ")
        ext_seen = set()
        for i, name in enumerate(keys):
            if not SYMBOL.fullmatch(name) or name in ext_seen:
                raise ValueError("invalid or duplicate extended CRC symbol")
            ext_seen.add(name)
            crc = struct.unpack_from("<I", raw, i * 4)[0]
            # Linux may include the same symbol in both basic and extended
            # tables. Accept it only if its CRC is byte-for-byte identical.
            if name in found and found[name] != crc:
                raise ValueError("conflicting basic/extended CRC for " + name)
            found[name] = crc
    if not found:
        raise ValueError("module has no basic or extended modversions")
    return found


def module_vermagic(sections: dict[str, bytes]) -> str:
    for field in sections.get(".modinfo", b"").split(b"\0"):
        if field.startswith(b"vermagic="):
            return field[len(b"vermagic="):].decode("ascii", "strict").split(" ", 1)[0]
    raise ValueError("module has no vermagic")


def symvers(path: Path) -> dict[str, int]:
    result = {}
    for line in path.read_text().splitlines():
        row = line.split()
        if len(row) < 4:
            raise ValueError("malformed Module.symvers line")
        crc, name, provider = row[:3]
        if provider != "vmlinux":
            continue  # Core-kernel ABI only; external module providers need separate proof
        if not re.fullmatch(r"0x[0-9a-fA-F]{8}", crc) or not SYMBOL.fullmatch(name):
            raise ValueError("bad kernel export CRC")
        value = int(crc, 16)
        if name in result and result[name] != value:
            raise ValueError("duplicate vmlinux export")
        result[name] = value
    if len(result) < 100:
        raise ValueError("too few GKI kernel exports")
    return result



# ELF symbol descriptors for exported module CRCs (separate from import CRC tables).
SYMENT = struct.Struct("<IBBHQQ")
STRICT_SHORT_VERMAGIC = re.compile(
    r"^([0-9]+\.[0-9]+\.[0-9]+-android[0-9]+-[0-9]+)-g[0-9a-f]+-abogki[0-9]+(-4k)$"
)


def compatible_vermagic(module_release: str, full_release: str) -> str:
    """Return exact/stock-short form; never accept an arbitrary KMI prefix."""
    if module_release == full_release:
        return "exact"
    match = STRICT_SHORT_VERMAGIC.fullmatch(full_release)
    if match and module_release == match.group(1) + match.group(2):
        return "stock_short"
    raise ValueError("vermagic mismatch: " + module_release)


def module_export_crcs(data: bytes) -> dict[str, int]:
    """Read __ksymtab symbol exports and their actual __kcrctab CRC bytes.

    The ELF symbol __crc_<name> st_value is the relative offset into
    the named __kcrctab section for ET_REL modules. Never derive a
    provider's CRC from a consumer's expected CRC or a symbol name.
    """
    fields = ELF64_HDR.unpack_from(data)
    offset, entsize, count = fields[6], fields[11], fields[12]
    if data[:4] != b"\x7fELF" or data[4:6] != b"\x02\x01" or fields[1] != 1:
        raise ValueError("module provider must be ELF64 arm64 ET_REL")
    if entsize != 64 or count < 1 or count > 4096 or offset + count * entsize > len(data):
        raise ValueError("invalid provider section headers")
    headers = [SHDR.unpack_from(data, offset + i * entsize) for i in range(count)]
    symbol_tables = [h for h in headers if h[1] == 2]  # SHT_SYMTAB
    if not symbol_tables:
        if any(name.startswith("__ksymtab") for name in elf_sections(data)):
            raise ValueError("export sections without ELF symbol table")
        return {}
    if len(symbol_tables) != 1:
        raise ValueError("ambiguous ELF symbol table")
    table = symbol_tables[0]
    if table[9] != SYMENT.size or table[5] % SYMENT.size or table[6] >= count:
        raise ValueError("invalid ELF symbol entries")
    strings = headers[table[6]]
    if strings[1] != 3 or strings[4] + strings[5] > len(data):  # SHT_STRTAB
        raise ValueError("bad ELF symbol string table")
    names = data[strings[4]:strings[4]+strings[5]]
    if table[4] + table[5] > len(data):
        raise ValueError("bad ELF symbol table bounds")
    # Find section names through the validated ELF section header index.
    str_header = headers[fields[13]]
    shnames = data[str_header[4]:str_header[4] + str_header[5]]
    exports: set[str] = set()
    crc_locations: dict[str, tuple[int, int]] = {}
    for off in range(table[4], table[4] + table[5], SYMENT.size):
        name_offset, info, _other, index, value, _size = SYMENT.unpack_from(data, off)
        if index == 0 or name_offset >= len(names):
            continue
        end = names.find(b"\0", name_offset)
        if end < 0:
            raise ValueError("unterminated ELF symbol name")
        identifier = names[name_offset:end].decode("ascii", "strict")
        if info & 0xf == 3:  # STT_SECTION, not an actual exported function
            continue
        if identifier.startswith("__ksymtab_"):
            symbol = identifier[len("__ksymtab_"):]
            if symbol in ("gpl", "strings", "unused", "unused_gpl", "unused_gpl_future"):
                continue
            if not SYMBOL.fullmatch(symbol) or symbol in exports:
                raise ValueError("invalid or duplicate OEM provider export")
            exports.add(symbol)
        elif identifier.startswith("__crc_"):
            symbol = identifier[len("__crc_"):]
            if not SYMBOL.fullmatch(symbol) or symbol in crc_locations:
                raise ValueError("duplicate or invalid OEM provider CRC symbol")
            if index >= count or headers[index][1] != 1:
                raise ValueError("provider CRC must reside in a file-backed section")
            h = headers[index]
            if h[0] >= len(shnames):
                raise ValueError("invalid provider CRC section name")
            section_name = shnames[h[0]:shnames.find(b"\0", h[0])].decode("ascii", "strict")
            if not section_name.startswith("__kcrctab") or value + 4 > h[5]:
                raise ValueError("provider CRC not in __kcrctab bounds")
            crc_locations[symbol] = (h[4] + value, index)
    resolved = {}
    for symbol in exports:
        if symbol not in crc_locations:
            raise ValueError("missing provider CRC for " + symbol)
        crc_off, _index = crc_locations[symbol]
        if crc_off + 4 > len(data):
            raise ValueError("truncated provider CRC")
        resolved[symbol] = struct.unpack_from("<I", data, crc_off)[0]
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-zip", type=Path, required=True)
    parser.add_argument("--stock-report", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--symvers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    report = {"schema": 1, "gate": "BLOCKED", "eligible_for_fastboot_boot": False,
              "flashable": False, "lkg_unchanged": True, "failed_modules": [],
              "unresolved_kernel_imports": [], "crc_mismatches": [],
              "reason": "unverified"}
    try:
        stock = json.loads(a.stock_report.read_text())
        gki = json.loads(a.candidate_report.read_text())
        metadata = dict(line.split("=", 1) for line in a.metadata.read_text().splitlines() if "=" in line)
        if stock.get("status") != "NEW_OTA_CANDIDATE" or stock.get("source_provenance") != "BOOT_KERNEL_MARKER_AND_README_AGREE":
            raise ValueError("stock OTA not independently identity-marked")
        if not stock.get("kernel_marker_verified") or stock.get("header_version") != 4:
            raise ValueError("stock boot has no recognized kernel marker / v4 header")
        if gki.get("ota_source_id") != stock.get("ota_source_id") or metadata.get("STOCK_INPUT_SHA256") != stock.get("ota_source_id"):
            raise ValueError("stock and GKI build input provenance mismatch")
        if metadata.get("SOURCE_GKI_COMMIT") != gki.get("candidate_commit"):
            raise ValueError("GKI source commit differs from compiled candidate")
        if metadata.get("STOCK_BUILD") != stock.get("build") or metadata.get("STOCK_KMI") != stock.get("kmi"):
            raise ValueError("GKI candidate metadata not from matching OTA")
        release = metadata.get("KERNEL_RELEASE", "")
        if not release or release != stock.get("uname"):
            raise ValueError("GKI candidate kernel release does not equal OEM module vermagic release")
        exports = symvers(a.symvers)
        if sha(a.stock_zip.read_bytes()) != stock.get("ota_source_id"):
            raise ValueError("stock zip bytes changed after initial audit")
        with zipfile.ZipFile(a.stock_zip) as stock_zip:
            oem_members = [i for i in stock_zip.infolist() if i.filename.rsplit("/", 1)[-1] == "oem-modules.zip"]
            count_member = [i for i in stock_zip.infolist() if i.filename.rsplit("/", 1)[-1] == "oem-modules-count.txt"]
            if len(oem_members) != 1 or len(count_member) != 1:
                raise ValueError("new OTA must contain OEM/GKI modules and count manifest")
            if oem_members[0].file_size > MAX_COMPRESSED_ARCHIVE:
                raise ValueError("OEM module archive oversized")
            wanted_count = int(stock_zip.read(count_member[0]).decode("ascii", "strict").strip().split("=", 1)[1])
            raw = stock_zip.read(oem_members[0])
            if not (1 <= wanted_count <= MAX_MODULES):
                raise ValueError("invalid OEM modules manifest count")
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as oem_zip:
            files = [i for i in oem_zip.infolist() if not i.is_dir() and KO_NAME.search(i.filename)]
            if len(files) != wanted_count:
                raise ValueError("OEM module inventory incomplete or count mismatch")
            # First parse every module: complete provider inventory BEFORE resolving
            # any consumer. This handles modules regardless of ZIP ordering.
            records = []
            providers = {}
            short_vermagic_modules = 0
            full_vermagic_modules = 0
            for member in files:
                name = member.filename
                try:
                    if ".." in name.split("/") or member.file_size > MAX_MODULE:
                        raise ValueError("unsafe OEM module entry")
                    data = unpack_module(oem_zip.read(member), name)
                    sections = elf_sections(data)
                    mode = compatible_vermagic(module_vermagic(sections), release)
                    if mode == "stock_short":
                        short_vermagic_modules += 1
                    else:
                        full_vermagic_modules += 1
                    imported = imported_versions(sections)
                    provided = module_export_crcs(data)
                    records.append((name, imported))
                    for symbol, crc in provided.items():
                        providers.setdefault(symbol, []).append((name, crc))
                except Exception as exc:
                    report["failed_modules"].append({"name": name, "reason": str(exc)[:180]})
            total_imports = 0
            core_imports = 0
            oem_imports = 0
            ambiguous = []
            dependencies = {}
            for name, imported in records:
                total_imports += len(imported)
                for symbol, expected_crc in imported.items():
                    candidates = providers.get(symbol, [])
                    if symbol in exports:
                        # Any duplicate provider is ambiguous even if CRCs agree.
                        if candidates:
                            ambiguous.append(f"{name}:{symbol}:vmlinux+OEM")
                            continue
                        core_imports += 1
                        if exports[symbol] != expected_crc:
                            report["crc_mismatches"].append(f"{name}:{symbol}:vmlinux")
                    elif len(candidates) == 1:
                        provider, crc = candidates[0]
                        if provider == name:
                            ambiguous.append(f"{name}:{symbol}:self-provider")
                            continue
                        oem_imports += 1
                        edge = provider + " -> " + name
                        dependencies[edge] = dependencies.get(edge, 0) + 1
                        if crc != expected_crc:
                            report["crc_mismatches"].append(f"{name}:{symbol}:{provider}")
                    elif len(candidates) > 1:
                        ambiguous.append(f"{name}:{symbol}:multiple-OEM-providers")
                    else:
                        report["unresolved_kernel_imports"].append(f"{name}:{symbol}")
            report["ambiguous_providers"] = ambiguous
            report["provider_graph_edge_count"] = len(dependencies)
            report["provider_graph_example_edges"] = [
                {"edge": edge, "imports": count}
                for edge, count in list(sorted(dependencies.items()))[:40]
            ]
        report.update(stock_build=stock["build"], stock_input_sha256=stock["ota_source_id"],
                      candidate_commit=gki["candidate_commit"], kernel_release=release,
                      module_count=len(files), imports_checked=total_imports,
                      core_imports_checked=core_imports, oem_imports_checked=oem_imports,
                      short_vermagic_modules=short_vermagic_modules,
                      full_vermagic_modules=full_vermagic_modules,
                      verified_oem_export_symbols=sum(len(v) for v in providers.values()),
                      vmlinux_exports=len(exports), module_source="LIVE_OTA_MODULES_IN_XM_ZIP")
        if (report["failed_modules"] or report["unresolved_kernel_imports"]
                or report["crc_mismatches"] or report["ambiguous_providers"]
                or total_imports == 0 or core_imports == 0):
            raise ValueError("OEM .ko CRC/vermagic/provider graph has errors or unresolved imports")
        report.update(gate="CRC_AND_VERMAGIC_MATCH_CANDIDATE", eligible_for_fastboot_boot=True,
                      reason="Static module version CRC check passed; OEM boot still needs human fastboot boot and runtime validation")
    except Exception as exc:
        report["reason"] = str(exc)[:300]
        print("::warning::OTA OEM ABI gate BLOCKED: " + report["reason"])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print("OTA_OEM_MODULE_GATE=" + report["gate"])
    print("OTA_TEST_BOOT_ELIGIBLE=" + str(report["eligible_for_fastboot_boot"]).lower())
    # A blocked compatibility report is valid evidence; no boot build is allowed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
