#!/usr/bin/env python3
"""Synthetic completeness and tamper checks for OTA LKG Release assets."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
S=importlib.util.spec_from_file_location("release_verify", HERE/"verify-ota-lkg-release.py")
V=importlib.util.module_from_spec(S)
S.loader.exec_module(V)
TAG="pandora-os4-lkg-gen4"
BUILD="OS4.0.6.0.XBLCNXM"
PREFIX=BUILD+"-Gen4-"


class ReleaseGate(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.record={"schema":1,"status":"USER_PROMOTED_OTA_LKG",
                     "generation":4,"archive_tag":TAG,"stock_build":BUILD,
                     "source_run_id":123,"selections":{"ROOT_MODE":"none"}}
        self.files={
          PREFIX+"ORIGINAL-USER-ATTESTED-boot.img":b"OB",
          PREFIX+"ORIGINAL-USER-ATTESTED-AnyKernel3.zip":b"OA",
          PREFIX+"REBUILT-CI-ONLY-boot.img":b"RB",
          PREFIX+"REBUILT-CI-ONLY-AnyKernel3.zip":b"RA",
          PREFIX+"original-evidence.tar.zst":b"source data",
          PREFIX+"rebuilt-evidence.tar.zst":b"replay data",
          "README-RECOVERY.md":b"pandora only",
          "ota-lkg-promotion-record.json":json.dumps(self.record).encode()
        }
        self.write()

    def write(self):
        for name, content in self.files.items():
            (self.root/name).write_bytes(content)
        lines=["%s  %s" % (hashlib.sha256(v).hexdigest(), k)
               for k,v in sorted(self.files.items())]
        (self.root/("SHA256SUMS-"+TAG+".txt")).write_text("\n".join(lines)+"\n")

    def check(self):
        return V.verify(self.root,TAG)

    def test_exact_complete_release_is_valid(self):
        self.assertEqual(self.check()["generation"],4)

    def test_unlisted_extra_asset_rejected(self):
        (self.root/"unexpected.img").write_text("untracked")
        with self.assertRaises(ValueError):
            self.check()

    def test_asset_tamper_rejected(self):
        (self.root/(PREFIX+"ORIGINAL-USER-ATTESTED-boot.img")).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_reproduced_package_rejected(self):
        p=self.root/(PREFIX+"REBUILT-CI-ONLY-AnyKernel3.zip")
        p.unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_generation_rejected(self):
        with self.assertRaises(ValueError):
            V.verify(self.root,"pandora-os4-lkg-gen5")

    def test_root_enabled_missing_manager_rejected(self):
        self.record["selections"]["ROOT_MODE"]="bakasu-susfs"
        self.files["ota-lkg-promotion-record.json"]=json.dumps(self.record).encode()
        self.write()
        with self.assertRaises(ValueError):
            self.check()

    def test_root_enabled_manager_evidence_passes(self):
        self.record["selections"]["ROOT_MODE"]="bakasu-susfs"
        self.files["ota-lkg-promotion-record.json"]=json.dumps(self.record).encode()
        self.files[PREFIX+"manager-evidence.tar.zst"]=b"manager"
        self.write()
        self.check()

    def test_duplicate_manifest_entry_rejected(self):
        m=self.root/("SHA256SUMS-"+TAG+".txt")
        m.write_text(m.read_text()+m.read_text().splitlines()[0]+"\n")
        with self.assertRaises(ValueError):
            self.check()


if __name__=="__main__":
    unittest.main()
