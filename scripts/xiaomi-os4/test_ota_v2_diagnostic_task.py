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
        self.report={"gate":"BLOCKED","eligible_for_fastboot_boot":False,
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


if __name__=="__main__":
    unittest.main()
