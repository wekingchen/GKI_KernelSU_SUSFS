#!/usr/bin/env python3
"""No real-device boot, no GitHub release: hermetic ABI/testboot unit tests."""
from __future__ import annotations
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
from pathlib import Path

BASE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, BASE / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


abi = module("abi", "check-ota-oem-abi.py")
pack = module("pack", "package-ota-testboot-v4.py")
UNAME = "6.12.69-android16-6-synthetic-ci-4k"
SHA = lambda x: hashlib.sha256(x).hexdigest()


def make_elf(release=UNAME, crc=0x12345678, extended=False):
    sections = [
        (".modinfo", ("vermagic=" + release + " SMP preempt modversions aarch64\0").encode())
    ]
    if extended:
        sections += [("__version_ext_names", b"core_export\0"),
                     ("__version_ext_crcs", struct.pack("<I", crc))]
    else:
        sections.append(("__versions", struct.pack("<Q", crc) + b"core_export\0".ljust(56, b"\0")))
    names = b"\0.shstrtab\0"
    offs = {}
    for name, data in sections:
        offs[name] = len(names)
        names += name.encode() + b"\0"
    parts = [(".shstrtab", names)] + sections
    cursor = 64
    blob = bytearray(b"\0" * 64)
    headers = [(0,0,0,0,0,0,0,0,0,0)]
    for name, data in parts:
        offset = cursor
        blob += data
        cursor += len(data)
        headers.append((1 if name == ".shstrtab" else offs[name], 3 if name == ".shstrtab" else 1,
                        0, 0, offset, len(data), 0, 0, 1, 0))
    shoff = (len(blob) + 7)//8*8
    blob += b"\0"*(shoff-len(blob))
    for fields in headers:
        blob += struct.pack("<IIQQQQIIQQ", *fields)
    ident = b"\x7fELF" + bytes([2,1,1,0,0]) + b"\0"*7
    hdr = struct.pack("<16sHHIQQQIHHHHHH", ident,1,183,1,0,0,shoff,0,64,0,0,64,len(headers),1)
    blob[:64] = hdr
    return bytes(blob)


def make_boot(kernel, signature=0):
    head = bytearray(4096)
    head[:8] = b"ANDROID!"
    struct.pack_into("<I", head, 8, len(kernel))
    struct.pack_into("<I", head, 20, 1584)
    struct.pack_into("<I", head, 40, 4)
    struct.pack_into("<I", head, 1580, signature)
    return bytes(head) + kernel + b"\0"*8192


class ABIAndBootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name)
        self.kernel = UNAME.encode() + b"\0" + b"K"*8192
        self.boot = make_boot(self.kernel)
        self.input = self.d / "xm.zip"
        self.module_bytes = make_elf()
        self.mkzip(self.module_bytes)
        self.stock = {
            "status":"NEW_OTA_CANDIDATE", "source_provenance":"BOOT_KERNEL_MARKER_AND_README_AGREE",
            "kernel_marker_verified":True, "header_version":4,
            "build":"OS4.0.5.1.XBLCNXM", "kmi":"android16-6", "uname":UNAME,
            "stock_boot_sha256":SHA(self.boot), "ota_source_id":SHA(self.input.read_bytes())
        }
        self.gki = {"candidate_commit":"a"*40,"ota_source_id":self.stock["ota_source_id"]}
        self.meta = {
            "SOURCE_GKI_COMMIT":"a"*40,"STOCK_INPUT_SHA256":self.stock["ota_source_id"],
            "STOCK_BUILD":self.stock["build"],"STOCK_KMI":"android16-6",
            "KERNEL_RELEASE":UNAME,"IMAGE_SHA256":SHA(self.kernel)
        }
        self.write_json(self.d/"stock.json",self.stock)
        self.write_json(self.d/"gki.json",self.gki)
        (self.d/"meta.txt").write_text("".join(f"{k}={v}\n" for k,v in self.meta.items()))
        self.exports = self.d/"Module.symvers"
        self.exports.write_text("".join(
            f"0x{(0x12345678 if i==0 else 0x12345678+i):08x}\t{('core_export' if i==0 else 'other_'+str(i))}\tvmlinux\tEXPORT_SYMBOL\t\n"
            for i in range(110)
        ))
        (self.d/"Image").write_bytes(self.kernel)

    def write_json(self,p,obj):
        p.write_text(json.dumps(obj))
    def mkzip(self, mod, *, missing=False):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner,"w") as zipout:
            zipout.writestr("vendor_dlkm/test.ko",mod)
        with zipfile.ZipFile(self.input,"w") as zipout:
            zipout.writestr("boot.img",self.boot)
            if not missing:
                zipout.writestr("oem-modules.zip",inner.getvalue())
                zipout.writestr("oem-modules-count.txt","MODULE_COUNT=1\n")
    def check(self):
        return subprocess.run([sys.executable,str(BASE/"check-ota-oem-abi.py"),
                "--stock-zip",str(self.input),"--stock-report",str(self.d/"stock.json"),
                "--candidate-report",str(self.d/"gki.json"),"--metadata",str(self.d/"meta.txt"),
                "--symvers",str(self.exports),"--output",str(self.d/"abi.json")],
                capture_output=True,text=True)
    def runpack(self):
        return subprocess.run([sys.executable,str(BASE/"package-ota-testboot-v4.py"),
                "--stock-zip",str(self.input),"--stock-report",str(self.d/"stock.json"),
                "--abi-report",str(self.d/"abi.json"),"--metadata",str(self.d/"meta.txt"),
                "--candidate-image",str(self.d/"Image"),"--output",str(self.d/"testboot.img")],
                capture_output=True,text=True)
    def update_zip(self, *, mod=None, missing=False):
        self.mkzip(mod or self.module_bytes,missing=missing)
        self.stock["ota_source_id"] = SHA(self.input.read_bytes())
        self.gki["ota_source_id"] = self.stock["ota_source_id"]
        self.meta["STOCK_INPUT_SHA256"] = self.stock["ota_source_id"]
        self.write_json(self.d/"stock.json",self.stock)
        self.write_json(self.d/"gki.json",self.gki)
        (self.d/"meta.txt").write_text("".join(f"{k}={v}\n" for k,v in self.meta.items()))

    def test_parse_basic_and_extended_modversions(self):
        for flag in [False,True]:
            sections = abi.elf_sections(make_elf(extended=flag))
            self.assertEqual(abi.imported_versions(sections)["core_export"],0x12345678)
            self.assertEqual(abi.module_vermagic(sections),UNAME)

    def test_matching_modules_can_generate_only_testboot(self):
        self.assertEqual(self.check().returncode,0)
        gate=json.loads((self.d/"abi.json").read_text())
        self.assertTrue(gate["eligible_for_fastboot_boot"],gate)
        p=self.runpack()
        self.assertEqual(p.returncode,0,p.stderr)
        boot=(self.d/"testboot.img").read_bytes()
        self.assertEqual(len(boot),len(self.boot))
        self.assertEqual(boot[:8],b"ANDROID!")
        self.assertIn(b"module_blacklist=kernelsu",boot[:4096])
        self.assertEqual(boot[4096:4096+len(self.kernel)],self.kernel)

    def test_crc_mismatch_blocks_boot(self):
        self.update_zip(mod=make_elf(crc=0xabcdef98))
        self.check()
        gate=json.loads((self.d/"abi.json").read_text())
        self.assertFalse(gate["eligible_for_fastboot_boot"])
        self.assertTrue(gate["crc_mismatches"])
        self.assertNotEqual(self.runpack().returncode,0)
        self.assertFalse((self.d/"testboot.img").exists())

    def test_missing_oem_module_zip_blocks(self):
        self.update_zip(missing=True)
        self.check()
        gate=json.loads((self.d/"abi.json").read_text())
        self.assertFalse(gate["eligible_for_fastboot_boot"])
        self.assertNotEqual(self.runpack().returncode,0)

    def test_wrong_vermagic_blocks(self):
        self.update_zip(mod=make_elf(release="6.12.99-android16-6-other"))
        self.check()
        self.assertFalse(json.loads((self.d/"abi.json").read_text())["eligible_for_fastboot_boot"])

    def test_stock_signature_blocks_even_with_static_crc_pass(self):
        self.assertEqual(self.check().returncode,0)
        with zipfile.ZipFile(self.input,"r") as z:
            data={i.filename:z.read(i) for i in z.infolist()}
        modboot=make_boot(self.kernel,signature=1)
        data["boot.img"]=modboot
        with zipfile.ZipFile(self.input,"w") as z:
            for k,v in data.items():z.writestr(k,v)
        self.stock["stock_boot_sha256"]=SHA(modboot)
        self.stock["ota_source_id"]=SHA(self.input.read_bytes())
        self.meta["STOCK_INPUT_SHA256"]=self.stock["ota_source_id"]
        self.write_json(self.d/"stock.json",self.stock)
        (self.d/"meta.txt").write_text("".join(f"{k}={v}\n" for k,v in self.meta.items()))
        self.assertNotEqual(self.runpack().returncode,0)


if __name__ == "__main__":
    unittest.main()
