#!/usr/bin/env python3
"""Fail-closed unit/contract tests for OTA V2 historical replay."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ota_v2_abi_diagnostics", ROOT / "ota-v2-abi-diagnostics.py")
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)
REFERENCE_PATH = ROOT / "ota-v2-references/pandora-os4-406-raw-oem-abi.json"


class OTAV2DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
        exp = self.ref["expected_report"]
        self.report = {
            "schema": 1,
            "gate": "BLOCKED",
            "eligible_for_fastboot_boot": False,
            "flashable": False,
            "failed_modules": [],
            "unresolved_kernel_imports": [
                f"system_dlkm/rust_binder.ko:_R{i}" for i in range(71)],
            "ambiguous_providers": [
                f"vendor_dlkm/sample.ko:zsmalloc_symbol_{i}" for i in range(27)],
            "crc_mismatches": [],
            "reason": "OEM .ko CRC/vermagic/provider graph has errors or unresolved imports",
        }
        for field, value in exp.items():
            if field in (
                "unresolved_kernel_imports_count", "ambiguous_providers_count",
                "crc_mismatches_count", "failed_modules_count"):
                continue
            self.report[field] = value

    def test_historical_blocked_replay_matched_not_passed(self):
        out = diagnostics.interpret(diagnostics.read_report(self._write_report()))
        self.assertEqual(out["status"], "ABI_BLOCKED_DIAGNOSABLE")
        self.assertFalse(out["fastboot_boot_eligible"])
        self.assertFalse(out["persistent_install_authorized"])
        self.assertFalse(out["lkg_promotion_authorized"])
        self.assertEqual(
            [x["code"] for x in out["diagnoses"]],
            ["STOCK_RUST_BINDER_ABI_UNRESOLVED", "AMBIGUOUS_MODULE_PROVIDERS"],
        )
        reference = diagnostics.verify_reference(self.report, self.ref)
        self.assertTrue(reference["matched"])
        self.assertTrue(reference["historical_gate_still_blocked"])

    def test_mutated_provider_count_blocks_reference_replay(self):
        self.report["ambiguous_providers"].pop()
        with self.assertRaisesRegex(diagnostics.EvidenceError, "replay drift"):
            diagnostics.verify_reference(self.report, self.ref)

    def test_missing_vendor_boot_early_modules_blocks_reference_replay(self):
        self.report["vendor_boot_modules_seen"] = 0
        with self.assertRaisesRegex(diagnostics.EvidenceError, "replay drift"):
            diagnostics.verify_reference(self.report, self.ref)

    def test_replay_cannot_accept_unexpected_pass(self):
        self.report["gate"] = "CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        self.report["eligible_for_fastboot_boot"] = True
        with self.assertRaisesRegex(diagnostics.EvidenceError, "replay drift"):
            diagnostics.verify_reference(self.report, self.ref)

    def test_blocked_gate_claiming_boot_eligible_is_invalid(self):
        self.report["eligible_for_fastboot_boot"] = True
        with self.assertRaisesRegex(diagnostics.EvidenceError, "blocked ABI report"):
            diagnostics.read_report(self._write_report())

    def test_nonflash_static_pass_is_not_persistent_authorization(self):
        self.report.update(
            gate="CRC_AND_VERMAGIC_MATCH_CANDIDATE",
            eligible_for_fastboot_boot=True,
            unresolved_kernel_imports=[], unresolved_rust_binder=0,
            ambiguous_providers=[], ambiguous_same_crc=0, ambiguous_split_crc=0,
        )
        out = diagnostics.interpret(diagnostics.read_report(self._write_report()))
        self.assertEqual(out["status"], "STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST")
        self.assertTrue(out["fastboot_boot_eligible"])
        self.assertFalse(out["persistent_install_authorized"])
        self.assertFalse(out["lkg_promotion_authorized"])

    def test_passing_gate_with_unresolved_imports_is_invalid(self):
        self.report.update(
            gate="CRC_AND_VERMAGIC_MATCH_CANDIDATE",
            eligible_for_fastboot_boot=True)
        with self.assertRaisesRegex(diagnostics.EvidenceError, "passing ABI gate"):
            diagnostics.interpret(diagnostics.read_report(self._write_report()))

    def test_blocked_provenance_without_graph_not_misclassified(self):
        self.report.update(
            unresolved_kernel_imports=[], unresolved_rust_binder=0,
            ambiguous_providers=[], ambiguous_same_crc=0, ambiguous_split_crc=0,
            reason="stock zip bytes changed after initial audit")
        out = diagnostics.interpret(diagnostics.read_report(self._write_report()))
        self.assertEqual(out["status"], "AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW")
        self.assertEqual(out["diagnoses"][0]["code"], "INPUT_OR_PROVENANCE_BLOCKED")

    def test_runtime_selection_without_proof_cannot_pass(self):
        self.report.update(
            gate="CRC_VERMAGIC_AND_RUNTIME_SELECTION_MATCH_CANDIDATE",
            eligible_for_fastboot_boot=True,
            unresolved_kernel_imports=[], unresolved_rust_binder=0,
            ambiguous_providers=[], ambiguous_same_crc=0, ambiguous_split_crc=0,
        )
        with self.assertRaisesRegex(diagnostics.EvidenceError, "missing fail-closed evidence"):
            diagnostics.interpret(diagnostics.read_report(self._write_report()))

    def test_rust_count_greater_than_unresolved_is_invalid(self):
        self.report["unresolved_kernel_imports"] = []
        with self.assertRaisesRegex(diagnostics.EvidenceError, "exceeds all unresolved"):
            diagnostics.interpret(diagnostics.read_report(self._write_report()))

    def test_negative_provider_subcount_is_invalid(self):
        self.report["ambiguous_split_crc"] = -1
        with self.assertRaisesRegex(diagnostics.EvidenceError, "invalid nonnegative"):
            diagnostics.interpret(diagnostics.read_report(self._write_report()))

    def test_reference_expectations_cannot_be_empty(self):
        ref = copy.deepcopy(self.ref)
        ref["expected_report"] = {}
        with self.assertRaisesRegex(diagnostics.EvidenceError, "empty replay"):
            diagnostics.verify_reference(self.report, ref)

    def _write_report(self):
        # unittest cleanup runs when the test completes; no real stock data.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "abi.json"
        path.write_text(json.dumps(self.report), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
