#!/usr/bin/env python3
"""Offline, negative-heavy tests for fail-closed resumed OTA LKG drafts."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("lkg_recovery", HERE / "check-ota-lkg-recovery.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DraftRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "source"
        self.res = self.root / "rebuilt"
        self.src.mkdir()
        self.res.mkdir()
        self.src.joinpath("Image").write_bytes(b"known original user tested kernel")
        src_image = digest(self.src.joinpath("Image").read_bytes())
        self.pointer = dict(
            schema=1, generation=6, status="USER_PROMOTED_OTA_LKG",
            device="pandora", stock_build="OS4.0.6.0.XBLCNXM",
            kernel_release="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k",
            gki_commit="a"*40, stock_input_sha256="b"*64,
            stock_release_asset_id=123, source_run_id=37,
        )
        self.manifest = dict(
            kind="PANDORA_OS4_OTA_COMPAT_CUSTOM_SOURCE",
            compat_custom_promotion=True,
            real_device_feature_test="USER_ATTESTED_AT_PROMOTION",
            source_run_id=39, source_head_sha="c"*40,
            stock_build=self.pointer["stock_build"],
            gki_commit=self.pointer["gki_commit"],
            image_sha256=src_image,
            boot_sha256="d"*64,
            anykernel_sha256="e"*64,
            selections={"ROOT_MODE":"bakasu-susfs"},
            upstream_commits={"BAKASU":"f"*40},
        )
        self.src.joinpath("ota-custom-source.json").write_text(
            json.dumps(self.manifest))
        self.reproduction = dict(
            source_image_sha256=src_image,
            rebuild_verification="NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS",
            rebuild_device_tested=False,
        )
        self.res.joinpath("reproduction-report.json").write_text(
            json.dumps(self.reproduction))
        self.record = dict(
            schema=1, status="USER_PROMOTED_OTA_LKG", generation=7,
            archive_tag="pandora-os4-lkg-gen7",
            device="pandora", stock_build=self.pointer["stock_build"],
            kernel_release=self.pointer["kernel_release"],
            gki_commit=self.pointer["gki_commit"],
            stock_input_sha256=self.pointer["stock_input_sha256"],
            stock_release_asset_id=123,
            source_run_id=39, source_head_sha="c"*40, promotion_run_id=7,
            image_sha256=src_image, boot_sha256="d"*64,
            anykernel_sha256="e"*64,
            legacy_r62_lkg_unchanged=True,
            attestation="USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF",
            reproduction=self.reproduction,
            source_manifest_sha256=digest(self.src.joinpath("ota-custom-source.json").read_bytes()),
            selections=copy.deepcopy(self.manifest["selections"]),
            upstream_commits=copy.deepcopy(self.manifest["upstream_commits"]),
        )
        self.source = dict(id=39, event="workflow_dispatch", head_branch="dev",
                           head_sha="c"*40, status="completed", conclusion="success",
                           path=MOD.SOURCE_WORKFLOW,
                           repository={"full_name":MOD.REPO})
        self.promotion = dict(id=7, event="workflow_dispatch", head_branch="dev",
                              head_sha="d"*40, status="completed", conclusion="failure",
                              path=MOD.WORKFLOW,
                              repository={"full_name":MOD.REPO})
        self.release = dict(
            draft=True, tag_name="pandora-os4-lkg-gen7",
            target_commitish="d"*40,
            body="SOURCE_RUN_ID=39\nPROMOTION_RUN_ID=7\n"
                 "STOCK_BUILD=OS4.0.6.0.XBLCNXM\n"
                 "USER_ATTESTED_ORIGINAL_AND_CI_REPRODUCED=YES\n",
        )

    def validate(self):
        return MOD.verify(self.pointer, self.record, self.release,
                          self.source, self.promotion, self.manifest,
                          self.src, self.res)

    def test_real_draft_can_be_replayed_without_claiming_new_rebuild(self):
        self.assertTrue(self.validate())

    def test_rejects_altered_pointer_or_gen(self):
        for changes in ({"generation":7}, {"gki_commit":"0"*40},
                        {"stock_input_sha256":"0"*64}):
            with self.subTest(changes=changes):
                self.pointer.update(changes)
                with self.assertRaises(ValueError):
                    self.validate()
                self.pointer.update(generation=6, gki_commit="a"*40,
                                    stock_input_sha256="b"*64)

    def test_rejects_foreign_source_or_workflow(self):
        self.source["repository"]["full_name"] = "attacker/elsewhere"
        with self.assertRaises(ValueError):
            self.validate()
        self.source["repository"]["full_name"] = MOD.REPO
        self.source["head_sha"] = "1"*40
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_promotion_that_did_not_fail_after_archiving(self):
        self.promotion["conclusion"] = "success"
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_mutated_or_published_draft(self):
        self.release["draft"] = False
        with self.assertRaises(ValueError):
            self.validate()
        self.release["draft"] = True
        self.release["target_commitish"] = "1"*40
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_wrong_source_run_or_false_attestation(self):
        self.record["source_run_id"] = 40
        with self.assertRaises(ValueError):
            self.validate()
        self.record["source_run_id"] = 39
        self.record["attestation"] = "NOT_ATTESTED"
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_modified_manifest_or_kernel_image(self):
        self.manifest["upstream_commits"]["BAKASU"] = "0"*40
        with self.assertRaises(ValueError):
            self.validate()
        self.manifest["upstream_commits"]["BAKASU"] = "f"*40
        self.src.joinpath("Image").write_bytes(b"wrong replacement kernel")
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_reproduction_proof_drift(self):
        self.reproduction["rebuild_verification"] = "NOT_VERIFIED"
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_origin_source_not_compat_custom(self):
        self.manifest["kind"] = "PANDORA_OS4_OTA_CUSTOM_SOURCE"
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
