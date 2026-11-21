#!/usr/bin/env python3
"""Strict boot-v4 early module CPIO parser safety tests (mocked LZ4 decoder)."""
import importlib.util
from pathlib import Path
import struct
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    "early", Path(__file__).with_name("pandora_vendorboot_modules.py"))
early=importlib.util.module_from_spec(spec)
spec.loader.exec_module(early)


def record(name, data=b"", mode=0o100644):
    values=[1,mode,0,0,1,0,len(data),0,0,0,0,len(name)+1,0]
    header=b"070701"+b"".join(f"{value:08x}".encode() for value in values)
    blob=header+name.encode()+b"\0"
    blob+=b"\0"*((-len(blob))%4)
    blob+=data+b"\0"*((-len(data))%4)
    return blob


def image():
    data=bytearray(b"\0"*(8192+108))
    data[:8]=b"VNDRBOOT"
    for off,value in [(8,4),(12,4096),(24,12),(2096,2128),(2112,108),(2116,1),(2120,108)]:
        struct.pack_into("<I",data,off,value)
    data[4096:4108]=b"\x02\x21\x4c\x18"+b"\0"*8
    struct.pack_into("<III",data,8192,12,0,1)
    return bytes(data)


class VendorBootModules(unittest.TestCase):
    def extract(self,raw):
        with patch.object(early.subprocess,"run",return_value=types.SimpleNamespace(stdout=raw)) as proc:
            result=early.extract_vendor_boot_modules(image())
            proc.assert_called_once()
            self.assertEqual(proc.call_args.args[0], ["lz4","-dc"])
            return result

    def test_valid_early_provider(self):
        cpio=(record("lib/modules/smem.ko",b"\x7fELF")
              +record("lib/modules/qcom-scm.ko",b"\x7fELF2")
              +record("TRAILER!!!",b"",0))
        self.assertEqual(self.extract(cpio),[
            ("lib/modules/smem.ko",b"\x7fELF"),
            ("lib/modules/qcom-scm.ko",b"\x7fELF2")
        ])

    def test_path_traversal_rejected(self):
        cpio=record("lib/modules/../bad.ko",b"test")+record("TRAILER!!!",b"",0)
        with self.assertRaisesRegex(ValueError,"unsafe"):
            self.extract(cpio)

    def test_no_modules_rejected(self):
        with self.assertRaisesRegex(ValueError,"no verified .ko"):
            self.extract(record("TRAILER!!!",b"",0))

    def test_duplicate_module_rejected(self):
        cpio=(record("lib/modules/smem.ko",b"a")
              +record("lib/modules/smem.ko",b"a")
              +record("TRAILER!!!",b"",0))
        with self.assertRaisesRegex(ValueError,"duplicated"):
            self.extract(cpio)

    def test_vendor_boot_wrong_header_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid vendor_boot"):
            early.extract_vendor_boot_modules(b"BAD")

    def test_vendor_boot_wrong_compression_rejected(self):
        vb=bytearray(image())
        vb[4096:4100]=b"\x1f\x8b\0\0"
        with self.assertRaisesRegex(ValueError,"unsupported vendor ramdisk compression"):
            early.extract_vendor_boot_modules(bytes(vb))

if __name__=="__main__":
    unittest.main()
