#!/usr/bin/env python3
"""Regressions for showing a mobile task only when the ABI BLOCKED source matches."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("stage",ROOT/"collect-os4-stage.py")
stage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class TaskAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.run={"id":12345,"head_sha":"b"*40}
        self.build="OS4.0.6.0.XBLCNXM"
        self.sha="a"*64
        self.task={
            "schema":"pandora-ota-diagnostic-task-v1",
            "device":"pandora","repository":stage.REPO,
            "status":"ABI_BLOCKED_DIAGNOSABLE","source_run_id":12345,
            "source_head_sha":"b"*40,"stock_build":self.build,
            "stock_input_sha256":self.sha,"candidate_commit":"c"*40,
            "commands":[],"device_write_allowed":False,"safe_to_flash":False,
            "promote_lkg":False,"requires_manual_review":True,
            "upload_requires_confirmation":True,
            "issues":[{"code":"STOCK_RUST_BINDER_ABI_UNRESOLVED","count":71}],
            "checks":[{"id":"binder_runtime","label":"只读状态"}],
        }
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"task.json"

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self):
        self.path.write_text(json.dumps(self.task),encoding="utf-8")
        return stage.diagnostic_task_matches(self.path,self.run,self.build,self.sha)

    def test_verified_task_can_show_button(self):
        self.assertTrue(self.verify())

    def test_missing_and_cross_ota_tasks_have_no_button(self):
        self.assertFalse(stage.diagnostic_task_matches(
            self.path,self.run,self.build,self.sha))
        self.task["source_run_id"]=12346
        self.assertFalse(self.verify())
        self.task["source_run_id"]=12345
        self.task["stock_input_sha256"]="d"*64
        self.assertFalse(self.verify())

    def test_command_or_flash_permission_is_never_considered_a_valid_task(self):
        self.task["commands"]=["su -c id"]
        self.assertFalse(self.verify())
        self.task["commands"]=[]
        self.task["safe_to_flash"]=True
        self.assertFalse(self.verify())

    def test_invalid_and_partial_json_fails_closed(self):
        self.path.write_text("{",encoding="utf-8")
        self.assertFalse(stage.diagnostic_task_matches(
            self.path,self.run,self.build,self.sha))


if __name__=="__main__":
    unittest.main()
