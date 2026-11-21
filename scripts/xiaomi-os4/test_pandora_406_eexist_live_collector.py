#!/usr/bin/env python3
import re
import unittest
from pathlib import Path

SRC=(Path(__file__).resolve().parent/"collect-pandora-406-eexist-testboot.cmd").read_text(encoding="utf-8")
LOW=SRC.lower()

class Collector(unittest.TestCase):
    def test_read_only_contract(self):
        forbidden=[
            r"\badb\s+push\b", r"\badb\s+install\b", r"\badb\s+reboot\b",
            r"\bfastboot\s+(?:flash|boot|erase)\b", r"\binsmod\b", r"\bmodprobe\b",
            r"\bsu\s+-c\b", r"\bmount\s+-o\s+rw\b", r"\bdd\s+if=",
        ]
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern,LOW),pattern)

    def test_never_persists_raw_cmdline_or_kernel_log(self):
        self.assertIn("cat /proc/cmdline",LOW)
        self.assertIn("pandora_rust_binder_eexist=",LOW)
        self.assertNotIn('> "%out%\\cmdline',LOW)
        self.assertIn("logcat -b kernel -d",LOW)
        self.assertNotIn('> "%out%\\kernel-log',LOW)

    def test_expected_runtime_contract_is_observed(self):
        for needle in (
            "/sys/module/binder/parameters/impl",
            "/sys/module/rust_binder/initstate",
            "service check activity",
            "service check package",
            "loaded-modules-redacted.txt",
            "/sys/module/zsmalloc/notes/.note.gnu.build-id",
            "/sys/module/zram/notes/.note.gnu.build-id",
            "/sys/module/node_cache/notes/.note.gnu.build-id",
        ):
            self.assertIn(needle,LOW)

    def test_local_zip_only(self):
        self.assertIn("compress-archive",LOW)
        self.assertNotIn("adb push",LOW)

if __name__=="__main__":
    unittest.main()
