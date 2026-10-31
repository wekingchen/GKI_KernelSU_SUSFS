#!/usr/bin/env python3
"""Synthetic routing / source-lock / core-ABI tests; no Xiaomi hardware or network."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROUTER = ROOT / "ota-development-pointer.py"
ABI = ROOT / "check-ota-feature-abi.py"
BUILD = "OS4.0.6.0.XBLCNXM"
UNAME = "6.12.80-android16-6-test-custom-4k"


def digest(b):
    return hashlib.sha256(b).hexdigest()


class DynamicOTA(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        rel = Path(".github/config/ota-verified") / BUILD
        self.folder = self.root / rel
        self.folder.mkdir(parents=True)
        self.record_path = rel / "verification.json"
        self.fixture_path = rel / "fixture.json"
        self.pointer_path = self.root / ".github/config/ota-development-current.json"
        self.report_path = self.root / "stock.json"
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.image = b"Linux version " + UNAME.encode() + b"\0" + b"K" * 4096
        self.symvers = "".join(f"0x{i:08x}\tsym_{i}\tvmlinux\tEXPORT_SYMBOL\n"
                               for i in range(100)).encode()
        (self.candidate / "Image").write_bytes(self.image)
        (self.candidate / "Module.symvers").write_bytes(self.symvers)
        (self.candidate / "final.config").write_text("CONFIG_MODVERSIONS=y\n")
        self.record = {
            "schema": 1, "status": "HUMAN_ATTESTED_BASELINE_BOOTED",
            "next_stage": "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION",
            "verification_mode": "USER_ATTESTATION_NOT_REMOTE_HARDWARE_PROOF",
            "safe_to_flash": False, "full_parity_lkg_promoted": False,
            "stock_build": BUILD, "kernel_release": UNAME, "kmi": "android16-6",
            "observed_build": BUILD, "observed_uname": UNAME,
            "stock_input_sha256": "a" * 64, "stock_boot_sha256": "b" * 64,
            "candidate_boot_sha256": "c" * 64,
            "candidate_image_sha256": digest(self.image),
            "module_symvers_sha256": digest(self.symvers),
            "candidate_gki_commit": "d" * 40,
            "stock_release_asset_id": 1234, "verification_run_id": 12345,
        }
        self.fixture = {
            "schema": 2, "safe_to_flash": False,
            "stock_build": BUILD, "stock_boot_sha256": self.record["stock_boot_sha256"],
            "stock_input_sha256": self.record["stock_input_sha256"],
            "tested_boot_sha256": self.record["candidate_boot_sha256"],
            "baseline_kernel_sha256": self.record["candidate_image_sha256"],
        }
        self.stock = {
            "status": "NEW_OTA_CANDIDATE", "kernel_marker_verified": True,
            "may_build_gki_candidate": True, "device": "pandora",
            "build": BUILD, "uname": UNAME,
            "ota_source_id": self.record["stock_input_sha256"],
            "stock_boot_sha256": self.record["stock_boot_sha256"],
            "github_asset_id": "1234",
        }
        self.write()
        self.new_pointer()

    def write(self):
        (self.root / self.record_path).write_text(json.dumps(self.record))
        (self.root / self.fixture_path).write_text(json.dumps(self.fixture))
        self.report_path.write_text(json.dumps(self.stock))

    def run_cmd(self, *args):
        return subprocess.run([sys.executable, *map(str, args)],
                              cwd=self.root, capture_output=True, text=True)

    def new_pointer(self):
        p = self.run_cmd(ROUTER, "create", "--record", self.record_path,
                     "--fixture", self.fixture_path,
                     "--output", self.pointer_path)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def select(self):
        return self.run_cmd(ROUTER, "select", "--stock-report", self.report_path,
                        "--root", self.root, "--pointer", self.pointer_path,
                        "--output", self.root / "route.txt")

    def test_valid_new_ota_selected_and_no_lkg_promotion(self):
        x = self.select()
        self.assertEqual(x.returncode, 0, x.stdout + x.stderr)
        self.assertEqual((self.root / "route.txt").read_text(), f"mode=ota\nbuild={BUILD}\n")
        self.assertFalse(json.loads(self.pointer_path.read_text())["full_parity_lkg_promoted"])

    def test_missing_verification_blocks_new_ota_instead_of_legacy(self):
        self.pointer_path.unlink()
        x = self.select()
        self.assertNotEqual(x.returncode, 0)
        self.assertIn("refusing old R62 fallback", x.stderr)

    def test_same_stock_without_pointer_selects_existing_legacy(self):
        self.pointer_path.unlink()
        self.stock["status"] = "SAME_PINNED_BUILD"
        self.stock["build"] = "OS4.0.5.0.XBLCNXM"
        self.write()
        x = self.select()
        self.assertEqual(x.returncode, 0, x.stderr)
        self.assertEqual((self.root / "route.txt").read_text(),
                         "mode=legacy\nbuild=OS4.0.5.0.XBLCNXM\n")

    def test_bad_release_asset_identity_fails_closed(self):
        self.stock["github_asset_id"] = "99999"
        self.write()
        self.assertNotEqual(self.select().returncode, 0)

    def test_modified_record_does_not_match_committed_pointer(self):
        self.record["candidate_gki_commit"] = "e" * 40
        self.write()
        self.assertNotEqual(self.select().returncode, 0)

    def test_prepare_only_accepts_original_candidate_and_clang(self):
        (self.candidate / "locked-candidate.env").write_text(
            "OTA_GKI_TAG=android16-6.12-2026-06_r8\n"
            "OTA_GKI_COMMIT=" + self.record["candidate_gki_commit"] + "\n"
            "OTA_KERNEL_VERSION=6.12.80\n"
            "OTA_KMI=android16-6\n"
            "OTA_BUILD=" + BUILD + "\n"
            "OTA_INPUT_SHA256=" + self.record["stock_input_sha256"] + "\n"
        )
        (self.candidate / "build-metadata.txt").write_text(
            "SOURCE_GKI_TAG=android16-6.12-2026-06_r8\n"
            "SOURCE_GKI_COMMIT=" + self.record["candidate_gki_commit"] + "\n"
            "KERNEL_RELEASE=" + UNAME + "\n"
            "IMAGE_SHA256=" + self.record["candidate_image_sha256"] + "\n"
            "SYMVERS_SHA256=" + self.record["module_symvers_sha256"] + "\n"
        )
        (self.candidate / "gki-candidate.json").write_text(json.dumps({
            "candidate_commit": self.record["candidate_gki_commit"]}))
        (self.candidate / "stock-report.json").write_text(json.dumps(self.stock))
        output = self.root / "ota.env"
        args = (ROUTER, "prepare", "--root", self.root,
                "--stock-report", self.report_path,
                "--pointer", self.pointer_path, "--candidate-dir", self.candidate,
                "--output", output)
        x = self.run_cmd(*args)
        self.assertEqual(x.returncode, 0, x.stdout + x.stderr)
        self.assertIn("OS4_KERNEL_VERSION=6.12.80", output.read_text())
        self.assertIn("OS4_GKI_COMMON_COMMIT=" + "d" * 40, output.read_text())
        (self.candidate / "Image").write_bytes(b"tampered candidate")
        self.assertNotEqual(self.run_cmd(*args).returncode, 0)

    def test_custom_features_drifted_kernel_abi_is_blocked(self):
        candidate_symvers = self.root / "feature.symvers"
        candidate_symvers.write_bytes(self.symvers)
        meta = self.root / "metadata.txt"
        meta.write_text(
            "SOURCE_COMMIT=" + self.record["candidate_gki_commit"] + "\n"
            "STOCK_RELEASE=" + UNAME + "\nKERNEL_RELEASE=" + UNAME + "\n"
            "SYMVERS_SHA256=" + digest(self.symvers) + "\n"
            "FLASHABLE=NO\nSELECTABLE_BUILD=1\n"
        )
        def check():
            return self.run_cmd(ABI,
                "--baseline-symvers", self.candidate / "Module.symvers",
                "--feature-symvers", candidate_symvers,
                "--baseline-record", self.root / self.record_path,
                "--feature-metadata", meta,
                "--report", self.root / "abi.json")
        self.assertEqual(check().returncode, 0)
        bad = self.symvers.decode().replace("0x00000001\tsym_1", "0x00000002\tsym_1")
        candidate_symvers.write_text(bad)
        meta.write_text(meta.read_text().replace(digest(self.symvers), digest(bad.encode())))
        x = check()
        self.assertNotEqual(x.returncode, 0)
        self.assertEqual(json.loads((self.root / "abi.json").read_text())["gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
