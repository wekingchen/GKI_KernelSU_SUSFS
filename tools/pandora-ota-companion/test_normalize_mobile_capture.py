#!/usr/bin/env python3
"""Synthetic, no-device contract tests. Not a replacement for real pandora OTA validation."""
import io
import os
import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path
from normalize_mobile_capture import normalize

BASE = (
    "schema=pandora-ota-capture-v1\n"
    "source=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\n"
    "device=pandora\n"
    "ro.product.device=pandora\n"
    "ro.mi.os.version.incremental=OS4.0.6.0.XBLCNXM\n"
    "ro.boot.slot_suffix=_a\n"
    "slot=_a\n"
    "uname=6.12.70-android16-6-gabcdef01-4k\n"
)


def create_capture(path, manifest=BASE, include_dtbo=True, tar_kind="normal"):
    nested = io.BytesIO()
    with tarfile.open(fileobj=nested, mode="w") as stream:
        if tar_kind == "symlink":
            member = tarfile.TarInfo("vendor_dlkm/lib/modules/x.ko")
            member.type = tarfile.SYMTYPE
            member.linkname = "another.ko"
            stream.addfile(member)
        else:
            mod = b"\x7fELF" + b"A" * 512
            member = tarfile.TarInfo("vendor_dlkm/lib/modules/x.ko")
            member.size = len(mod)
            stream.addfile(member, io.BytesIO(mod))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr("manifest.txt", manifest)
        outer.writestr("kernel-release.txt", "6.12.70-android16-6-gabcdef01-4k\n")
        outer.writestr("oem-modules.tar", nested.getvalue())
        for part in ("boot", "init_boot", "vendor_boot", "dtbo"):
            if part == "dtbo" and not include_dtbo:
                continue
            outer.writestr(part + "_a.img", b"ANDROID!" + os.urandom(8192))


class MobileNormalizerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capture = self.root / "source.zip"
        self.output = self.root / "pandora-stock-OS4.0.6.0.XBLCNXM-_a-xm.zip"

    def tearDown(self):
        self.temp.cleanup()

    def test_expected_xm_contract_and_modules(self):
        create_capture(self.capture)
        result = normalize(self.capture, self.output)
        self.assertEqual(result["modules"], 1)
        self.assertEqual(result["build"], "OS4.0.6.0.XBLCNXM")
        with zipfile.ZipFile(self.output) as output:
            expected = {
                "boot.img", "init_boot.img", "vendor_boot.img", "dtbo.img",
                "README.txt", "SHA256SUMS.txt", "oem-modules.zip",
                "oem-modules-count.txt"
            }
            self.assertEqual(set(output.namelist()), expected)
            self.assertEqual(output.read("oem-modules-count.txt"), b"MODULE_COUNT=1\n")
            with zipfile.ZipFile(io.BytesIO(output.read("oem-modules.zip"))) as nested:
                self.assertEqual(nested.namelist(), ["vendor_dlkm/lib/modules/x.ko"])
            self.assertIn(b"ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK",
                          output.read("README.txt"))

    def test_missing_boot_fails_closed(self):
        create_capture(self.capture, include_dtbo=False)
        with self.assertRaisesRegex(ValueError, "missing or too-small"):
            normalize(self.capture, self.output)

    def test_wrong_device_fails_closed(self):
        create_capture(self.capture, manifest=BASE.replace(
            "ro.product.device=pandora", "ro.product.device=wrongdevice"))
        with self.assertRaisesRegex(ValueError, "not pandora"):
            normalize(self.capture, self.output)

    def test_wrong_slot_fails_closed(self):
        create_capture(self.capture, manifest=BASE.replace("slot=_a", "slot=_b"))
        with self.assertRaisesRegex(ValueError, "slot mismatch"):
            normalize(self.capture, self.output)

    def test_module_symlinks_fail_closed(self):
        create_capture(self.capture, tar_kind="symlink")
        with self.assertRaisesRegex(ValueError, "symlink"):
            normalize(self.capture, self.output)

    def test_existing_archive_never_overwritten(self):
        create_capture(self.capture)
        self.output.write_bytes(b"KEEP")
        with self.assertRaisesRegex(ValueError, "existing destination"):
            normalize(self.capture, self.output)
        self.assertEqual(self.output.read_bytes(), b"KEEP")


if __name__ == "__main__":
    unittest.main()
