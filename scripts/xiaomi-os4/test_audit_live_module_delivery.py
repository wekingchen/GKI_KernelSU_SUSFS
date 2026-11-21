#!/usr/bin/env python3
"""Static regressions for read-only Windows pandora module loader collector."""
import re
import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parent /
          "collect-pandora-live-module-delivery.cmd").read_text(encoding="utf-8")
COMMANDS = [x.strip().lower() for x in SOURCE.splitlines()
            if x.strip() and not x.strip().lower().startswith("rem ")]


class LiveLoaderCollector(unittest.TestCase):
    def test_read_only_adb_contract(self):
        calls = [x for x in COMMANDS if x.startswith("adb ") or
                 x.startswith("for /f") and "adb shell" in x]
        self.assertGreater(len(calls), 12)
        for line in calls:
            self.assertNotRegex(line, r"\badb\s+(?:push|pull|install|remount|reboot|root|disable-verity|shell\s+(?:mount|dd|rm|insmod|modprobe|setprop))\b")
        self.assertNotRegex("\n".join(COMMANDS), r"\bfastboot\s+(?:flash|boot|erase)\b")

    def test_source_identity_required(self):
        self.assertIn('if /i not "%device%"=="pandora"', "\n".join(COMMANDS))
        self.assertIn('if /i not "%osbuild%"=="os4.0.6.0.xblcnxm"', "\n".join(COMMANDS))
        self.assertIn('uid=0(root)', "\n".join(COMMANDS))

    def test_no_raw_cmdline_or_kallsyms_written(self):
        text = "\n".join(COMMANDS)
        self.assertIn('cat /proc/cmdline', text)
        self.assertIn('regex]::matches', text)
        self.assertNotIn('> "%out%\\cmdline', text)
        self.assertNotIn('cat /proc/kallsyms', text)
        self.assertIn('loaded-modules-redacted.txt', text)

    def test_partition_paths_not_conflated(self):
        text = "\n".join(COMMANDS)
        self.assertIn('/system_dlkm/lib/modules/6.12.69-', text)
        self.assertIn('/vendor_dlkm/lib/modules/zsmalloc.ko', text)
        self.assertIn('/system_dlkm/lib/modules/modules.load', text)
        self.assertIn('/vendor_dlkm/lib/modules/modules.load', text)
        self.assertIn('not proof of actual loaded elf contents', text)


if __name__ == "__main__":
    unittest.main()
