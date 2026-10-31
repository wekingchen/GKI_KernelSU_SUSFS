#!/usr/bin/env python3
"""Offline guards for experimental same-OTA AnyKernel3 packaging."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ota_ak3", HERE / "check-ota-anykernel-evidence.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

BUILD = "OS4.0.6.0.XBLCNXM"
UNAME = "6.12.80-android16-6-experiment-4k"
IMAGE = b"Linux version " + UNAME.encode() + b"\x00" + b"kernel bytes"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AnykernelEvidence(unittest.TestCase):
    def setUp(self):
        self.record = {
            "status": "HUMAN_ATTESTED_BASELINE_BOOTED",
            "next_stage": "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION",
            "verification_mode": "USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF",
            "device": "pandora", "safe_to_flash": False,
            "full_parity_lkg_promoted": False, "stock_build": BUILD,
            "observed_build": BUILD, "observed_uname": UNAME, "kernel_release": UNAME,
            "candidate_gki_commit": "a" * 40,
            "module_symvers_sha256": "b" * 64,
            "candidate_boot_sha256": "c" * 64,
            "stock_input_sha256": "d" * 64,
            "candidate_image_sha256": "e" * 64,
        }
        self.fixture = {
            "schema": 2, "safe_to_flash": False,
            "stock_build": BUILD, "tested_boot_sha256": "c" * 64,
            "stock_input_sha256": "d" * 64, "baseline_kernel_sha256": "e" * 64,
        }
        self.abi = {
            "gate": "PASS", "safe_to_flash": False,
            "full_parity_lkg_promoted": False, "missing_or_crc_changed_total": 0,
            "build": BUILD, "kernel_release": UNAME, "source_commit": "a" * 40,
            "baseline_symvers_sha256": "b" * 64,
            "feature_symvers_sha256": "f" * 64,
        }
        self.meta = {
            "BUILD_KIND": "OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED",
            "SYSTEM_BUILD": BUILD, "STOCK_RELEASE": UNAME,
            "KERNEL_RELEASE": UNAME, "SOURCE_COMMIT": "a" * 40,
            "IMAGE_SHA256": sha(IMAGE), "SYMVERS_SHA256": "f" * 64,
            "NEW_OTA_MODE": "1", "SELECTABLE_BUILD": "1", "FLASHABLE": "NO",
        }

    def check(self):
        CHECK.validate(self.record, self.fixture, self.abi,
                       self.meta, IMAGE, BUILD, UNAME)

    def test_all_gates_pass_but_feature_runtime_stays_unverified(self):
        self.check()
        self.assertEqual(self.meta["BUILD_KIND"], "OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED")
        self.assertFalse(self.record["full_parity_lkg_promoted"])

    def test_fail_without_ota_gki_human_attestation(self):
        self.record["status"] = "NEW_OTA_CANDIDATE"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_ota_fixture_from_another_version(self):
        self.fixture["stock_build"] = "OS4.0.9.0.XBLCNXM"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_when_original_gki_input_differs(self):
        self.fixture["stock_input_sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_custom_kmi_crc_gate_blocked(self):
        self.abi["gate"] = "BLOCKED"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_feature_symvers_not_consistent(self):
        self.meta["SYMVERS_SHA256"] = "0" * 64
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_actual_image_hash_mismatch(self):
        self.meta["IMAGE_SHA256"] = "0" * 64
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_custom_build_is_accidentally_lkg(self):
        self.meta["BUILD_KIND"] = "R62_OS4_SELECTABLE_FULL_PARITY_LKG"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_custom_build_has_wrong_kernel_release(self):
        self.meta["KERNEL_RELEASE"] = "6.12.69-android16-6-old-4k"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_custom_build_claims_flashable(self):
        self.meta["FLASHABLE"] = "YES"
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_gki_record_claims_flashable(self):
        self.record["safe_to_flash"] = True
        with self.assertRaises(SystemExit):
            self.check()

    def test_fail_if_unsupported_new_android_kmi(self):
        with self.assertRaises(SystemExit):
            CHECK.validate(self.record, self.fixture, self.abi, self.meta, IMAGE,
                           BUILD, "6.13.1-android17-7-other-4k")


if __name__ == "__main__":
    unittest.main()
