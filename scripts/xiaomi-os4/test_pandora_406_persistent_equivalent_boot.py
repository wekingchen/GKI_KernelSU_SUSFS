#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "persistent_equiv", BASE / "build-pandora-406-persistent-equivalent-boot.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PersistentEquivalentCmdline(unittest.TestCase):
    def test_empty_stock_cmdline_gets_stable_order(self):
        self.assertEqual(
            mod.patch_persistent_cmdline(b""),
            b"module_blacklist=kernelsu pandora_rust_binder_eexist=1",
        )

    def test_preserves_existing_blacklist_and_appends_kernelsu_then_eexist(self):
        self.assertEqual(
            mod.patch_persistent_cmdline(b"foo=1 module_blacklist=bar,baz"),
            b"foo=1 module_blacklist=bar,baz,kernelsu pandora_rust_binder_eexist=1",
        )

    def test_idempotent(self):
        original = b"foo=1 module_blacklist=kernelsu pandora_rust_binder_eexist=1"
        self.assertEqual(mod.patch_persistent_cmdline(original), original)

    def test_conflicting_eexist_value_fails_closed(self):
        with self.assertRaises(SystemExit):
            mod.patch_persistent_cmdline(b"pandora_rust_binder_eexist=0")

    def test_duplicate_blacklist_fails_closed(self):
        with self.assertRaises(SystemExit):
            mod.patch_persistent_cmdline(
                b"module_blacklist=a module_blacklist=b")


if __name__ == "__main__":
    unittest.main()
