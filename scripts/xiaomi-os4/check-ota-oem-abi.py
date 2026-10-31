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
        keys = [n.decode("ascii", "strict") for n in names[:-1].split(b"\0")]
        if len(keys) != len(raw) // 4:
            raise ValueError("extended names and CRC counts differ")
        for i, name in enumerate(keys):
            if not SYMBOL.fullmatch(name) or name in found:
                raise ValueError("invalid or duplicate extended CRC symbol")
            found[name] = struct.unpack_from("<I", raw, i * 4)[0]
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
            total_imports = 0
            for member in files:
                name = member.filename
                try:
                    if ".." in name.split("/") or member.file_size > MAX_MODULE:
                        raise ValueError("unsafe OEM module entry")
                    b = unpack_module(oem_zip.read(member), name)
                    sections = elf_sections(b)
                    vermagic = module_vermagic(sections)
                    if vermagic != release:
                        raise ValueError("vermagic mismatch: " + vermagic)
                    imported = imported_versions(sections)
                    total_imports += len(imported)
                    for symbol, expected_crc in imported.items():
                        if symbol not in exports:
                            report["unresolved_kernel_imports"].append(f"{name}:{symbol}")
                        elif exports[symbol] != expected_crc:
                            report["crc_mismatches"].append(f"{name}:{symbol}")
                except Exception as exc:
                    report["failed_modules"].append({"name": name, "reason": str(exc)[:180]})
        report.update(stock_build=stock["build"], stock_input_sha256=stock["ota_source_id"],
                      candidate_commit=gki["candidate_commit"], kernel_release=release,
                      module_count=len(files), imports_checked=total_imports,
                      vmlinux_exports=len(exports), module_source="LIVE_OTA_MODULES_IN_XM_ZIP")
        if report["failed_modules"] or report["unresolved_kernel_imports"] or report["crc_mismatches"] or total_imports == 0:
            raise ValueError("OEM .ko version check has errors, unproven external providers or missing CRCs")
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
