#!/usr/bin/env python3
import hashlib
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/xiaomi-os4/repack-tested-fastboot-boot-v4.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("os4_repack", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def make_boot(kernel: bytes, signature: bytes = b"S" * 16384, cmdline: bytes = b"console=tty0") -> bytes:
    page = 4096
    header = bytearray(page)
    header[:8] = b"ANDROID!"
    struct.pack_into("<IIII", header, 8, len(kernel), 0, 0, 1584)
    struct.pack_into("<I", header, 40, 4)
    if len(cmdline) + 1 > 1536:
        raise ValueError("test cmdline too long")
    header[44:44 + len(cmdline)] = cmdline
    struct.pack_into("<I", header, 1580, len(signature))
    padding = b"\0" * (((len(kernel) + page - 1) // page * page) - len(kernel))
    return bytes(header) + kernel + padding + signature


class RepackFastbootBootV4Test(unittest.TestCase):
    def test_repack_preserves_header_and_suffix_and_replaces_kernel(self):
        mod = load_tool()
        old = b"old-" + b"x" * 7000 + mod.EXPECTED_TEMPLATE_RELEASE
        new = b"new-" + b"y" * 9000 + mod.EXPECTED_FEATURE_RELEASE
        signature = b"Q" * 16384
        mod.EXPECTED_TEMPLATE_KERNEL_SHA256 = hashlib.sha256(old).hexdigest()
        mod.EXPECTED_FEATURE_KERNEL_SHA256 = hashlib.sha256(new).hexdigest()

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            template = td / "template.img"
            image = td / "Image"
            output = td / "out.img"
            boot = make_boot(old, signature)
            mod.EXPECTED_TEMPLATE_BOOT_SHA256 = hashlib.sha256(boot).hexdigest()
            template.write_bytes(boot)
            image.write_bytes(new)

            with patch.object(sys, "argv", [str(SCRIPT), str(template), str(image), str(output)]):
                mod.main()

            data = output.read_bytes()
            self.assertEqual(data[:8], b"ANDROID!")
            self.assertEqual(struct.unpack_from("<I", data, 40)[0], 4)
            self.assertEqual(struct.unpack_from("<I", data, 8)[0], len(new))
            self.assertEqual(data[4096:4096 + len(new)], new)
            self.assertEqual(data[-len(signature):], signature)
            self.assertNotEqual(data[-64:-60], b"AVBf")
            cmdline = data[44:44 + 1536].split(b"\0", 1)[0]
            self.assertEqual(cmdline, b"console=tty0 module_blacklist=kernelsu")

    def test_existing_unreviewed_module_blacklist_is_rejected(self):
        mod = load_tool()
        old = b"old-" + b"x" * 7000 + mod.EXPECTED_TEMPLATE_RELEASE
        new = b"new-" + b"y" * 9000 + mod.EXPECTED_FEATURE_RELEASE
        mod.EXPECTED_TEMPLATE_KERNEL_SHA256 = hashlib.sha256(old).hexdigest()
        mod.EXPECTED_FEATURE_KERNEL_SHA256 = hashlib.sha256(new).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            template, image, output = td/"template.img", td/"Image", td/"out.img"
            boot = make_boot(old, cmdline=b"module_blacklist=foo")
            mod.EXPECTED_TEMPLATE_BOOT_SHA256 = hashlib.sha256(boot).hexdigest()
            template.write_bytes(boot)
            image.write_bytes(new)
            with patch.object(sys, "argv", [str(SCRIPT), str(template), str(image), str(output)]):
                with self.assertRaises(SystemExit):
                    mod.main()
            self.assertFalse(output.exists())

    def test_wrong_template_kernel_is_rejected(self):
        mod = load_tool()
        old = b"wrong-" + b"x" * 4000 + mod.EXPECTED_TEMPLATE_RELEASE
        new = b"new-" + b"y" * 5000 + mod.EXPECTED_FEATURE_RELEASE
        mod.EXPECTED_FEATURE_KERNEL_SHA256 = hashlib.sha256(new).hexdigest()

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            template = td / "template.img"
            image = td / "Image"
            output = td / "out.img"
            boot = make_boot(old)
            mod.EXPECTED_TEMPLATE_BOOT_SHA256 = hashlib.sha256(boot).hexdigest()
            template.write_bytes(boot)
            image.write_bytes(new)

            with patch.object(sys, "argv", [str(SCRIPT), str(template), str(image), str(output)]):
                with self.assertRaises(SystemExit):
                    mod.main()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
