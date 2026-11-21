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
        self.assertIn('if /i not "%krel%"=="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"', "\n".join(COMMANDS))
        self.assertIn('uid=0(root)', "\n".join(COMMANDS))

    def test_no_raw_cmdline_or_kallsyms_written(self):
        text = "\n".join(COMMANDS)
        self.assertIn('cat /proc/cmdline', text)
        self.assertIn('regex]::matches', text)
        self.assertNotIn('> "%out%\\cmdline', text)
        self.assertNotIn('cat /proc/kallsyms', text)
        self.assertIn('loaded-modules-redacted.txt', text)

    def test_live_module_notes_only_hashed_from_sysfs(self):
        text = "\n".join(COMMANDS)
        for module in ("rust_binder", "zsmalloc", "zram", "node_cache"):
            self.assertIn("/sys/module/" + module + "/notes/.note.gnu.build-id", text)
        self.assertNotIn('adb shell su -c "insmod ', text)
        self.assertNotIn('adb shell su -c "modprobe ', text)
        self.assertNotIn('cat /sys/module/zsmalloc/notes/.note.gnu.build-id', text)

    def test_archive_is_local_only_and_optional(self):
        text = "\n".join(COMMANDS)
        self.assertIn('compress-archive -literalpath', text)
        self.assertIn('destinationpath', text)
        self.assertIn('evidence archive:', text)
        self.assertNotIn('adb push', text)

    def test_binder_runtime_state_is_read_only(self):
        text = "\n".join(COMMANDS)
        self.assertIn('/sys/module/binder/parameters/impl', text)
        self.assertIn('/sys/module/binder/parameters/active_impl', text)
        self.assertNotIn('echo rust > /sys/module/binder', text)
        self.assertNotIn('echo c > /sys/module/binder', text)

    def test_partition_paths_not_conflated(self):
        text = "\n".join(COMMANDS)
        self.assertIn('/system_dlkm/lib/modules/%krel%/modules.load', text)
        self.assertIn('/system_dlkm/lib/modules/%krel%/modules.dep', text)
        self.assertIn('/system_dlkm/lib/modules/%krel%/kernel/mm/zsmalloc.ko', text)
        self.assertIn('/vendor_dlkm/lib/modules/zsmalloc.ko', text)
        self.assertIn('/system_dlkm/lib/modules/modules.load', text)
        self.assertIn('/vendor_dlkm/lib/modules/modules.load', text)
        self.assertIn('not proof of actual loaded elf contents', text)


if __name__ == "__main__":
    unittest.main()
