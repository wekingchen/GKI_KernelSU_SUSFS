#!/usr/bin/env python3
"""Tests that soft-failed BBG and skipped stock config cannot be promoted."""
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "verify_fork_build_log", HERE / "verify_fork_build_log.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

GOOD = """2026-11-20T11:55:56Z 使用版本专用 stock config: config/stock_5.10.config
2026-11-20T11:55:56Z 已复制库存配置 -> common/arch/arm64/configs/stock_defconfig (6781 行)
2026-11-20T11:55:56Z 已替换 config_data 规则: common/kernel/Makefile
2026-11-20T11:58:02Z -- Baseband-guard: flask.h found, skip generation
2026-11-20T11:58:02Z -- Baseband-guard: Okay, Baseband_guard was found in CONFIG_LSM
2026-11-20T12:17:44Z CONFIG_LTO_CLANG_FULL=y
"""


class ForkBuildEvidence(unittest.TestCase):
    def test_realistic_good_output(self):
        mod.verify(GOOD)

    def test_stock_config_skipped(self):
        with self.assertRaisesRegex(ValueError, "Stock Config"):
            mod.verify(GOOD.replace("已复制库存配置 ->", "未复制 ->"))

    def test_missing_bbg_evidence(self):
        with self.assertRaisesRegex(ValueError, "BBG"):
            mod.verify(GOOD.replace("Okay, Baseband_guard", "Cannot find Baseband_guard"))

    def test_full_lto_required(self):
        with self.assertRaisesRegex(ValueError, "FULL LTO"):
            mod.verify(GOOD.replace("CONFIG_LTO_CLANG_FULL=y", "CONFIG_LTO_CLANG_THIN=y"))

    def test_host_ld_soft_fail_forbidden(self):
        with self.assertRaisesRegex(ValueError, "软失败"):
            mod.verify(GOOD + 'clang-12: error: Executable "ld" doesn\'t exist!\n')

    def test_fake_echo_does_not_count(self):
        with self.assertRaisesRegex(ValueError, "关键构建证据缺失"):
            mod.verify("\n".join("echo " + line for line in GOOD.splitlines()))

    def test_empty_fails(self):
        with self.assertRaisesRegex(ValueError, "日志为空"):
            mod.verify("")


if __name__ == "__main__":
    unittest.main()
