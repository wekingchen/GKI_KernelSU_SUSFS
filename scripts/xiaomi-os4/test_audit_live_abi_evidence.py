#!/usr/bin/env python3
"""Static safety regression for Windows read-only pandora ABI evidence collection."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/xiaomi-os4/collect-pandora-live-abi-evidence.cmd"


class ReadOnlyLiveABICollection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents = SCRIPT.read_text(encoding="utf-8")

    def test_pandora_and_root_verified_before_collection(self):
        content = self.contents
        self.assertIn('ro.product.device', content)
        self.assertIn('"%DEVICE%"=="pandora"', content)
        self.assertIn('uid=0(root)', content)
        self.assertLess(content.index('uid=0(root)'), content.index('/proc/modules'))

    def test_provenance_is_observed_not_inferred(self):
        for item in ('ro.mi.os.version.incremental', 'ro.boot.slot_suffix',
                     'uname -r', '/proc/modules', 'modules.load', '/proc/kallsyms'):
            self.assertIn(item, self.contents)

    def test_no_kernel_addresses_are_collected(self):
        self.assertIn("awk '{print $3}' /proc/kallsyms", self.contents)
        self.assertIn('findstr /C:"qcom_smem_get"', self.contents)
        self.assertIn('kernel-symbol-names.txt', self.contents)

    def test_no_device_mutations(self):
        lines = [x.strip().lower() for x in self.contents.splitlines()
                 if x.strip() and not x.strip().lower().startswith('rem ')]
        code = "\n".join(lines)
        for command in ('fastboot ', 'adb push ', 'adb pull ', 'adb reboot ',
                        'adb install ', 'adb sideload ', 'adb shell mount ',
                        'adb shell umount ', 'adb shell setprop ',
                        'dd if=', 'rm -rf ', 'reboot -p', '/dev/block/by-name/'):
            self.assertNotIn(command, code)


if __name__ == "__main__":
    unittest.main()
