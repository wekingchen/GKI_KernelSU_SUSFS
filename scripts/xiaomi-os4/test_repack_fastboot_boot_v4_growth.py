#!/usr/bin/env python3
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPACK = ROOT / "scripts/xiaomi-os4/repack-fastboot-boot-v4-from-fixture.py"
BUILD = "OS4.0.6.0.XBLCNXM"
RELEASE = "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RepackGrowth(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = self.root / "fixture.json"
        self.image = self.root / "Image"
        self.output = self.root / "boot.img"
        image = RELEASE.encode() + b"\0" + b"K" * 5000
        self.image.write_bytes(image)
        self.image_sha = digest(image)
        self.fixture_data = {
            "schema": 2,
            "safe_to_flash": False,
            "stock_build": BUILD,
            "header_version": 4,
            "header_size": 1584,
            "kernel_size": 4096,
            "ramdisk_size": 0,
            "signature_size": 0,
            "boot_size": 8192,
            "header_v4": {
                "os_version": 0,
                "reserved": [0, 0, 0, 0],
                "cmdline": "pandora_rust_binder_eexist=1 module_blacklist=kernelsu",
            },
            "ramdisk_region_b64": base64.b64encode(b"").decode(),
            "suffix_b64": base64.b64encode(b"").decode(),
            "baseline_kernel_sha256": "0" * 64,
            "tested_boot_sha256": "1" * 64,
        }
        self.write_fixture()

    def write_fixture(self):
        self.fixture.write_text(json.dumps(self.fixture_data), encoding="utf-8")

    def run_repack(self, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(REPACK),
                str(self.fixture),
                str(self.image),
                str(self.output),
                "--expected-image-sha256",
                self.image_sha,
                "--expected-release",
                RELEASE,
                "--expected-build",
                BUILD,
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def test_growth_is_blocked_without_explicit_nonflash_flag(self):
        result = self.run_repack()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate cannot fit in this OTA's recorded boot image", result.stderr)

    def test_growth_flag_builds_structured_header_v4_fastboot_boot_image(self):
        result = self.run_repack("--fastboot-boot-only-allow-growth")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.output.is_file())
        # PAGE + aligned 5k-ish Image = 4096 + 8192 = 12288.
        self.assertEqual(self.output.stat().st_size, 12288)
        self.assertIn("output_size=12288", result.stdout)
        self.assertIn("boot_file_growth=4096", result.stdout)
        self.assertIn("FLASHABLE=NO", result.stdout)
        self.assertIn("USE=fastboot boot ONLY", result.stdout)

    def test_growth_flag_still_rejects_flashable_fixture(self):
        self.fixture_data["safe_to_flash"] = True
        self.write_fixture()
        result = self.run_repack("--fastboot-boot-only-allow-growth")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture must remain fastboot-boot-only", result.stderr)

    def test_structured_header_keeps_eexist_and_kernelsu_guard(self):
        result = self.run_repack("--fastboot-boot-only-allow-growth")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pandora_rust_binder_eexist=1", result.stdout)
        self.assertIn("module_blacklist=kernelsu", result.stdout)

    def test_real_repo_os406_fixture_accepts_nonflash_growth(self):
        real_fixture = ROOT / ".github/config/ota-verified/OS4.0.6.0.XBLCNXM/compatibility-fixture.json"
        fixture = json.loads(real_fixture.read_text(encoding="utf-8"))
        self.assertEqual(fixture["stock_build"], BUILD)
        self.assertFalse(fixture["safe_to_flash"])
        self.assertEqual(fixture["header_v4"]["cmdline"],
                         "module_blacklist=kernelsu pandora_rust_binder_eexist=1")

        # Cross the real recorded boot-file envelope by one byte of kernel
        # payload. Alignment then requires exactly one extra 4 KiB page.
        real_image_size = fixture["boot_size"] - 4096 + 1
        marker = RELEASE.encode() + b"\0"
        image = marker + b"K" * (real_image_size - len(marker))
        self.image.write_bytes(image)
        self.image_sha = digest(image)
        self.fixture = real_fixture

        result = self.run_repack("--fastboot-boot-only-allow-growth")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected_size = fixture["boot_size"] + 4096
        self.assertEqual(self.output.stat().st_size, expected_size)
        self.assertIn(f"output_size={expected_size}", result.stdout)
        self.assertIn("boot_file_growth=4096", result.stdout)
        self.assertIn("FINAL_BOOT_V4_AUDIT=PASS", result.stdout)
        self.assertIn("FLASHABLE=NO", result.stdout)


if __name__ == "__main__":
    unittest.main()
