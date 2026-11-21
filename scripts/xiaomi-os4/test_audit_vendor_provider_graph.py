#!/usr/bin/env python3
"""Hermetic tests: real ELF __kcrctab provider CRC and pinned OEM short vermagic."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("abi", BASE / "check-ota-oem-abi.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)
FULL = "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
SHORT = "6.12.69-android16-6-4k"
CORE = 0x12345678
VENDOR = 0x84561234
SHA = lambda x: hashlib.sha256(x).hexdigest()


def elf(imports=None, exports=None, release=FULL):
    imports = imports if imports is not None else {"core_export": CORE}
    exports = exports if exports is not None else {}
    parts = [
        (".modinfo", f"vermagic={release} SMP preempt modversions aarch64\0".encode()),
        ("__version_ext_names", b"\0".join(k.encode() for k in imports) + b"\0\0"),
        ("__version_ext_crcs", b"".join(struct.pack("<I", v) for v in imports.values())),
    ]
    if exports:
        parts.extend([
            ("__ksymtab", b"\0" * (16 * len(exports))),
            ("__kcrctab", b"".join(struct.pack("<I", v) for v in exports.values())),
        ])
    names = b"\0.shstrtab\0"
    name_offsets = {}
    for section, data in parts + [(".strtab", b""), (".symtab", b"")]:
        name_offsets[section] = len(names)
        names += section.encode() + b"\0"
    symbol_names = b"\0"
    symbol_offsets = {}
    sym_entries = [b"\0" * 24]  # Undefined ELF symbol.
    section_index = {name: n for n, (name, _) in enumerate(parts, 2)}
    if exports:
        for n, symbol in enumerate(exports):
            for prefix, index, size, value in (
                ("__ksymtab_", section_index["__ksymtab"], 16, n * 16),
                ("__crc_", section_index["__kcrctab"], 4, n * 4),
            ):
                name = prefix + symbol
                symbol_offsets[name] = len(symbol_names)
                symbol_names += name.encode() + b"\0"
                sym_entries.append(struct.pack(
                    "<IBBHQQ", symbol_offsets[name], 0x11, 0, index, value, size))
    parts += [
        (".strtab", symbol_names),
        (".symtab", b"".join(sym_entries)),
    ]
    blob = bytearray(b"\0" * 64)
    all_parts = [(".shstrtab", names)] + parts
    headers = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for section, content in all_parts:
        offset = len(blob)
        blob.extend(content)
        typ = 3 if section.endswith("strtab") else 2 if section == ".symtab" else 1
        link = section_index.get(".strtab", 0) if section == ".symtab" else 0
        # .strtab index is 2 + len(initial parts), not the existing section_index.
        if section == ".symtab":
            link = 2 + len(parts) - 2
        headers.append((name_offsets[section] if section != ".shstrtab" else 1,
                        typ, 0, 0, offset, len(content), link, 0,
                        8 if section == ".symtab" else 1,
                        24 if section == ".symtab" else 0))
    table_off = (len(blob) + 7) // 8 * 8
    blob.extend(b"\0" * (table_off - len(blob)))
    for row in headers:
        blob.extend(struct.pack("<IIQQQQIIQQ", *row))
    ident = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + b"\0" * 7
    blob[:64] = struct.pack("<16sHHIQQQIHHHHHH", ident, 1, 183, 1,
                            0, 0, table_off, 0, 64, 0, 0, 64, len(headers), 1)
    return bytes(blob)


class OEMProviderGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_read_crc_from_provider_section(self):
        data = elf(exports={"vendor_export": VENDOR})
        self.assertEqual(abi.module_export_crcs(data), {"vendor_export": VENDOR})

    def test_stock_short_vermagic_is_exactly_pinned(self):
        self.assertEqual(abi.compatible_vermagic(FULL, FULL), "exact")
        self.assertEqual(abi.compatible_vermagic(SHORT, FULL), "stock_short")
        for invalid in (
            "6.12.68-android16-6-4k", "6.12.69-android16-7-4k",
            "6.12.69-android16-6-16k", "6.12.69-android16-6-custom-4k",
            "6.12.69-android16-6-4k-evil",
        ):
            with self.assertRaisesRegex(ValueError, "vermagic mismatch"):
                abi.compatible_vermagic(invalid, FULL)

    def run_gate(self, *, expected_vendor_crc=VENDOR, include_provider=True,
                 duplicate_provider=False, consumer_release=SHORT):
        members = {
            "vendor_dlkm/consumer.ko": elf(
                imports={"core_export": CORE, "vendor_export": expected_vendor_crc},
                exports={}, release=consumer_release)
        }
        if include_provider:
            members["vendor_dlkm/provider.ko"] = elf(
                imports={"core_export": CORE}, exports={"vendor_export": VENDOR})
        if duplicate_provider:
            members["vendor_dlkm/duplicate_provider.ko"] = elf(
                imports={"core_export": CORE}, exports={"vendor_export": VENDOR})
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            for name, data in members.items():
                z.writestr(name, data)
        stockzip = self.path / "xm.zip"
        with zipfile.ZipFile(stockzip, "w") as z:
            z.writestr("oem-modules.zip", inner.getvalue())
            z.writestr("oem-modules-count.txt", f"MODULE_COUNT={len(members)}\n")
        identity = SHA(stockzip.read_bytes())
        stock = dict(status="NEW_OTA_CANDIDATE",
                     source_provenance="BOOT_KERNEL_MARKER_AND_README_AGREE",
                     kernel_marker_verified=True, header_version=4,
                     build="OS4.0.6.0.XBLCNXM", kmi="android16-6",
                     uname=FULL, ota_source_id=identity)
        gki = dict(candidate_commit="a" * 40, ota_source_id=identity)
        meta = dict(SOURCE_GKI_COMMIT="a" * 40, STOCK_INPUT_SHA256=identity,
                    STOCK_BUILD=stock["build"], STOCK_KMI=stock["kmi"], KERNEL_RELEASE=FULL)
        (self.path / "stock.json").write_text(json.dumps(stock))
        (self.path / "gki.json").write_text(json.dumps(gki))
        (self.path / "meta.txt").write_text(
            "".join(f"{k}={v}\n" for k, v in meta.items()))
        (self.path / "symvers.txt").write_text("".join(
            f"0x{(CORE if i == 0 else CORE+i):08x}\t"
            f"{('core_export' if i == 0 else 'other_'+str(i))}\t"
            "vmlinux\tEXPORT_SYMBOL\t\n" for i in range(110)))
        output = self.path / "report.json"
        p = subprocess.run([sys.executable, str(BASE / "check-ota-oem-abi.py"),
            "--stock-zip", str(stockzip), "--stock-report", str(self.path / "stock.json"),
            "--candidate-report", str(self.path / "gki.json"),
            "--metadata", str(self.path / "meta.txt"),
            "--symvers", str(self.path / "symvers.txt"), "--output", str(output)],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return json.loads(output.read_text())

    def test_correct_oem_provider_crc_passes(self):
        report = self.run_gate()
        self.assertTrue(report["eligible_for_fastboot_boot"], report)
        self.assertEqual(report["oem_imports_checked"], 1)
        self.assertEqual(report["core_imports_checked"], 2)
        self.assertEqual(report["short_vermagic_modules"], 1)

    def test_bad_vendor_crc_fails(self):
        report = self.run_gate(expected_vendor_crc=VENDOR ^ 1)
        self.assertFalse(report["eligible_for_fastboot_boot"])
        self.assertTrue(report["crc_mismatches"])

    def test_absent_provider_fails(self):
        report = self.run_gate(include_provider=False)
        self.assertFalse(report["eligible_for_fastboot_boot"])
        self.assertTrue(report["unresolved_kernel_imports"])

    def test_duplicate_provider_fails(self):
        report = self.run_gate(duplicate_provider=True)
        self.assertFalse(report["eligible_for_fastboot_boot"])
        self.assertTrue(report["ambiguous_providers"])

    def test_bad_short_vermagic_fails(self):
        report = self.run_gate(consumer_release="6.12.68-android16-6-4k")
        self.assertFalse(report["eligible_for_fastboot_boot"])
        self.assertTrue(report["failed_modules"])


if __name__ == "__main__":
    unittest.main()
