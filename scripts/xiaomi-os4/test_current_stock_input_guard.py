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

    def test_d02_software_revision_is_evidence_only(self):
        stock_zip(self.current, self.fallback, b"current")
        stock_zip(self.incoming, self.fallback + ".D02", b"incoming")
        decision, current = GUARD.decide(
            self.current, self.incoming, self.fallback + ".D02",
            self.fallback, "SOFTWARE_OTA_REVIEW")
        self.assertEqual(("SOFTWARE_REVIEW", self.fallback), (decision, current))

    def test_d02_cannot_be_mislabeled_as_full_kernel_candidate(self):
        stock_zip(self.current, self.fallback)
        stock_zip(self.incoming, self.fallback + ".D02")
        with self.assertRaises(SystemExit):
            GUARD.decide(self.current, self.incoming, self.fallback + ".D02",
                         self.fallback, "NEW_OTA_CANDIDATE")

    def test_d02_d01_and_base_rollbacks_are_blocked(self):
        stock_zip(self.current, self.fallback + ".D02")
        for older in (self.fallback, self.fallback + ".D01"):
            stock_zip(self.incoming, older)
            with self.assertRaises(SystemExit) as ctx:
                GUARD.decide(self.current, self.incoming, older,
                             self.fallback, "SOFTWARE_OTA_REVIEW")
            self.assertIn("older than current fixed stock-input", str(ctx.exception))

    def test_d02_to_new_firmware_build_is_full_ota(self):
        stock_zip(self.current, self.fallback + ".D02")
        newer = "OS4.0.6.0.XBLCNXM"
        stock_zip(self.incoming, newer)
        decision, current = GUARD.decide(
            self.current, self.incoming, newer, self.fallback, "NEW_OTA_CANDIDATE")
        self.assertEqual(("FORWARD", self.fallback + ".D02"), (decision, current))

    def test_same_d02_different_content_still_requires_manual_review(self):
        stock_zip(self.current, self.fallback + ".D02", b"original")
        stock_zip(self.incoming, self.fallback + ".D02", b"modified")
        with self.assertRaises(SystemExit) as ctx:
            GUARD.decide(self.current, self.incoming, self.fallback + ".D02",
                         self.fallback, "SOFTWARE_OTA_REVIEW")
        self.assertIn("different canonical ZIP bytes", str(ctx.exception))

    def test_malformed_software_suffix_is_not_accepted(self):
        for invalid in (self.fallback + ".D2", self.fallback + ".D002",
                        self.fallback + ".D02.EXTRA", self.fallback + ".XYZ"):
            with self.assertRaises(SystemExit):
                GUARD.build_order(invalid)


if __name__ == "__main__":
    unittest.main()
