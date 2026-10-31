#!/usr/bin/env python3
"""Synthetic action metadata for the one visible OS4 LKG promotion entry."""
import importlib.util
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
S=importlib.util.spec_from_file_location("lkgroute",HERE/"select-lkg-promotion-route.py")
MOD=importlib.util.module_from_spec(S)
S.loader.exec_module(MOD)
RID="88811222"

def run(**changes):
    r={"id":int(RID),"status":"completed","conclusion":"success",
       "event":"workflow_dispatch","head_branch":"dev",
       "path":".github/workflows/xiaomi-sm8850-os4-custom.yml",
       "head_sha":"a"*40,
       "repository":{"full_name":"wekingchen/GKI_KernelSU_SUSFS"}}
    r.update(changes)
    return r

def asset(name,expired=False):
    return {"name":name,"expired":expired,"id":66}

def list_(*items,total_count=None):
    return {"total_count":len(items) if total_count is None else total_count,
            "artifacts":list(items)}

OLD=f"pandora-OS4-R62-CUSTOM-run-{RID}"
OTA=f"pandora-OTA-CUSTOM-OS4.0.6.0.XBLCNXM-run-{RID}"


class Routes(unittest.TestCase):
    def check(self,r=None,a=None,current=False,repair=False,id=RID):
        return MOD.route(id,run() if r is None else r,
                         list_(asset(OTA)) if a is None else a,
                         current,repair=repair)

    def test_ota_default(self):
        self.assertEqual(self.check(),"ota")

    def test_legacy_supported_until_first_new_lkg(self):
        self.assertEqual(self.check(a=list_(asset(OLD))),"legacy")

    def test_legacy_forbidden_after_ota_lkg(self):
        with self.assertRaises(ValueError):
            self.check(a=list_(asset(OLD)),current=True)

    def test_ota_after_new_lkg(self):
        self.assertEqual(self.check(current=True),"ota")

    def test_repair_without_requiring_expired_source_artifact(self):
        self.assertEqual(MOD.route(RID,None,None,True,repair=True),"repair")

    def test_wrong_source_run_id(self):
        with self.assertRaises(ValueError):
            self.check(id="0")
        with self.assertRaises(ValueError):
            self.check(id="1;touch /tmp/untrusted")

    def test_different_workflow_or_branch(self):
        for key,value in (("path",".github/workflows/kernel-custom.yml"),
                          ("head_branch","feature"),
                          ("event","push"),
                          ("conclusion","failure"),
                          ("status","in_progress"),
                          ("head_sha","g"*40)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.check(r=run(**{key:value}))

    def test_foreign_repository_and_run_id(self):
        with self.assertRaises(ValueError):
            self.check(r=run(repository={"full_name":"attacker/elsewhere"}))
        with self.assertRaises(ValueError):
            self.check(r=run(id=111))

    def test_ambiguous_two_artifacts(self):
        with self.assertRaises(ValueError):
            self.check(a=list_(asset(OLD),asset(OTA)))

    def test_expired_and_missing_artifacts(self):
        for a in (list_(asset(OTA,True)),list_()):
            with self.subTest(artifact=a),self.assertRaises(ValueError):
                self.check(a=a)

    def test_duplicate_and_truncated_artifacts(self):
        for a in (list_(asset(OTA),asset(OTA)),
                  list_(asset(OTA),total_count=101),
                  list_(asset(OTA),total_count=2)):
            with self.subTest(artifact=a),self.assertRaises(ValueError):
                self.check(a=a)

    def test_invalid_ota_build_or_different_run(self):
        for name in ("pandora-OTA-CUSTOM-not-build-run-"+RID,
                     "pandora-OTA-CUSTOM-OS4.0.6.0.XBLCNXM-run-999"):
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.check(a=list_(asset(name)))


if __name__=="__main__":
    unittest.main()
