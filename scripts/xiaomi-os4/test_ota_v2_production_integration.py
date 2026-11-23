#!/usr/bin/env python3
"""Production OTA V2 integration gate: dynamic and static negative regressions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts/xiaomi-os4/run-ota-v2-diagnostics.sh"
WORKFLOW = ROOT / ".github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml"


class OTAV2ProductionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("jq") is None:
            raise RuntimeError("jq is required to execute the real production V2 bridge")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.raw = self.folder / "original-abi.json"
        self.out = self.folder / "v2.json"
        self.md = self.folder / "v2.md"
        self.report = {
            "schema": 1,
            "gate": "BLOCKED",
            "eligible_for_fastboot_boot": False,
            "flashable": False,
            "failed_modules": [],
            "unresolved_kernel_imports": ["system_dlkm/rust_binder.ko:_R_example"],
            "unresolved_rust_binder": 1,
            "ambiguous_providers": ["vendor_dlkm/sample.ko:zsmalloc"],
            "ambiguous_same_crc": 1,
            "ambiguous_split_crc": 0,
            "crc_mismatches": [],
            "reason": "OEM graph contains unresolved imports and provider ambiguity",
        }

    def run_bridge(self, *, write=True, report=None):
        if write:
            self.raw.write_text(json.dumps(self.report if report is None else report),
                                encoding="utf-8")
        env = dict(os.environ)
        env.pop("GITHUB_STEP_SUMMARY", None)
        return subprocess.run(
            ["bash", str(BRIDGE), str(self.raw), str(self.out), str(self.md)],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False)

    def test_production_workflow_keeps_original_oem_gate_as_authority(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        job = text.split("\n  oem-abi-and-testboot:", 1)[1]
        raw_pos = job.index('id: abi')
        v2_pos = job.index('id: v2')
        boot_pos = job.index('name: "仅静态门禁全部通过时生成同 OTA fastboot boot')
        self.assertLess(raw_pos, v2_pos)
        self.assertLess(v2_pos, boot_pos)
        self.assertIn('if: steps.abi.outcome == \'success\'', job)
        self.assertIn('bash scripts/xiaomi-os4/run-ota-v2-diagnostics.sh', job)
        self.assertIn('--output "$DIR/ota-abi-report.json"', job)
        self.assertIn('echo "eligible=$ELIGIBLE" >> "$GITHUB_OUTPUT"', job)
        self.assertEqual(
            job.count("if: steps.abi.outputs.eligible == 'true' && steps.v2.outcome == 'success'"),
            3)
        self.assertIn("ota-v2-diagnostic.json", job)
        self.assertIn("ota-v2-diagnostic.md", job)
        self.assertIn("if: always()", job)
        self.assertIn("if-no-files-found: warn", job)
        self.assertNotIn("--runtime-selection", job)

    def test_blocked_with_specific_causes_produces_no_eligibility(self):
        result = self.run_bridge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "ABI_BLOCKED_DIAGNOSABLE")
        self.assertFalse(data["fastboot_boot_eligible"])
        self.assertFalse(data["persistent_install_authorized"])
        self.assertFalse(data["lkg_promotion_authorized"])
        self.assertIn("只读", self.md.read_text(encoding="utf-8"))

    def test_incomplete_provenance_report_never_becomes_zero_error_pass(self):
        self.report["unresolved_kernel_imports"] = []
        self.report["unresolved_rust_binder"] = 0
        self.report["ambiguous_providers"] = []
        self.report["ambiguous_same_crc"] = 0
        self.report["reason"] = "stock input SHA mismatch"
        result = self.run_bridge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW")
        self.assertFalse(data["fastboot_boot_eligible"])
        self.assertIn("输入或审计不完整", self.md.read_text(encoding="utf-8"))

    def test_original_static_pass_is_only_a_temporary_boot_candidate(self):
        self.report.update(
            gate="CRC_AND_VERMAGIC_MATCH_CANDIDATE",
            eligible_for_fastboot_boot=True,
            unresolved_kernel_imports=[], unresolved_rust_binder=0,
            ambiguous_providers=[], ambiguous_same_crc=0)
        result = self.run_bridge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST")
        self.assertTrue(data["fastboot_boot_eligible"])
        self.assertFalse(data["persistent_install_authorized"])
        self.assertFalse(data["lkg_promotion_authorized"])

    def test_dangerous_blocked_but_boot_eligible_is_rejected(self):
        self.report["eligible_for_fastboot_boot"] = True
        result = self.run_bridge()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())

    def test_pass_with_unresolved_module_is_rejected(self):
        self.report.update(gate="CRC_AND_VERMAGIC_MATCH_CANDIDATE",
                           eligible_for_fastboot_boot=True)
        result = self.run_bridge()
        self.assertNotEqual(result.returncode, 0)

    def test_missing_or_truncated_original_report_blocks(self):
        result = self.run_bridge(write=False)
        self.assertNotEqual(result.returncode, 0)
        self.raw.write_text("{", encoding="utf-8")
        result = self.run_bridge(write=False)
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_runtime_selection_report_blocks(self):
        self.report.update(
            gate="CRC_VERMAGIC_AND_RUNTIME_SELECTION_MATCH_CANDIDATE",
            eligible_for_fastboot_boot=True,
            unresolved_kernel_imports=[], unresolved_rust_binder=0,
            ambiguous_providers=[], ambiguous_same_crc=0)
        result = self.run_bridge()
        self.assertNotEqual(result.returncode, 0)

    def test_python_interpreter_does_not_create_persistent_package(self):
        text = (ROOT / "scripts/xiaomi-os4/ota-v2-abi-diagnostics.py").read_text()
        self.assertNotIn("fastboot flash", text)
        self.assertNotIn("eligible_for_persistent_kernel_payload\": True", text)
        self.assertNotIn("auto_waiver_applied\": True", text)


if __name__ == "__main__":
    unittest.main()
