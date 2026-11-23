#!/usr/bin/env python3
"""Pure fixture tests for the OS4.0.5/OS4.0.6 learned follow-up plan."""
import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("ota_v2_recovery_plan",
    Path(__file__).resolve().parent / "plan-ota-v2-recovery.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecoveryPlanTest(unittest.TestCase):
    def setUp(self):
        self.task = {
            "schema": "pandora-ota-diagnostic-task-v1",
            "source_run_id": 12345, "stock_build": "OS4.0.6.0.XBLCNXM",
            "stock_input_sha256": "a"*64, "source_head_sha": "b"*40,
            "candidate_commit": "c"*40,
            "issues": [{"code":x, "count":1} for x in
                       ("OTHER_UNRESOLVED_IMPORTS", "AMBIGUOUS_MODULE_PROVIDERS",
                        "STOCK_RUST_BINDER_ABI_UNRESOLVED")],
        }
        self.report = {
            "gate":"BLOCKED", "eligible_for_fastboot_boot":False, "flashable":False,
            "stock_input_sha256":"a"*64, "stock_build":"OS4.0.6.0.XBLCNXM",
            "candidate_commit":"c"*40,
        }
        self.evidence = {
            "schema":"pandora-ota-diagnostic-evidence-v1",
            "source_run_id":12345,"stock_build":"OS4.0.6.0.XBLCNXM",
            "stock_input_sha256":"a"*64,"source_head_sha":"b"*40,
            "candidate_commit":"c"*40, "status":"CAPTURED_READ_ONLY",
            "observations":{
                "binder_runtime":{"active_impl":"c","rust_binder_loaded":False,
                                  "module_blacklist_kernelsu":True,"eexist_parameter":True},
                "loaded_module_identity":{
                    x:{"gnu_note_sha256":"d"*64}
                    for x in ("node_cache","zram","zsmalloc")}
            },
        }
        self.review = {
            "schema":"pandora-ota-diagnostic-review-v1", "review":"REVIEW_REQUIRED",
            "source_run_id":12345,"stock_build":"OS4.0.6.0.XBLCNXM",
            "stock_input_sha256":"a"*64,"payload_sha256":"e"*64,
            "safe_to_flash":False,"oem_gate_unlocked":False,"lkg_promotion":False,
        }

    def run_plan(self):
        return module.plan(self.task,self.report,self.evidence,self.review)

    def test_real_os406_gaps_get_distinct_triage_paths(self):
        plan=self.run_plan()
        names={item["code"] for item in plan["actions"]}
        self.assertIn("VENDOR_BOOT_PROVIDER_GRAPH",names)
        self.assertIn("SPLIT_VENDOR_SYSTEM_CRC",names)
        self.assertIn("RUST_BINDER_RUNTIME_ROUTE",names)
        self.assertIn("POST_FIX_RUNTIME_GATES",names)
        self.assertFalse(plan["automatic_rebuild_authorized"])
        self.assertFalse(plan["fastboot_boot_authorized"])
        self.assertFalse(plan["lkg_promotion_authorized"])
        self.assertTrue(plan["requires_new_candidate_after_fix"])
        rust=next(x for x in plan["actions"]
                  if x["code"]=="RUST_BINDER_RUNTIME_ROUTE")
        self.assertIn("C Binder",rust["detail"])
        self.assertIn("71 条 Rust",rust["detail"])

    def test_partial_or_rust_loaded_never_means_auto_waiver(self):
        self.evidence["status"]="PARTIAL_READ_ONLY"
        self.evidence["observations"]["binder_runtime"]={
            "active_impl":"rust","rust_binder_loaded":True,
            "module_blacklist_kernelsu":None,"eexist_parameter":None,
        }
        codes=[x["code"] for x in self.run_plan()["actions"]]
        self.assertIn("RECOLLECT_MISSING_ONLY",codes)
        rust=next(x for x in self.run_plan()["actions"]
                  if x["code"]=="RUST_BINDER_RUNTIME_ROUTE")
        self.assertIn("Rust Binder 已加载",rust["detail"])
        self.assertFalse(rust["automated_patch"])

    def test_no_classified_reason_remains_blocked(self):
        self.task["issues"]=[]
        result=self.run_plan()
        self.assertIn("BLOCKED_INPUT_REVIEW",[x["code"] for x in result["actions"]])
        self.assertEqual("BLOCKED",result["oem_gate"])

    def test_wrong_stock_or_candidate_or_unlocked_gate_fails_closed(self):
        self.evidence["stock_input_sha256"]="f"*64
        with self.assertRaises(ValueError):self.run_plan()
        self.evidence["stock_input_sha256"]="a"*64
        self.report["candidate_commit"]="f"*40
        with self.assertRaises(ValueError):self.run_plan()
        self.report["candidate_commit"]="c"*40
        self.review["oem_gate_unlocked"]=True
        with self.assertRaises(ValueError):self.run_plan()


if __name__=="__main__":
    unittest.main()
