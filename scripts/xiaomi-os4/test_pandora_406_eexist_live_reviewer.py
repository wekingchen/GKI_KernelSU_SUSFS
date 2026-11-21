#!/usr/bin/env python3
import importlib.util,tempfile,unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("review",BASE/"review-pandora-406-eexist-testboot.py")
review=importlib.util.module_from_spec(spec); spec.loader.exec_module(review)

class Reviewer(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.d=Path(self.t.name)
        data={
            "device.txt":"pandora\n",
            "build.txt":"OS4.0.6.0.XBLCNXM\n",
            "slot.txt":"_b\n",
            "uname.txt":review.RELEASE+"\n",
            "boot-completed.txt":"1\n",
            "filtered-kernel-params.txt":"pandora_rust_binder_eexist=1\nmodule_blacklist=kernelsu\n",
            "binder-impl.txt":"c\n",
            "binder-active-impl.txt":"c\n",
            "loaded-modules-redacted.txt":"node_cache size=1 users=0\nzram size=2 users=1\nzsmalloc size=3 users=2\n",
            "rust-binder-initstate.txt":"ABSENT\n",
            "modules-disabled.txt":"0\n",
            "binder-service-activity.txt":"Service activity: found\n",
            "binder-service-package.txt":"Service package: found\n",
            "shim-kernel-log.txt":"pandora: rust_binder load request satisfied as EEXIST for C-Binder experiment\n",
        }
        for n,v in data.items(): (self.d/n).write_text(v)
        for m,h in review.EXPECTED_NOTES.items():
            (self.d/f"loaded-{m.replace('_','-')}-note-sha.txt").write_text(
                f"{h}  {review.NOTE_PATHS[m]}\n")

    def test_exact_expected_state_passes_but_formal_gate_stays_blocked(self):
        r=review.evaluate(self.d)
        self.assertTrue(r["temporary_boot_pass"])
        self.assertEqual(r["verdict"],"PASS_EXPERIMENTAL_FASTBOOT_BOOT_ONLY")
        self.assertEqual(r["formal_oem_gate"],"BLOCKED")
        self.assertFalse(r["persistent_flash"])
        self.assertFalse(r["lkg_promotion"])
        self.assertTrue(r["binder"]["active_impl_directly_verified"])
        self.assertTrue(r["runtime_vendor_notes_complete"])

    def test_missing_active_impl_is_allowed_but_not_directly_verified(self):
        (self.d/"binder-active-impl.txt").write_text("")
        r=review.evaluate(self.d)
        self.assertTrue(r["temporary_boot_pass"])
        self.assertFalse(r["binder"]["active_impl_directly_verified"])

    def test_rust_binder_loaded_fails_closed(self):
        p=self.d/"loaded-modules-redacted.txt"
        p.write_text(p.read_text()+"rust_binder size=4 users=0\n")
        r=review.evaluate(self.d)
        self.assertFalse(r["temporary_boot_pass"])
        self.assertIn("unexpectedly loaded",r["reason"])

    def test_rust_binder_blacklist_is_not_accepted(self):
        (self.d/"filtered-kernel-params.txt").write_text(
            "pandora_rust_binder_eexist=1\nmodule_blacklist=kernelsu,rust_binder\n")
        r=review.evaluate(self.d)
        self.assertFalse(r["temporary_boot_pass"])
        self.assertIn("must not be blacklisted",r["reason"])

    def test_binder_service_failure_blocks(self):
        (self.d/"binder-service-package.txt").write_text("Service package: not found\n")
        r=review.evaluate(self.d)
        self.assertFalse(r["temporary_boot_pass"])
        self.assertIn("package Binder service",r["reason"])

    def test_vendor_note_mismatch_blocks_when_note_is_available(self):
        (self.d/"loaded-zsmalloc-note-sha.txt").write_text(
            "f"*64+"  "+review.NOTE_PATHS["zsmalloc"]+"\n")
        r=review.evaluate(self.d)
        self.assertFalse(r["temporary_boot_pass"])
        self.assertIn("GNU Note mismatch",r["reason"])

    def test_note_unavailable_is_recorded_not_fabricated(self):
        (self.d/"loaded-zsmalloc-note-sha.txt").unlink()
        r=review.evaluate(self.d)
        self.assertTrue(r["temporary_boot_pass"])
        self.assertFalse(r["runtime_vendor_notes_complete"])
        self.assertEqual(r["runtime_vendor_note_evidence"]["zsmalloc"]["state"],"UNAVAILABLE")

if __name__=="__main__":
    unittest.main()
