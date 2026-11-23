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
COMPAT=f"pandora-OTA-COMPAT-NONFLASH-OS4.0.6.0.XBLCNXM-run-{RID}"
COMPAT_CUSTOM=f"pandora-OTA-COMPAT-CUSTOM-OS4.0.6.0.XBLCNXM-run-{RID}"

def persistent(**changes):
    p={
        "status":"PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY",
        "device":"pandora",
        "stock_build":"OS4.0.6.0.XBLCNXM",
        "feature_workflow_run_id":int(RID),
        "feature_image_sha256":"3daba0524738ab872ebf75653f25754433c36a624eb8002198440a4cb1cb1dc0",
        "runtime_selected_oem_gate":"PASS_RUNTIME_SELECTED_EXACT_OS406",
        "persistent_boot_equivalence":"PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37",
        "package_run_id":45105070444,
        "package_artifact_id":14787211465,
        "package_sha256":"44a63799a6dce8b373181029ee2aa2c92340781713fc398c3220b482e88fde8e",
        "actual_persistent_install_verified":True,
        "lkg_promotion":True,
    }
    p.update(changes)
    return p


class Routes(unittest.TestCase):
    def check(self,r=None,a=None,current=False,repair=False,id=RID,p=None):
        return MOD.route(id,run() if r is None else r,
                         list_(asset(OTA)) if a is None else a,
                         current,repair=repair,persistent=p)

    def test_ota_default(self):
        self.assertEqual(self.check(),"ota")

    def test_legacy_supported_until_first_new_lkg(self):
        self.assertEqual(self.check(a=list_(asset(OLD))),"legacy")

    def test_legacy_forbidden_after_ota_lkg(self):
        with self.assertRaises(ValueError):
            self.check(a=list_(asset(OLD)),current=True)

    def test_ota_after_new_lkg(self):
        self.assertEqual(self.check(current=True),"ota")

    def test_eexist_compatibility_artifact_requires_exact_persistent_proof(self):
        with self.assertRaisesRegex(ValueError, "lacks exact two-reboot persistent proof"):
            self.check(a=list_(asset(COMPAT)))
        self.assertEqual(
            self.check(a=list_(asset(COMPAT)), p=persistent()),
            "ota-compat-persistent",
        )

    def test_compat_custom_requires_previous_ota_lkg(self):
        with self.assertRaisesRegex(ValueError, "previously validated same-OTA LKG"):
            self.check(a=list_(asset(COMPAT_CUSTOM)))
        self.assertEqual(
            self.check(a=list_(asset(COMPAT_CUSTOM)), current=True),
            "ota-compat-custom",
        )

    def test_compat_custom_rejects_wrong_run_or_build_and_ambiguous_packages(self):
        for bad in (
            "pandora-OTA-COMPAT-CUSTOM-OS4.0.6.0.XBLCNXM-run-999",
            f"pandora-OTA-COMPAT-CUSTOM-OS4.0.5.0.XBLCNXM-run-{RID}",
            f"pandora-OTA-COMPAT-CUSTOM-OS4.0.7.0.XBLCNXM-run-{RID}",
        ):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                self.check(a=list_(asset(bad)), current=True)
        with self.assertRaises(ValueError):
            self.check(a=list_(asset(COMPAT_CUSTOM), asset(COMPAT_CUSTOM)), current=True)

    def test_persistent_compat_fails_closed_on_any_identity_drift(self):
        cases = (
            {"status":"FIRST_TRUE_DEVICE_PERSISTENT_REBOOT_PASS_SECOND_REBOOT_PENDING"},
            {"actual_persistent_install_verified":False},
            {"lkg_promotion":False},
            {"feature_workflow_run_id":1},
            {"feature_image_sha256":"0"*64},
            {"runtime_selected_oem_gate":"BLOCKED"},
            {"persistent_boot_equivalence":"BLOCKED"},
            {"package_run_id":1},
            {"package_artifact_id":1},
            {"package_sha256":"0"*64},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check(a=list_(asset(COMPAT)), p=persistent(**changes))

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


    def test_legacy_r62_followup_names_match_actual_unified_promotion(self):
        workflows=HERE.parents[1]/".github/workflows"
        current=(workflows/"xiaomi-sm8850-os4-promote-lkg.yml").read_text()
        fallback=(workflows/"xiaomi-sm8850-os4-lkg.yml").read_text()
        archive=(workflows/"xiaomi-sm8850-os4-archive-lkg-release.yml").read_text()
        stage=(workflows/"pandora-os4-stage-status.yml").read_text()
        title="小米17 Pro OS4 / 晋升真机稳定内核为 LKG"
        legacy="旧 R62：核验候选并晋升稳定内核"
        self.assertIn(f'name: "{title}"',current)
        self.assertIn(f'      - "{title}"',fallback)
        self.assertIn(f'      - "{title}"',stage)
        self.assertIn(f'name: "{legacy}"',current)
        self.assertEqual(fallback.count('"' + legacy + '"'),2)
        self.assertNotIn('"小米17 Pro OS4 / 将自定义构建晋升为 LKG"',fallback)
        self.assertIn('      - "小米17 Pro OS4 / 当前 LKG 复现与打包"',archive)



if __name__=="__main__":
    unittest.main()
