#!/usr/bin/env python3
"""使用实际 ARM64 ELF .ko 测试 ABI 比对器；不会触及任何手机。"""
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/xiaomi-os4/audit-vendor-kmi.py"
spec = importlib.util.spec_from_file_location("oem_kmi", SCRIPT)
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


class TestOemModuleAbi(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.modules = self.base / "modules"
        self.modules.mkdir()
        self.symvers = self.base / "Module.symvers"
        self.symvers.write_text("0x12345678\ttest_export\tvmlinux\tEXPORT_SYMBOL\t\n")
        self.compiler = shutil.which("clang")
        if not self.compiler:
            self.skipTest("clang not installed")

    def compile(self, content):
        source = self.base / "vendor.c"
        source.write_text(content)
        output = self.modules / "vendor.ko"
        subprocess.run([self.compiler, "--target=aarch64-linux-gnu", "-ffreestanding",
                        "-c", str(source), "-o", str(output)], check=True, capture_output=True)
        return output

    def classic(self, crc):
        self.compile(f"""
            struct v {{ unsigned long crc; char name[56]; }};
            __attribute__((used, section("__versions")))
            const struct v ver[] = {{{{0x{crc:08x}UL, "test_export"}}}};
            __attribute__((used, section(".modinfo")))
            const char vm[] = "vermagic=6.12.69-android16-6-test";
            extern int test_export(void);
            int k(void) {{return test_export();}}
        """.replace("{{", "{").replace("}}", "}"))

    def extended(self, crc):
        self.compile(f"""
            __attribute__((used, section("__version_ext_names")))
            const char names[] = "test_export";
            __attribute__((used, section("__version_ext_crcs")))
            const unsigned int crcs[] = {{0x{crc:08x}U}};
            extern int test_export(void);
            int k(void) {{return test_export();}}
        """)

    def test_classic_matching(self):
        self.classic(0x12345678)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 0)
        self.assertEqual(report["matched_vmlinux_crc"], 1)
        self.assertFalse(report["safe_to_flash"])

    def test_classic_mismatch(self):
        self.classic(0x12345679)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 1)
        self.assertEqual(report["verdict"], "CRC_CONFLICT_DETECTED")

    def test_candidate_other_module_crc_mismatch(self):
        self.symvers.write_text("0x12345678\\ttest_export\\tmm/zsmalloc\\tEXPORT_SYMBOL\\t\\n")
        self.classic(0x12345679)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 1)
        self.assertEqual(report["mismatched_vmlinux_crc"], 0)
        self.assertEqual(report["candidate_other_module_crc_mismatched"], 1)
        self.assertEqual(report["verdict"], "CANDIDATE_MODULE_CRC_CONFLICT_DETECTED")
        self.assertFalse(report["safe_to_flash"])

    def test_candidate_other_module_crc_matching(self):
        self.symvers.write_text("0x12345678\\ttest_export\\tmm/zsmalloc\\tEXPORT_SYMBOL\\t\\n")
        self.classic(0x12345678)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(report["candidate_other_module_crc_matched"], 1)
        self.assertEqual(report["candidate_other_module_crc_mismatched"], 0)
        self.assertFalse(report["safe_to_flash"])

    def test_extended_matching(self):
        self.extended(0x12345678)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 0)
        self.assertEqual(report["modules"][0]["format"], "extended")

    def test_extended_mismatch(self):
        self.extended(0x12345679)
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 1)

    def test_without_version_is_incomplete(self):
        self.compile("extern int test_export(void); int k(void) {return test_export();}")
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 2)

    def test_invalid_elf_is_incomplete(self):
        self.classic(0x12345678)
        (self.modules / "broken.ko").write_bytes(b"not an ELF module")
        report, code = abi.audit(self.symvers, self.modules)
        self.assertEqual(code, 2)
        self.assertEqual(report["errors_count"], 1)

    def test_symlink_module_never_silently_skipped(self):
        original = self.modules / "vendor.ko"
        self.classic(0x12345678)
        (self.modules / "vendor-link.ko").symlink_to(original)
        with self.assertRaisesRegex(ValueError, "软链接"):
            abi.audit(self.symvers, self.modules)

    def test_compressed_modules_never_silently_skipped(self):
        self.classic(0x12345678)
        (self.modules / "hidden.ko.zst").write_bytes(b"placeholder")
        with self.assertRaisesRegex(ValueError, "压缩模块"):
            abi.audit(self.symvers, self.modules)


if __name__ == "__main__":
    unittest.main()
