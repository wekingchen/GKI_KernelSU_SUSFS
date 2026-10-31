#!/usr/bin/env python3
"""Offline synthetic tests: no phone, no real Xiaomi image, no network."""
from __future__ import annotations
import base64
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE / "package-ota-testboot-v4.py"
FINALIZE = HERE / "finalize-ota-baseline.py"
REPACK = HERE / "repack-fastboot-boot-v4-from-fixture.py"
RELEASE = "6.12.80-android16-6-ota-feedback-test-4k"
BUILD = "OS4.0.6.0.XBLCNXM"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *map(str, args)],
                          capture_output=True, text=True, check=False)


class SyntheticFeedback(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.image = self.base / "Image"
        self.stock_zip = self.base / "new-xm.zip"
        self.stock_report = self.base / "stock-report.json"
        self.gki = self.base / "gki-candidate.json"
        self.abi = self.base / "ota-abi-report.json"
        self.metadata = self.base / "build-metadata.txt"
        self.symvers = self.base / "Module.symvers"
        self.symvers.write_bytes(b"synthetic vmlinux CRC evidence\n")
        self.testboot = self.base / "testboot.img"
        self.outdir = self.base / "out"

        header = bytearray(4096)
        header[:8] = b"ANDROID!"
        kernel = b"Linux version " + RELEASE.encode() + b"\0" + b"K" * 12288
        struct.pack_into("<I", header, 8, len(kernel))
        struct.pack_into("<I", header, 12, 0)
        struct.pack_into("<I", header, 20, 1584)
        struct.pack_into("<I", header, 40, 4)
        stock_boot = bytes(header) + kernel
        stock_boot += b"\0" * (65536 - len(stock_boot))
        with zipfile.ZipFile(self.stock_zip, "w") as z:
            z.writestr("boot.img", stock_boot)
        new_image = b"Linux version " + RELEASE.encode() + b"\0" + b"X" * 14288
        self.image.write_bytes(new_image)

        self.stock = {
            "device": "pandora", "build": BUILD, "status": "NEW_OTA_CANDIDATE",
            "kernel_marker_verified": True, "may_build_gki_candidate": True,
            "safe_to_flash": False, "uname": RELEASE, "kmi": "android16-6",
            "ota_source_id": sha(self.stock_zip.read_bytes()),
            "stock_boot_sha256": sha(stock_boot), "github_asset_id": "42",
        }
        self.gki_data = {"ota_source_id": self.stock["ota_source_id"],
                         "candidate_commit": "a" * 40}
        self.abi_data = {
            "gate": "CRC_AND_VERMAGIC_MATCH_CANDIDATE",
            "eligible_for_fastboot_boot": True,
            "stock_input_sha256": self.stock["ota_source_id"],
            "stock_build": BUILD, "kernel_release": RELEASE,
            "candidate_commit": "a" * 40, "module_count": 12,
        }
        self.meta = {
            "STOCK_INPUT_SHA256": self.stock["ota_source_id"],
            "SOURCE_GKI_COMMIT": "a" * 40,
            "STOCK_BUILD": BUILD,
            "KERNEL_RELEASE": RELEASE,
            "IMAGE_SHA256": sha(new_image),
            "SYMVERS_SHA256": sha(self.symvers.read_bytes()),
        }
        self.sync()
        packed = run(PACK, "--stock-zip", self.stock_zip,
                     "--stock-report", self.stock_report,
                     "--abi-report", self.abi,
                     "--metadata", self.metadata,
                     "--candidate-image", self.image,
                     "--output", self.testboot)
        self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)

    def sync(self):
        for path, value in ((self.stock_report, self.stock),
                            (self.gki, self.gki_data), (self.abi, self.abi_data)):
            path.write_text(json.dumps(value), encoding="utf-8")
        self.metadata.write_text(
            "".join(f"{k}={v}\n" for k, v in self.meta.items()), encoding="utf-8"
        )

    def finalize(self, *, sha_override=None, observed_uname=RELEASE):
        return run(
            FINALIZE,
            "--stock-zip", self.stock_zip,
            "--stock-report", self.stock_report,
            "--gki-candidate", self.gki,
            "--abi-report", self.abi,
            "--metadata", self.metadata,
            "--image", self.image,
            "--testboot", self.testboot,
            "--output-dir", self.outdir,
            "--source-run-id", "1001",
            "--source-head-sha", "b" * 40,
            "--asset-id", "42",
            "--tested-sha256", sha_override or sha(self.testboot.read_bytes()),
            "--observed-uname", observed_uname,
            "--observed-build", BUILD,
            "--actor", "test-user",
            "--verification-run-id", "1002",
            "--verified-at", "2026-11-01T00:00:00Z",
        )

    def test_positive_gki_roundtrip_and_immutable_lkg_boundary(self):
        r = self.finalize()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fixture = json.loads((self.outdir / "fixture.json").read_text())
        rec = json.loads((self.outdir / "verification.json").read_text())
        self.assertEqual(fixture["schema"], 2)
        self.assertFalse(fixture["safe_to_flash"])
        self.assertEqual(fixture["boot_size"], 65536)
        self.assertEqual(fixture["tested_boot_sha256"], sha(self.testboot.read_bytes()))
        self.assertEqual(rec["next_stage"], "READY_FOR_VERSION_SCOPED_FEATURE_ADAPTATION")
        self.assertFalse(rec["full_parity_lkg_promoted"])
        rebuilt = self.base / "rebuilt.img"
        p = run(REPACK, self.outdir / "fixture.json", self.image, rebuilt,
                "--expected-image-sha256", sha(self.image.read_bytes()),
                "--expected-release", RELEASE, "--expected-build", BUILD,
                "--expected-output-sha256", fixture["tested_boot_sha256"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(rebuilt.read_bytes(), self.testboot.read_bytes())

    def test_reported_boot_sha_cannot_differ(self):
        r = self.finalize(sha_override="c" * 64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("provided SHA256", r.stdout + r.stderr)

    def test_reported_uname_must_match_source(self):
        r = self.finalize(observed_uname="6.12.80-android16-6-wrong-4k")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uname", r.stdout + r.stderr)

    def test_blocked_abi_cannot_be_certified(self):
        self.abi_data["eligible_for_fastboot_boot"] = False
        self.sync()
        r = self.finalize()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OEM static CRC", r.stdout + r.stderr)

    def test_changed_boot_even_with_user_supplied_sha_cannot_pass(self):
        boot = bytearray(self.testboot.read_bytes())
        boot[-12] = 3
        self.testboot.write_bytes(boot)
        r = self.finalize()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("byte-identical", r.stdout + r.stderr)

    def test_schema2_rejects_other_build_and_tampering(self):
        r = self.finalize()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        bad = self.base / "bad.img"
        p = run(REPACK, self.outdir / "fixture.json", self.image, bad,
                "--expected-image-sha256", sha(self.image.read_bytes()),
                "--expected-release", RELEASE,
                "--expected-build", "OS4.0.99.0.XBLCNXM")
        self.assertNotEqual(p.returncode, 0)
        f = json.loads((self.outdir / "fixture.json").read_text())
        f["boot_size"] -= 1
        (self.outdir / "fixture.json").write_text(json.dumps(f))
        p = run(REPACK, self.outdir / "fixture.json", self.image, bad,
                "--expected-image-sha256", sha(self.image.read_bytes()),
                "--expected-release", RELEASE, "--expected-build", BUILD)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
