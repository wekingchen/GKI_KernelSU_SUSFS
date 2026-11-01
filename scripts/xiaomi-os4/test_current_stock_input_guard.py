#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "current_stock_guard", HERE / "guard-current-stock-input.py")
GUARD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(GUARD)


def stock_zip(path: Path, build: str | None, payload: bytes = b"boot") -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("boot.img", payload)
        if build is not None:
            archive.writestr("README.txt", "device=pandora\nbuild=" + build + "\n")


class CurrentStockInputGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.current = self.base / "current.zip"
        self.incoming = self.base / "incoming.zip"
        self.fallback = "OS4.0.5.0.XBLCNXM"

    def test_forward_build_is_allowed_against_current_release(self):
        stock_zip(self.current, "OS4.0.7.0.XBLCNXM", b"current")
        stock_zip(self.incoming, "OS4.0.8.0.XBLCNXM", b"incoming")
        decision, current = GUARD.decide(
            self.current, self.incoming, "OS4.0.8.0.XBLCNXM",
            self.fallback, "NEW_OTA_CANDIDATE")
        self.assertEqual("FORWARD", decision)
        self.assertEqual("OS4.0.7.0.XBLCNXM", current)

    def test_historical_build_cannot_roll_back_current_release(self):
        stock_zip(self.current, "OS4.0.7.0.XBLCNXM", b"current")
        stock_zip(self.incoming, "OS4.0.6.0.XBLCNXM", b"historical")
        with self.assertRaises(SystemExit) as ctx:
            GUARD.decide(self.current, self.incoming, "OS4.0.6.0.XBLCNXM",
                         self.fallback, "NEW_OTA_CANDIDATE")
        self.assertIn("older than current fixed stock-input", str(ctx.exception))

    def test_same_current_archive_is_already_current(self):
        stock_zip(self.current, "OS4.0.7.0.XBLCNXM", b"same")
        self.incoming.write_bytes(self.current.read_bytes())
        decision, current = GUARD.decide(
            self.current, self.incoming, "OS4.0.7.0.XBLCNXM",
            self.fallback, "NEW_OTA_CANDIDATE")
        self.assertEqual(("ALREADY_CURRENT", "OS4.0.7.0.XBLCNXM"),
                         (decision, current))

    def test_same_current_build_with_changed_bytes_requires_review(self):
        stock_zip(self.current, "OS4.0.7.0.XBLCNXM", b"one")
        stock_zip(self.incoming, "OS4.0.7.0.XBLCNXM", b"two")
        with self.assertRaises(SystemExit) as ctx:
            GUARD.decide(self.current, self.incoming, "OS4.0.7.0.XBLCNXM",
                         self.fallback, "NEW_OTA_CANDIDATE")
        self.assertIn("different canonical ZIP bytes", str(ctx.exception))

    def test_original_legacy_fixed_zip_uses_fallback_build(self):
        stock_zip(self.current, None, b"legacy")
        stock_zip(self.incoming, self.fallback, b"normalized")
        decision, current = GUARD.decide(
            self.current, self.incoming, self.fallback,
            self.fallback, "SAME_PINNED_BUILD")
        self.assertEqual(("ALREADY_CURRENT", self.fallback), (decision, current))

    def test_channel_change_never_auto_replaces_current(self):
        stock_zip(self.current, "OS4.0.7.0.XBLCNXM", b"current")
        stock_zip(self.incoming, "OS4.0.8.0.XBLMIXM", b"incoming")
        with self.assertRaises(SystemExit) as ctx:
            GUARD.decide(self.current, self.incoming, "OS4.0.8.0.XBLMIXM",
                         self.fallback, "NEW_OTA_CANDIDATE")
        self.assertIn("channel differs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
