#!/usr/bin/env python3
"""Static end-to-end invariants for the Windows OTA stock collector.

Cannot emulate Windows/adb/hardware on Ubuntu CI. This catches incomplete
PowerShell statements, duplicate stale pack paths and missing OEM inputs.
"""
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / "collect-pandora-stock-input.cmd").read_text(encoding="utf-8-sig")


class WindowsOTACollectorIntegrity(unittest.TestCase):
    def test_one_complete_script_tail(self):
        self.assertEqual(len(re.findall(r"(?im)^endlocal\s*$", SOURCE)), 1)
        self.assertEqual(len(re.findall(r"(?im)^echo \[打包\] 生成 ", SOURCE)), 1)
        self.assertEqual(len(re.findall(r"(?im)^echo \[成功\] 已生成", SOURCE)), 1)
        self.assertTrue(SOURCE.rstrip().lower().endswith("endlocal"))

    def test_powershell_commands_have_balanced_quotes_and_continuations(self):
        lines = SOURCE.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('"') and stripped.endswith('^'):
                self.assertEqual(stripped.count('"') % 2, 0,
                                 f"odd quote count in PowerShell argument at line {i + 1}")
            if stripped.startswith("powershell -NoProfile"):
                self.assertTrue(stripped.endswith("^"))
        self.assertNotRegex(SOURCE, r"(?m)^\s*\"\$m=@.*\?\s*$")

    def test_critical_inputs_are_present_in_final_zip(self):
        marker = "Compress-Archive -Path '%OUT%\\boot.img'"
        self.assertIn(marker, SOURCE)
        pack = SOURCE[SOURCE.index(marker):]
        for name in ("boot.img", "init_boot.img", "vendor_boot.img",
                     "dtbo.img", "README.txt", "SHA256SUMS.txt",
                     "oem-modules.zip", "oem-modules-count.txt"):
            self.assertIn(name, pack)

    def test_module_count_manifest_and_archive(self):
        for text in ("MODULE_COUNT=", "4096", "500MB",
                     "Compress-Archive -Path '%OUT%\\oem_modules\\*'",
                     "oem-modules-count.txt"):
            self.assertIn(text, SOURCE)
        self.assertIn("Where-Object { $_.Name -match", SOURCE)
        self.assertIn(r"\.ko(\.zst|\.xz|\.gz)?$", SOURCE)

    def test_modules_are_read_via_root_without_device_writes(self):
        self.assertIn('adb exec-out su -c "tar -C /%%V/lib/modules -cf - ."', SOURCE)
        for prohibited in ("fastboot flash", "fastboot erase", "fastboot set_active",
                           "adb push ", "adb shell su -c \"cp ", "adb shell su -c \"dd "):
            # Documentation messages can mention prohibited verbs; only
            # reject actual executable code.
            for line in SOURCE.splitlines():
                if not line.lstrip().lower().startswith(("rem ", "echo ")):
                    self.assertNotIn(prohibited, line.lower())

    def test_all_failures_are_fail_closed(self):
        self.assertIn("if errorlevel 1 (", SOURCE)
        self.assertIn("exit /b 1", SOURCE)
        self.assertIn("if \"%OEM_DIRS%\"==\"0\"", SOURCE)
        self.assertIn('if(Test-Path -LiteralPath $o)', SOURCE)
        self.assertIn("del /q \"%OUT%\\modules-%%V.tar\"", SOURCE)


if __name__ == "__main__":
    unittest.main()
