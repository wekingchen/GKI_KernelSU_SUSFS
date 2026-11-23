#!/usr/bin/env python3
"""Synthetic OS4 cross-OTA LKG transaction regressions (no phone or network)."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cross_lkg", HERE / "cross-ota-lkg.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
BUILD = "OS4.0.6.0.XBLCNXM"
RELEASE = "6.12.80-android16-6-ota-custom-4k"
RUN = "123456789"
HEAD = "b" * 40
COMPONENTS = MOD.COMPONENTS
IMAGE = b"Linux version " + RELEASE.encode() + b"\0" + b"I" * 2048


def sha(b):
    return hashlib.sha256(b).hexdigest()


class CrossOTALKGTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.rebuilt = self.root / "rebuilt"
        self.rebuilt.mkdir()
        self._write("Image", IMAGE)
        self._write("Module.symvers", b"0x00000001\tsome\tvmlinux\tEXPORT_SYMBOL\n" * 200)
        self._write("final.config", b"CONFIG_MODVERSIONS=y\n")
        self.rec = dict(device="pandora", status="HUMAN_ATTESTED_BASELINE_BOOTED",
                        next_stage="READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION",
                        safe_to_flash=False, full_parity_lkg_promoted=False,
                        stock_build=BUILD, kernel_release=RELEASE,
                        observed_build=BUILD, observed_uname=RELEASE,
                        candidate_boot_sha256="a" * 64,
                        stock_input_sha256="c" * 64,
                        candidate_image_sha256="d" * 64,
                        candidate_gki_commit="e" * 40,
                        module_symvers_sha256="f" * 64,
                        stock_release_asset_id=111, verification_run_id=222)
        self.fix = dict(schema=2, safe_to_flash=False, stock_build=BUILD,
                        tested_boot_sha256="a" * 64,
                        stock_input_sha256="c" * 64,
                        baseline_kernel_sha256="d" * 64)
        self.abi = dict(gate="PASS", safe_to_flash=False,
                        full_parity_lkg_promoted=False,
                        missing_or_crc_changed_total=0,
                        build=BUILD, kernel_release=RELEASE,
                        source_commit="e" * 40,
                        baseline_symvers_sha256="f" * 64,
                        feature_symvers_sha256=MOD.sha(self.source / "Module.symvers"))
        self.pins = {}
        self.meta = dict(BUILD_KIND="OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED",
                         NEW_OTA_MODE="1", SYSTEM_BUILD=BUILD,
                         STOCK_RELEASE=RELEASE, KERNEL_RELEASE=RELEASE,
                         SOURCE_COMMIT="e" * 40, SELECTABLE_BUILD="1",
                         FLASHABLE="NO", IMAGE_SHA256=sha(IMAGE),
                         SYMVERS_SHA256=self.abi["feature_symvers_sha256"],
                         ROOT_MODE="bakasu-susfs",
                         SUSFS_EXTRA_FEATURES="1", USE_NOMOUNT="1",
                         DROIDSPACES_ENABLED="1", USE_NTSYNC="0",
                         USE_BBG="0", USE_REKERNEL="0",
                         USE_NETWORKING="1", USE_CVE="1",
                         KBUILD_BUILD_TIMESTAMP="Sun Nov 01 00:00:00 UTC 2026",
                         UPSTREAM_CHANGED_COMPONENTS="BAKASU,SUSFS,NOMOUNT")
        for i, c in enumerate(COMPONENTS):
            commit = format(i + 1, "040x")
            kind = "branch" if c in ("BAKASU", "SUSFS", "NTSYNC") else "tag"
            ref = "main" if kind == "branch" else "v2.0.0"
            self.pins["RESOLVED_" + c + "_COMMIT"] = commit
            self.pins["RESOLVED_" + c + "_KIND"] = kind
            self.pins["RESOLVED_" + c + "_REF"] = ref
            self.meta[c + "_REF_KIND"] = kind
            self.meta[c + "_REF"] = ref
            if c in ("BAKASU", "SUSFS", "NOMOUNT", "DROIDSPACES"):
                self.meta[c + "_COMMIT"] = commit
        self.boot = self.source / f"pandora-{BUILD}-CUSTOM-run-{RUN}-UNVERIFIED-FASTBOOT-BOOT-ONLY.img"
        self.boot.write_bytes(b"ANDROID!" + b"boot" * 2048)
        self.zip = self.source / f"Xiaomi17Pro-pandora-{BUILD}-CUSTOM-run-{RUN}-UNVERIFIED-AnyKernel3.zip"
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("Image", IMAGE)
            z.writestr("anykernel.sh", "ui_print accepted")
        self.write()
        self.dummy_rebuild()

    def _write(self, name, data):
        (self.source / name).write_bytes(data)

    def write(self):
        for name, obj in (("verified-baseline.json", self.rec),
                          ("fixture.json", self.fix),
                          ("ota-custom-abi-report.json", self.abi)):
            (self.source / name).write_text(json.dumps(obj))
        for name, obj in (("build-metadata.txt", self.meta),
                          ("locked-upstreams.env", self.pins)):
            (self.source / name).write_text(
                "".join(f"{k}={v}\n" for k, v in obj.items()))
        (self.source / "image-reproducibility.env").write_text(
            f"IMAGE_SIZE={len(IMAGE)}\nIMAGE_SHA256={sha(IMAGE)}\n"
            "NORMALIZED_IMAGE_SHA256=" + "9" * 64 + "\n")

    def dummy_rebuild(self):
        for n in ("Image", "Module.symvers", "final.config", "build-metadata.txt",
                  "image-reproducibility.env"):
            (self.rebuilt / n).write_bytes((self.source / n).read_bytes())

    def identify(self):
        self.write()
        with patch("subprocess.run", return_value=CompletedProcess([], 0, "", "")):
            return MOD.identify(self.source, RUN, HEAD)

    def test_good_source_binds_all_pins_and_experimental_artifacts(self):
        m = self.identify()
        self.assertEqual(m["source_head_sha"], HEAD)
        self.assertEqual(len(m["upstream_refs"]), 7)
        self.assertEqual(m["anykernel_sha256"], MOD.sha(self.zip))
        self.assertFalse(m["full_parity_lkg_promoted"])

    def make_compat_persistent(self):
        self.rec.update(
            schema=2,
            status="HUMAN_ATTESTED_COMPAT_BASELINE_BOOTED",
            next_stage="READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION_NONFLASH",
            persistent_flash=False,
            compatibility_kind="PANDORA_RUST_BINDER_EEXIST_SHIM",
            compatibility_parameter="pandora_rust_binder_eexist=1",
            compatibility_image_sha256="1" * 64,
            compatibility_boot_sha256="2" * 64,
        )
        self.fix.update(
            tested_boot_sha256="2" * 64,
            baseline_kernel_sha256="1" * 64,
            compatibility_kind="PANDORA_RUST_BINDER_EEXIST_SHIM",
        )
        self.abi["compatibility_baseline"] = True

        self.zip.unlink()
        self.zip = self.source / "Xiaomi17Pro-pandora-OS4.0.6.0-run37-PERSISTENT-CANDIDATE-AnyKernel3.zip"
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("Image", IMAGE)
            z.writestr("anykernel.sh", "ui_print accepted")
        persistent = {
            "status":"PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY",
            "actual_persistent_install_verified":True,
            "lkg_promotion":True,
            "feature_workflow_run_id":int(RUN),
            "feature_image_sha256":sha(IMAGE),
            "package_sha256":MOD.sha(self.zip),
        }
        runtime = {
            "status":"PASS_RUNTIME_SELECTED_EXACT_OS406",
            "feature_workflow_run_id":int(RUN),
            "feature_image_sha256":sha(IMAGE),
            "unresolved_kernel_imports":0,
            "ambiguous_providers":0,
            "crc_mismatches":0,
            "failed_modules":0,
            "actual_persistent_install_verified":True,
            "lkg_promotion":True,
        }
        persistent_boot = {
            "status":"PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37",
            "feature_workflow_run_id":int(RUN),
            "feature_image_sha256":sha(IMAGE),
            "actual_persistent_install_verified":True,
            "lkg_promotion":True,
        }
        for name,obj in (
            ("persistent-candidate.json",persistent),
            ("runtime-selected-oem-gate.json",runtime),
            ("persistent-boot-equivalence.json",persistent_boot),
        ):
            (self.source/name).write_text(json.dumps(obj))
        self.write()

    def test_compat_persistent_source_requires_two_reboot_and_runtime_gate(self):
        self.make_compat_persistent()
        m=self.identify()
        self.assertEqual(m["kind"],"PANDORA_OS4_OTA_COMPAT_PERSISTENT_SOURCE")
        self.assertTrue(m["persistent_compatibility_source"])
        self.assertEqual(m["real_device_feature_test"],"TWO_PERSISTENT_REBOOTS_PASS")
        self.assertEqual(m["anykernel_sha256"],MOD.sha(self.zip))

    def test_compat_persistent_source_fails_if_persistence_is_revoked(self):
        self.make_compat_persistent()
        p=self.source/"persistent-candidate.json"
        obj=json.loads(p.read_text())
        obj["actual_persistent_install_verified"]=False
        p.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            self.identify()

    def test_compat_persistent_source_fails_if_runtime_ambiguity_returns(self):
        self.make_compat_persistent()
        p=self.source/"runtime-selected-oem-gate.json"
        obj=json.loads(p.read_text())
        obj["ambiguous_providers"]=1
        p.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            self.identify()

    def make_compat_custom(self):
        self.make_compat_persistent()
        for name in MOD.PERSISTENT_FILES:
            (self.source / name).unlink()
        self.zip.unlink()
        self.zip = self.source / (
            f"Xiaomi17Pro-pandora-{BUILD}-COMPAT-CUSTOM-run-{RUN}-UNVERIFIED-AnyKernel3.zip"
        )
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("Image", IMAGE)
            z.writestr("anykernel.sh", "ui_print accepted")
        self.meta["PANDORA_RUST_BINDER_EEXIST_SHIM"] = "1"
        self.meta["COMPATIBILITY_BASELINE_KIND"] = "PANDORA_RUST_BINDER_EEXIST_SHIM"
        previous = {
            "schema": 1, "generation": 6,
            "status": "USER_PROMOTED_OTA_LKG",
            "attestation": "USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF",
            "stock_build": BUILD, "kernel_release": RELEASE,
            "gki_commit": "e" * 40, "source_run_id": 777,
            "image_sha256": "0" * 64,
            "reproduction": {"symvers_sha256": self.abi["feature_symvers_sha256"]},
        }
        record = self.root / ".github/config/ota-lkg-current.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(previous))
        (self.source / MOD.COMPAT_CUSTOM_PROOF).write_text(json.dumps(previous))
        evidence = self.root / ".github/config/ota-verified" / BUILD
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "persistent-candidate.json").write_text(json.dumps({
            "status": "PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY",
            "feature_workflow_run_id": 777,
            "feature_image_sha256": "0" * 64,
            "actual_persistent_install_verified": True,
            "lkg_promotion": True,
        }))
        (evidence / "runtime-selected-oem-gate.json").write_text(json.dumps({
            "status": "PASS_RUNTIME_SELECTED_EXACT_OS406",
            "feature_workflow_run_id": 777,
            "feature_image_sha256": "0" * 64,
            "feature_module_symvers_sha256": self.abi["feature_symvers_sha256"],
            "unresolved_kernel_imports": 0, "ambiguous_providers": 0,
            "crc_mismatches": 0, "failed_modules": 0,
        }))
        (evidence / "persistent-boot-equivalence.json").write_text(json.dumps({
            "status": "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37",
            "feature_workflow_run_id": 777,
            "feature_image_sha256": "0" * 64,
        }))
        self.write()

    def test_compat_custom_has_independent_attested_source_and_trusted_anchor(self):
        self.make_compat_custom()
        with patch.object(MOD, "ROOT", self.root):
            result = self.identify()
        self.assertEqual(result["kind"], "PANDORA_OS4_OTA_COMPAT_CUSTOM_SOURCE")
        self.assertTrue(result["compat_custom_promotion"])
        self.assertFalse(result["persistent_compatibility_source"])
        self.assertEqual(result["real_device_feature_test"], "USER_ATTESTED_AT_PROMOTION")
        self.assertIn(MOD.COMPAT_CUSTOM_PROOF, result["files"])
        self.assertEqual(result["anykernel_sha256"], MOD.sha(self.zip))

    def test_compat_custom_rejects_untrusted_previous_lkg(self):
        self.make_compat_custom()
        p = self.source / MOD.COMPAT_CUSTOM_PROOF
        obj = json.loads(p.read_text())
        obj["source_run_id"] = 888
        p.write_text(json.dumps(obj))
        with patch.object(MOD, "ROOT", self.root), self.assertRaises(ValueError):
            self.identify()

    def test_compat_custom_rejects_oem_abi_drift(self):
        self.make_compat_custom()
        p = self.root / ".github/config/ota-verified" / BUILD / "runtime-selected-oem-gate.json"
        obj = json.loads(p.read_text())
        obj["feature_module_symvers_sha256"] = "1" * 64
        p.write_text(json.dumps(obj))
        with patch.object(MOD, "ROOT", self.root), self.assertRaises(ValueError):
            self.identify()

    def test_compat_custom_rejects_missing_eexist_shim(self):
        self.make_compat_custom()
        self.meta["PANDORA_RUST_BINDER_EEXIST_SHIM"] = "0"
        with patch.object(MOD, "ROOT", self.root), self.assertRaises(ValueError):
            self.identify()

    def test_compat_custom_rejects_relabelled_legacy_package(self):
        self.make_compat_custom()
        self.zip.rename(self.source / f"Xiaomi17Pro-pandora-{BUILD}-CUSTOM-run-{RUN}-UNVERIFIED-AnyKernel3.zip")
        with patch.object(MOD, "ROOT", self.root), self.assertRaises(ValueError):
            self.identify()

    def test_inert_metadata_may_contain_timestamp_and_commas(self):
        self.assertEqual(MOD.env(self.source / "build-metadata.txt")["UPSTREAM_CHANGED_COMPONENTS"],
                         "BAKASU,SUSFS,NOMOUNT")

    def test_wrong_ota_baseline_fails(self):
        self.rec["stock_build"] = "OS4.0.9.0.XBLCNXM"
        with self.assertRaises(ValueError):
            self.identify()

    def test_wrong_fixture_fails(self):
        self.fix["stock_input_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.identify()

    def test_crc_drift_fails(self):
        self.abi["gate"] = "BLOCKED"
        with self.assertRaises(ValueError):
            self.identify()

    def test_ref_or_tag_drift_fails_even_when_commit_matches(self):
        self.pins["RESOLVED_SUSFS_REF"] = "old"
        with self.assertRaises(ValueError):
            self.identify()

    def test_enabled_upstream_commit_drift_fails(self):
        self.meta["NOMOUNT_COMMIT"] = "0" * 40
        with self.assertRaises(ValueError):
            self.identify()

    def test_invalid_ref_chars_fail_closed(self):
        self.pins["RESOLVED_SUSFS_REF"] = "main;touch /tmp/pwned"
        with self.assertRaises(ValueError):
            self.identify()

    def test_legitimately_disabled_features_dont_require_commit(self):
        self.meta["ROOT_MODE"] = "none"
        self.meta["USE_NOMOUNT"] = "0"
        self.meta["DROIDSPACES_ENABLED"] = "0"
        for c in ("BAKASU", "SUSFS", "NOMOUNT", "DROIDSPACES"):
            self.meta[c + "_COMMIT"] = ""
        self.identify()

    def test_missing_archive_image_rejected(self):
        self.zip.unlink()
        with self.assertRaises(ValueError):
            self.identify()

    def test_reproduction_checks_exact_config_symvers_and_normalized_image(self):
        m = self.identify()
        report = MOD.compare_rebuild(self.source, self.rebuilt, m)
        self.assertFalse(report["rebuild_device_tested"])
        self.assertEqual(report["rebuild_verification"],
                         "NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS")

    def test_reproduction_changed_symvers_rejected(self):
        m = self.identify()
        (self.rebuilt / "Module.symvers").write_text("tampered")
        with self.assertRaises(ValueError):
            MOD.compare_rebuild(self.source, self.rebuilt, m)

    def test_reproduction_changed_normalized_image_rejected(self):
        m = self.identify()
        r = self.rebuilt / "image-reproducibility.env"
        r.write_text(r.read_text().replace("9" * 64, "8" * 64))
        with self.assertRaises(ValueError):
            MOD.compare_rebuild(self.source, self.rebuilt, m)

    def test_generation_from_old_gen3_is_four(self):
        m = self.identify()
        m["source_manifest_sha256"] = "1" * 64
        result = MOD.promotion_record(m, {"rebuild_verification": "pass"}, None, "989898", "test")
        self.assertEqual(result["generation"], 4)
        self.assertEqual(result["archive_tag"], "pandora-os4-lkg-gen4")
        self.assertFalse(result["legacy_r62_lkg_unchanged"] is False)

    def test_first_new_ota_generation_follows_actual_legacy_if_it_advanced(self):
        m = self.identify()
        m["source_manifest_sha256"] = "1" * 64
        result = MOD.promotion_record(m, {"rebuild_verification": "ok"}, None,
                                      "989898", "test", legacy_generation=5)
        self.assertEqual(result["generation"], 6)
        self.assertEqual(result["archive_tag"], "pandora-os4-lkg-gen6")
        with self.assertRaises(ValueError):
            MOD.promotion_record(m, {}, None, "989898", "bad", legacy_generation=0)

    def test_generations_increment_and_same_run_rejected(self):
        m = self.identify()
        m["source_manifest_sha256"] = "1" * 64
        prev = MOD.promotion_record(
            dict(m, source_run_id=333), {"rebuild_verification": "ok"},
            None, "888888", "old")
        new = MOD.promotion_record(m, {"rebuild_verification": "ok"}, prev, "999999", "new")
        self.assertEqual(new["generation"], 5)
        with self.assertRaises(ValueError):
            MOD.promotion_record(m, {}, new, "111111", "duplicate")

    def test_prevent_fake_promoted_run_without_human_evidence(self):
        self.rec["status"] = "NEW_OTA_CANDIDATE"
        with self.assertRaises(ValueError):
            self.identify()


if __name__ == "__main__":
    unittest.main()
