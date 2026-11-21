#!/usr/bin/env python3
"""Validate extended modversions CRC parsing without weakening the OTA ABI gate."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location(
    "abi", Path(__file__).with_name("check-ota-oem-abi.py"))
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)

class ExtendedModVersions(unittest.TestCase):
    def test_one_and_two_nul_terminators_have_the_same_two_symbols(self):
        crcs = struct.pack("<II", 0x11223344, 0x55667788)
        for trailer in (b"\0", b"\0\0"):
            self.assertEqual(
                abi.imported_versions({
                    "__version_ext_names": b"core_export\0vendor_export" + trailer,
                    "__version_ext_crcs": crcs,
                }),
                {"core_export": 0x11223344, "vendor_export": 0x55667788}
            )

    def test_empty_interior_name_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "empty extended CRC symbol"):
            abi.imported_versions({
                "__version_ext_names": b"first\0\0second\0",
                "__version_ext_crcs": struct.pack("<II", 1, 2),
            })

    def test_true_count_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "names and CRC counts differ"):
            abi.imported_versions({
                "__version_ext_names": b"first\0second\0\0",
                "__version_ext_crcs": struct.pack("<I", 1),
            })

    def test_excessive_padding_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "names padding"):
            abi.imported_versions({
                "__version_ext_names": b"first" + b"\0" * 32,
                "__version_ext_crcs": struct.pack("<I", 1),
            })


if __name__ == "__main__":
    unittest.main()
