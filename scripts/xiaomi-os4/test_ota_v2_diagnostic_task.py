#!/usr/bin/env python3
"""OTA V2 mobile task + received evidence negative contract tests."""
import importlib.util
import hashlib
import json
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent


def load(filename,name):
    spec=importlib.util.spec_from_file_location(name,BASE/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


maker=load("make-ota-v2-diagnostic-task.py","make_task")
verifier=load("verify-ota-v2-diagnostic-evidence.py","verify_task")


class DiagnosticTaskContract(unittest.TestCase):
    def setUp(self):
        self.diagnosis={
            "schema":1,"status":"ABI_BLOCKED_DIAGNOSABLE","oem_gate":"BLOCKED",
            "fastboot_boot_eligible":False,"persistent_install_authorized":False,
            "lkg_promotion_authorized":False,"auto_waiver_applied":False,
            "stock_build":"OS4.0.6.0.XBLCNXM",
            "stock_input_sha256":"a"*64,"candidate_commit":"b"*40,
            "diagnoses":[
                {"code":"STOCK_RUST_BINDER_ABI_UNRESOLVED","count":71},
                {"code":"AMBIGUOUS_MODULE_PROVIDERS","count":27}
            ]
        }
        self.task=maker.build_task(self.diagnosis,12345,"c"*40)
        self.report={"schema":1,"gate":"BLOCKED","eligible_for_fastboot_boot":False,
                     "flashable":False,"failed_modules":[],"unresolved_kernel_imports":[],
                     "ambiguous_providers":[],"crc_mismatches":[],
                     "stock_input_sha256":self.task["stock_input_sha256"],
                     "stock_build":self.task["stock_build"],
                     "candidate_commit":self.task["candidate_commit"]}
        self.evidence={
            "schema":"pandora-ota-diagnostic-evidence-v1",
            "repository":"wekingchen/GKI_KernelSU_SUSFS",
            "source_run_id":12345,"source_head_sha":"c"*40,
            "stock_build":"OS4.0.6.0.XBLCNXM","stock_input_sha256":"a"*64,
            "candidate_commit":"b"*40,
            "checks":["binder_runtime","loaded_module_identity"],
            "status":"CAPTURED_READ_ONLY","captured_at_ms":1795400000000,
            "observations":{
                "identity":{"device":"pandora","build":"OS4.0.6.0.XBLCNXM",
                            "boot_completed":"1","slot":"_b",
                            "uname":"6.12.69-android16-6-test-4k"},
                "binder_runtime":{
                    "impl":"c","active_impl":"c","rust_binder_loaded":False,
                    "kernelsu_lkm_loaded":False,"module_blacklist_kernelsu":True,
                    "eexist_parameter":True},
                "loaded_module_identity":{
                    key:{"loaded":True,"gnu_note_sha256":str(i)*64}
                    for i,key in enumerate(("node_cache","zram","zsmalloc"),start=1)}
            },
            "attestation":"DEVICE_READ_ONLY_OBSERVATION_NOT_KERNEL_COMPATIBILITY_PROOF",
            "device_write_allowed":False,"safe_to_flash":False,"lkg_promotion":False
        }

    def verify(self):
        raw=json.dumps(self.evidence).encode()
        return verifier.verify(self.task,self.report,self.evidence,raw,hashlib.sha256(raw).hexdigest())

    def test_historical_obstacles_generate_two_fixed_phone_checks(self):
        self.assertEqual([x["id"] for x in self.task["checks"]],
                         ["binder_runtime","loaded_module_identity"])
        self.assertEqual(self.task["commands"],[])
        self.assertFalse(self.task["device_write_allowed"])
        self.assertFalse(self.task["safe_to_flash"])
        self.assertTrue(self.task["requires_manual_review"])

    def test_task_and_oem_report_cannot_silently_waive_block(self):
        self.task["commands"]=["echo noop"]
        with self.assertRaises(ValueError):self.verify()
        self.task["commands"]=[]
        self.task["safe_to_flash"]=True
        with self.assertRaises(ValueError):self.verify()
        self.task["safe_to_flash"]=False
        self.task["issues"][0]["code"]="READ_ANY_PATH"
        with self.assertRaises(ValueError):self.verify()

    def test_original_report_requires_real_schema_and_negative_authorization(self):
        self.report["flashable"]=True
        with self.assertRaises(ValueError):self.verify()
        self.report["flashable"]=False
        self.report["schema"]=2
        with self.assertRaises(ValueError):self.verify()

    def test_received_evidence_requires_review_never_unlocks_abi(self):
        accepted=self.verify()
        self.assertEqual(accepted["review"],"REVIEW_REQUIRED")
        self.assertFalse(accepted["safe_to_flash"])
        self.assertFalse(accepted["oem_gate_unlocked"])
        self.assertFalse(accepted["lkg_promotion"])

    def test_partial_with_unknown_values_is_reviewable(self):
        self.evidence["status"]="PARTIAL_READ_ONLY"
        self.evidence["observations"]["binder_runtime"]["impl"]="UNKNOWN"
        self.evidence["observations"]["loaded_module_identity"]["zsmalloc"]["gnu_note_sha256"]=None
        self.assertEqual(self.verify()["review"],"REVIEW_REQUIRED")

    def test_server_supplied_unknown_issue_cannot_request_commands(self):
        self.diagnosis["diagnoses"]=[{"code":"READ_ANY_PATH","count":1}]
        with self.assertRaises(ValueError):maker.build_task(self.diagnosis,12345,"c"*40)

    def test_duplicate_issue_and_zero_count_rejected(self):
        self.diagnosis["diagnoses"].append(self.diagnosis["diagnoses"][0])
        with self.assertRaises(ValueError):maker.build_task(self.diagnosis,12345,"c"*40)
        self.diagnosis["diagnoses"]=[{"code":"AMBIGUOUS_MODULE_PROVIDERS","count":0}]
        with self.assertRaises(ValueError):maker.build_task(self.diagnosis,12345,"c"*40)

    def test_nonblocked_case_never_creates_task(self):
        self.diagnosis["status"]="STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST"
        with self.assertRaises(ValueError):maker.build_task(self.diagnosis,12345,"c"*40)

    def test_executable_commands_are_not_accepted(self):
        self.task["commands"]=["cat /proc/kallsyms"]
        # Back-end checks task origin; app also rejects nonempty commands.
        # Here ensure that no unexpected field can be accepted within evidence.
        self.evidence["commands"]=self.task["commands"]
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_ota_or_run_rejected(self):
        self.evidence["source_run_id"]=12346
        with self.assertRaises(ValueError):self.verify()
        self.evidence["source_run_id"]=12345
        self.evidence["stock_input_sha256"]="d"*64
        with self.assertRaises(ValueError):self.verify()

    def test_raw_kernel_address_and_log_fields_rejected(self):
        self.evidence["observations"]["kernel_log"]="finit_module error, private details"
        with self.assertRaises(ValueError):self.verify()
        self.evidence["observations"].pop("kernel_log")
        self.evidence["observations"]["identity"]["kallsyms"]="ffffffff80000000"
        with self.assertRaises(ValueError):self.verify()

    def test_untrusted_gnu_note_or_binder_value_rejected(self):
        self.evidence["observations"]["loaded_module_identity"]["zram"]["gnu_note_sha256"]="not-a-digest"
        with self.assertRaises(ValueError):self.verify()
        self.evidence["observations"]["loaded_module_identity"]["zram"]["gnu_note_sha256"]="2"*64
        self.evidence["observations"]["binder_runtime"]["active_impl"]="malicious"
        with self.assertRaises(ValueError):self.verify()

    def test_suspicious_persistent_authority_rejected(self):
        self.evidence["safe_to_flash"]=True
        with self.assertRaises(ValueError):self.verify()
        self.evidence["safe_to_flash"]=False
        self.evidence["lkg_promotion"]=True
        with self.assertRaises(ValueError):self.verify()

    def test_original_oem_abi_must_still_be_blocked(self):
        self.report["gate"]="CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_sha_or_oversize_rejected(self):
        raw=json.dumps(self.evidence).encode()
        with self.assertRaises(ValueError):
            verifier.verify(self.task,self.report,self.evidence,raw,"0"*64)
        with self.assertRaises(ValueError):
            verifier.verify(self.task,self.report,self.evidence,raw+b" "*32768,
                            hashlib.sha256(raw+b" "*32768).hexdigest())

    def test_review_run_identity_and_binary_download_are_explicit(self):
        workflow=(BASE.parents[1]/".github/workflows/pandora-os4-ota-diagnostic-intake.yml").read_text()
        self.assertIn('run-name: "Pandora OTA diagnosis / source-',workflow)
        for token in ("inputs.source_run_id", "inputs.release_id", "inputs.asset_id"):
            self.assertIn(token,workflow)
        # Draft Release tag lookup is not reliable (404 on unpublished tags).
        # The reviewer must use the already-validated numeric asset identity.
        self.assertIn('releases/$RELEASE_ID',workflow)
        self.assertIn('releases/assets/$ASSET_ID',workflow)
        self.assertIn('Authorization: Bearer $GH_TOKEN',workflow)
        self.assertIn('Accept: application/octet-stream',workflow)
        self.assertIn('stat -c%s',workflow)
        self.assertIn('sha256sum "$DIR/diagnostic-evidence.json"',workflow)
        self.assertNotIn('gh release download "$TAG"',workflow)
        self.assertIn('EXPECTED_SHA',workflow)
        self.assertIn('verify-ota-v2-diagnostic-evidence.py',workflow)
        self.assertIn('REVIEW_REQUIRED',workflow)
        self.assertNotIn('gh release edit "$TAG" --draft=false',workflow)

    def test_stage_snapshot_refreshes_on_exact_unified_lkg_workflow(self):
        workflow=(BASE.parents[1]/".github/workflows/pandora-os4-stage-status.yml").read_text()
        promotion=(BASE.parents[1]/".github/workflows/xiaomi-sm8850-os4-promote-lkg.yml").read_text()
        self.assertIn('name: "小米17 Pro OS4 / 晋升真机稳定内核为 LKG"',promotion)
        self.assertIn('      - "小米17 Pro OS4 / 晋升真机稳定内核为 LKG"',workflow)
        self.assertIn('      - ".github/config/ota-lkg-current.json"',workflow)
        self.assertIn('      - ".github/config/ota-verified/**"',workflow)
        self.assertIn("workflow_run:",workflow)
        self.assertIn("types: [completed]",workflow)
        self.assertIn("collect-os4-stage.py --output os4-stage.json",workflow)



    def test_historical_abi_replay_uses_frozen_independent_stock_reference(self):
        ref=json.loads((BASE/"ota-v2-references/pandora-os4-406-raw-oem-abi.json").read_text())
        self.assertEqual("pandora-ota-v2-os406-raw-stock-reference",ref["source"]["stock_tag"])
        self.assertEqual("bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8",
                         ref["source"]["stock_input_sha256"])
        self.assertEqual("IMMUTABLE_READONLY_OS406_REFERENCE_EXACT_PINNED_SHA256",
                         ref["source"]["stock_source_note"])
        replay=(BASE.parents[1]/".github/workflows/pandora-os4-ota-v2-evidence-replay.yml").read_text()
        self.assertIn("stock_tag=\"$(jq -r '.source.stock_tag' \"$REFERENCE\")\"",replay)
        self.assertIn('sha256sum "$stock_zip"',replay)
        self.assertIn("reference_replay.historical_gate_still_blocked == true",replay)
        self.assertFalse((BASE/"freeze-ota-v2-historical-os406-stock.sh").exists())
        self.assertFalse((BASE.parents[1]/".github/workflows/pandora-ota-v2-freeze-os406-reference.yml").exists())


if __name__=="__main__":
    unittest.main()
