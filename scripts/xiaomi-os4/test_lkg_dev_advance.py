#!/usr/bin/env python3
"""Only unrelated OTA companion and diagnostic code may move dev during LKG build."""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = importlib.util.spec_from_file_location("dev_guard", HERE / "check-lkg-dev-advance.py")
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


class SafeAdvance(unittest.TestCase):
    def test_stage3_ota_companion_changes_from_original_failed_run_are_benign(self):
        paths = [
            ".github/workflows/pandora-os4-ota-companion-emulator.yml",
            ".github/workflows/pandora-os4-ota-diagnostic-intake.yml",
            ".github/workflows/pandora-os4-ota-v2-evidence-replay.yml",
            ".github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml",
            "docs/pandora-os4-guide.md",
            "scripts/xiaomi-os4/make-ota-v2-diagnostic-task.py",
            "scripts/xiaomi-os4/test_ota_v2_diagnostic_task.py",
            "scripts/xiaomi-os4/verify-ota-v2-diagnostic-evidence.py",
            "tools/pandora-ota-companion/README.md",
            "tools/pandora-ota-companion/app/src/main/AndroidManifest.xml",
        ]
        self.assertEqual(M.rejected(paths), [])

    def test_rejects_lkg_kernel_input_and_workflow_changes(self):
        for name in (
            ".github/config/ota-lkg-current.json",
            ".github/config/ota-verified/OS4.0.6.0.XBLCNXM/persistent-candidate.json",
            ".github/config/ota-development-current.json",
            "scripts/xiaomi-os4/build-r62-features.sh",
            "scripts/xiaomi-os4/cross-ota-lkg.py",
            "scripts/xiaomi-os4/check-lkg-dev-advance.py",
            ".github/workflows/xiaomi-sm8850-os4-promote-lkg.yml",
            ".github/workflows/xiaomi-sm8850-os4-custom.yml",
            ".github/workflows/pandora-os4-compat-custom-build-route-tests.yml",
            "security_patch/fix.patch",
            "kernel/common/Makefile",
        ):
            with self.subTest(name=name):
                self.assertEqual(M.rejected([name]), [name])

    def test_unknown_or_traversal_path_fails_closed(self):
        for name in (
            "", "../docs/README.md", "docs/../.github/config/ota-lkg-current.json",
            "docs\\..\\danger.py", "/docs/file.md", "docs/unsafe\nfile.md",
            "scripts/xiaomi-os4/not-allowlisted.py",
        ):
            with self.subTest(name=name):
                self.assertTrue(M.rejected([name]))


if __name__ == "__main__":
    unittest.main()
