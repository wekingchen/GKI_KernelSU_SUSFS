#!/usr/bin/env python3
"""Fail-closed snapshot interpretation tests, no device interaction."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "review_live_loader", BASE / "review-live-module-delivery-readonly.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class EvidenceReviewer(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.dir = Path(self.t.name)
        (self.dir / "identity.txt").write_text(
            "device=pandora\nbuild=OS4.0.6.0.XBLCNXM\n_b\n"
            "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k\n1\n")
        for name, (_, _, digest, path) in review.EXPECTED.items():
            (self.dir / name).write_text(f"{digest}  {path}\n")
        (self.dir / "binder-impl-cmdline.txt").write_text(
            "binder.impl=rust\n")
        (self.dir / "loaded-modules-redacted.txt").write_text(
            "rust_binder size=1234 users=0\nzsmalloc size=321 users=2\n")
        (self.dir / "system-modules.load").write_text("rust_binder.ko\n")
        (self.dir / "vendor-modules.load").write_text("zsmalloc.ko\n")
        (self.dir / "dlkm-mounts.txt").write_text("system_dlkm ro\n")

    def loaded_note(self, module, note_sha, path=None):
        name = "loaded-" + module.replace("_", "-") + "-note-sha.txt"
        path = path or "/sys/module/" + module + "/notes/.note.gnu.build-id"
        (self.dir / name).write_text(note_sha + "  " + path + "\n")

    def test_actual_loaded_note_can_distinguish_vendor_zsmalloc(self):
        self.loaded_note("zsmalloc", review.EXPECTED_GNU_NOTE_SHA["zsmalloc"]["vendor"])
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "vendor")
        self.assertEqual(r["runtime_module_note_evidence"]["zsmalloc"]["status"],
                         "UNIQUE_STOCK_GNU_NOTE_MATCH")
        self.assertFalse(r["module_delivery_verified"])
        self.assertEqual(r["runtime_loaded_binary_sha256"], "NOT_PROVEN")
        self.assertEqual(r["gate"], "BLOCKED")

    def test_actual_loaded_note_can_distinguish_system_zsmalloc(self):
        self.loaded_note("zsmalloc", review.EXPECTED_GNU_NOTE_SHA["zsmalloc"]["system"])
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "system")
        self.assertEqual(r["gate"], "BLOCKED")

    def test_missing_note_is_unknown_not_loaded_binary_claim(self):
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "UNPROVEN")
        self.assertEqual(r["runtime_module_note_evidence"]["zsmalloc"]["status"],
                         "MISSING_OR_MALFORMED_SYSFS_NOTE")

    def test_unknown_or_wrong_path_note_never_selects_stock_source(self):
        self.loaded_note("zsmalloc", "f" * 64)
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "UNPROVEN")
        self.assertEqual(r["runtime_module_note_evidence"]["zsmalloc"]["status"],
                         "UNKNOWN_GNU_NOTE_NOT_IN_PINNED_STOCK")
        self.loaded_note("zsmalloc", review.EXPECTED_GNU_NOTE_SHA["zsmalloc"]["vendor"],
                         path="/data/local/tmp/fake-note")
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_module_note_evidence"]["zsmalloc"]["status"],
                         "WRONG_NOTE_PATH")
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "UNPROVEN")

    def test_proc_modules_absence_prevents_note_attribution(self):
        (self.dir / "loaded-modules-redacted.txt").write_text("")
        self.loaded_note("zsmalloc", review.EXPECTED_GNU_NOTE_SHA["zsmalloc"]["vendor"])
        r = review.evaluate(self.dir)
        self.assertEqual(r["runtime_module_note_evidence"]["zsmalloc"]["status"],
                         "NOT_OBSERVED_IN_PROC_MODULES")
        self.assertEqual(r["runtime_zsmalloc_unique_note_source"], "UNPROVEN")

    def test_matched_on_disk_is_never_runtime_abi_pass(self):
        r = review.evaluate(self.dir)
        self.assertEqual(r["overall_status"], "ON_DISK_PINNED_FILES_MATCH_NO_LOADER_PROOF")
        self.assertEqual(r["gate"], "BLOCKED")
        self.assertFalse(r["flashable"])
        self.assertFalse(r["binder_implementation_verified"])
        self.assertFalse(r["module_delivery_verified"])
        self.assertFalse(r["signing_trust_verified"])
        self.assertFalse(r["system_dlkm_avb_chain_verified"])
        self.assertEqual(r["runtime_loaded_binary_sha256"], "NOT_PROVEN")
        self.assertTrue(r["zsmalloc_source_separation"])
        self.assertEqual(r["observed_binder_cmdline_tokens"], ["binder.impl=rust"])
        self.assertEqual(len(r["on_disk_source_qualified_modules"]), 3)

    def test_vendor_system_hashes_never_conflated(self):
        path = self.dir / "system-zsmalloc-file-sha.txt"
        vendor = review.EXPECTED["vendor-zsmalloc-file-sha.txt"]
        path.write_text(vendor[2] + "  " +
                        review.EXPECTED["system-zsmalloc-file-sha.txt"][3] + "\n")
        r = review.evaluate(self.dir)
        self.assertEqual(r["overall_status"], "ON_DISK_DISCREPANCY_NO_LOADER_PROOF")
        self.assertEqual(r["on_disk_discrepancies"], ["system:zsmalloc"])
        self.assertEqual(r["gate"], "BLOCKED")

    def test_missing_sha_is_partial_not_verified(self):
        (self.dir / "vendor-zsmalloc-file-sha.txt").unlink()
        r = review.evaluate(self.dir)
        self.assertEqual(r["overall_status"], "PARTIAL")
        self.assertEqual(r["on_disk_unknowns"], ["vendor:zsmalloc"])

    def test_wrong_kernel_fails_closed(self):
        p = self.dir / "identity.txt"
        p.write_text(p.read_text().replace("6.12.69-", "6.12.68-"))
        r = review.evaluate(self.dir)
        self.assertEqual(r["overall_status"], "PARTIAL")
        self.assertEqual(r["gate"], "BLOCKED")

    def test_empty_cmdline_does_not_claim_c_binder(self):
        (self.dir / "binder-impl-cmdline.txt").write_text("")
        r = review.evaluate(self.dir)
        self.assertEqual(r["observed_binder_cmdline_tokens"], [])
        self.assertEqual(r["binder_implementation_selection"], "UNPROVEN")

    def test_unknown_bad_path_no_source_fabrication(self):
        p = self.dir / "system-rust-binder-file-sha.txt"
        p.write_text(review.EXPECTED["system-rust-binder-file-sha.txt"][2]
                     + "  /data/local/tmp/rust_binder.ko\n")
        r = review.evaluate(self.dir)
        self.assertEqual(r["overall_status"], "PARTIAL")
        self.assertIn("system:rust_binder", r["on_disk_unknowns"])


if __name__ == "__main__":
    unittest.main()
