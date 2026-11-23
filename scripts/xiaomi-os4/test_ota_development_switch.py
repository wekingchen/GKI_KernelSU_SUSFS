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
        self.lkg_path = self.root / ".github/config/ota-lkg-current.json"
        self.persistent_path = self.root / ".github/config/ota-verified/OS4.0.6.0.XBLCNXM/persistent-candidate.json"
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
        self.assertEqual(
            (self.root / "route.txt").read_text(),
            f"mode=ota\nbuild={BUILD}\n"
            f"record_path=.github/config/ota-verified/{BUILD}/verification.json\n"
            f"fixture_path=.github/config/ota-verified/{BUILD}/fixture.json\n"
            "compatibility_mode=0\n",
        )
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


class CompatibilityOTA(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.build = "OS4.0.6.0.XBLCNXM"
        rel = Path(".github/config/ota-verified") / self.build
        self.record_path = rel / "compatibility-verification.json"
        self.fixture_path = rel / "compatibility-fixture.json"
        self.pointer_path = self.root / ".github/config/ota-development-current.json"
        self.lkg_path = self.root / ".github/config/ota-lkg-current.json"
        self.persistent_path = self.root / ".github/config/ota-verified/OS4.0.6.0.XBLCNXM/persistent-candidate.json"
        self.report_path = self.root / "stock.json"
        source_root = ROOT.parents[1]
        source_record = source_root / ".github/config/ota-verified" / self.build / "compatibility-verification.json"
        source_fixture = source_root / ".github/config/ota-verified" / self.build / "compatibility-fixture.json"
        self.record = json.loads(source_record.read_text())
        self.fixture = json.loads(source_fixture.read_text())
        self.stock = {
            "status": "NEW_OTA_CANDIDATE",
            "kernel_marker_verified": True,
            "may_build_gki_candidate": True,
            "device": "pandora",
            "build": self.build,
            "uname": self.record["kernel_release"],
            "ota_source_id": self.record["stock_input_sha256"],
            "stock_boot_sha256": self.record["stock_boot_sha256"],
            "github_asset_id": str(self.record["stock_release_asset_id"]),
        }
        self.write()

    def write(self):
        (self.root / self.record_path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.record_path).write_text(json.dumps(self.record))
        (self.root / self.fixture_path).write_text(json.dumps(self.fixture))
        self.report_path.write_text(json.dumps(self.stock))

    def run_cmd(self, *args):
        return subprocess.run([sys.executable, *map(str, args)],
                              cwd=self.root, capture_output=True, text=True)

    def create_pointer(self):
        return self.run_cmd(
            ROUTER, "create",
            "--record", self.record_path,
            "--fixture", self.fixture_path,
            "--output", self.pointer_path,
        )

    def select(self):
        return self.run_cmd(
            ROUTER, "select",
            "--stock-report", self.report_path,
            "--root", self.root,
            "--pointer", self.pointer_path,
            "--lkg-pointer", self.lkg_path,
            "--persistent-candidate", self.persistent_path,
            "--output", self.root / "route.txt",
        )

    def test_compatibility_baseline_routes_only_to_nonflash_ota_mode(self):
        created = self.create_pointer()
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        pointer = json.loads(self.pointer_path.read_text())
        self.assertEqual(pointer["status"], "VERIFIED_OTA_COMPATIBILITY_DEVELOPMENT_ONLY")
        self.assertFalse(pointer["full_parity_lkg_promoted"])
        selected = self.select()
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        route = (self.root / "route.txt").read_text()
        self.assertIn("mode=ota\n", route)
        self.assertIn("compatibility_mode=1\n", route)
        self.assertIn("compatibility-verification.json", route)
        self.assertIn("compatibility-fixture.json", route)

    def test_compatibility_persistent_custom_unlock_requires_promoted_lkg_and_two_reboots(self):
        created = self.create_pointer()
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        selected = self.select()
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertIn("persistent_compat_enabled=0\n",
                      (self.root / "route.txt").read_text())

        lkg = {
            "schema": 1,
            "status": "USER_PROMOTED_OTA_LKG",
            "device": "pandora",
            "generation": 6,
            "stock_build": self.build,
            "kernel_release": self.record["kernel_release"],
            "stock_input_sha256": self.record["stock_input_sha256"],
            "gki_commit": self.record["candidate_gki_commit"],
            "source_run_id": 45047763911,
            "image_sha256": "3" * 64,
            "anykernel_sha256": "4" * 64,
            "attestation": "USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF",
        }
        persistent = {
            "status": "PASS_TWO_TRUE_DEVICE_PERSISTENT_REBOOTS_LKG_READY",
            "device": "pandora",
            "stock_build": self.build,
            "kernel_release": self.record["kernel_release"],
            "feature_workflow_run_id": 45047763911,
            "feature_image_sha256": "3" * 64,
            "package_sha256": "4" * 64,
            "runtime_selected_oem_gate": "PASS_RUNTIME_SELECTED_EXACT_OS406",
            "persistent_boot_equivalence": "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37",
            "actual_persistent_install_verified": True,
            "lkg_promotion": True,
            "first_true_device_persistent_reboot": {"status": "PASS"},
            "second_true_device_persistent_reboot": {"status": "PASS"},
        }
        self.lkg_path.parent.mkdir(parents=True, exist_ok=True)
        self.lkg_path.write_text(json.dumps(lkg))
        self.persistent_path.parent.mkdir(parents=True, exist_ok=True)
        self.persistent_path.write_text(json.dumps(persistent))
        selected = self.select()
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertIn("persistent_compat_enabled=1\n",
                      (self.root / "route.txt").read_text())

        persistent["second_true_device_persistent_reboot"]["status"] = "PENDING"
        self.persistent_path.write_text(json.dumps(persistent))
        selected = self.select()
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertIn("persistent_compat_enabled=0\n",
                      (self.root / "route.txt").read_text())

    def test_compatibility_fixture_must_keep_eexist_and_not_blacklist_rust_binder(self):
        self.fixture["header_v4"]["cmdline"] = "module_blacklist=kernelsu"
        self.write()
        created = self.create_pointer()
        self.assertNotEqual(created.returncode, 0)
        self.assertIn("compatibility boot parameter missing", created.stderr)

    def test_compatibility_baseline_cannot_be_marked_flashable(self):
        self.record["safe_to_flash"] = True
        self.write()
        created = self.create_pointer()
        self.assertNotEqual(created.returncode, 0)
        self.assertIn("compatibility baseline identity mismatch: safe_to_flash", created.stderr)

    def test_prepare_delegates_to_exact_compatibility_baseline_validator(self):
        image = b"Linux version " + self.record["kernel_release"].encode() + b"\0" + b"K" * 4096
        symvers = "".join(
            f"0x{i:08x}\tsym_{i}\tvmlinux\tEXPORT_SYMBOL\n"
            for i in range(100)
        ).encode()
        self.record["candidate_gki_image_sha256"] = digest(image)
        self.record["module_symvers_sha256"] = digest(symvers)
        self.write()
        created = self.create_pointer()
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)

        candidate = self.root / "candidate"
        candidate.mkdir()
        (candidate / "Image").write_bytes(image)
        (candidate / "Module.symvers").write_bytes(symvers)
        (candidate / "final.config").write_text("CONFIG_MODVERSIONS=y\n")
        (candidate / "gki-candidate.json").write_text(json.dumps({
            "candidate_tag": self.record["candidate_gki_tag"],
            "candidate_commit": self.record["candidate_gki_commit"],
            "selection_reason": self.record["candidate_selection_reason"],
            "not_oem_source_proven": True,
        }))
        (candidate / "stock-report.json").write_text(json.dumps(self.stock))
        (candidate / "locked-candidate.env").write_text(
            f"OTA_GKI_TAG={self.record['candidate_gki_tag']}\n"
            f"OTA_GKI_COMMIT={self.record['candidate_gki_commit']}\n"
            "OTA_KERNEL_VERSION=6.12.69\n"
            "OTA_KMI=android16-6\n"
            f"OTA_BUILD={self.build}\n"
            f"OTA_INPUT_SHA256={self.record['stock_input_sha256']}\n"
        )
        (candidate / "build-metadata.txt").write_text(
            f"SOURCE_GKI_TAG={self.record['candidate_gki_tag']}\n"
            f"SOURCE_GKI_COMMIT={self.record['candidate_gki_commit']}\n"
            f"SOURCE_SELECTION={self.record['candidate_selection_reason']}\n"
            f"STOCK_UNAME={self.record['kernel_release']}\n"
            f"KERNEL_RELEASE={self.record['kernel_release']}\n"
            f"IMAGE_SHA256={digest(image)}\n"
            f"SYMVERS_SHA256={digest(symvers)}\n"
        )
        output = self.root / "verified-ota-source.env"
        prepared = self.run_cmd(
            ROUTER, "prepare",
            "--root", self.root,
            "--stock-report", self.report_path,
            "--pointer", self.pointer_path,
            "--candidate-dir", candidate,
            "--output", output,
        )
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        env = output.read_text()
        self.assertIn("OS4_PANDORA_RUST_BINDER_EEXIST_SHIM=1", env)
        self.assertIn("OS4_COMPATIBILITY_BASELINE_KIND=PANDORA_RUST_BINDER_EEXIST_SHIM", env)
        self.assertIn("OS4_PANDORA_RUST_BINDER_EEXIST_PATCH_SHA256=", env)


if __name__ == "__main__":
    unittest.main()
