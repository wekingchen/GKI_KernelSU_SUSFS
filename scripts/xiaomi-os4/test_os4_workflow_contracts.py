#!/usr/bin/env python3
"""Static cross-workflow contract checks for the OS4 multi-stage pipeline."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows"
DOCS = ROOT / "docs"


class WorkflowContracts(unittest.TestCase):
    def read(self, name):
        return (WF / name).read_text(encoding="utf-8")

    def test_failed_boot_reports_do_not_require_android_property_values(self):
        form = self.read("xiaomi-sm8850-os4-ota-test-feedback.yml")
        before, _, rest = form.partition("      observed_build:")
        build, _, rest = rest.partition("      observed_uname:")
        uname, _, rest = rest.partition("      confirmed_boot_completed:")
        self.assertIn("required: false", build)
        self.assertIn("required: false", uname)
        self.assertIn('if [[ "$TEST_RESULT" == pass ]]', form)
        self.assertIn('SOURCE_EXPECTED_BUILD=$BASE_BUILD', form)
        self.assertIn('实际读到的系统版本', form)
        self.assertIn('未能开机读取', form)

    def test_baseline_promotion_has_three_exact_file_gate(self):
        form = self.read("xiaomi-sm8850-os4-ota-test-feedback.yml")
        self.assertIn("ota-development-pointer.py", form)
        self.assertIn('[[ "$(git diff --cached --name-only | wc -l)" -eq 3 ]]', form)
        self.assertIn('[[ "$(wc -l <<<"$FILES")" -eq 3 ]]', form)

    def test_custom_paths_fail_closed_for_unverified_new_ota(self):
        source = self.read("xiaomi-sm8850-os4-custom.yml")
        self.assertIn("ota-development-pointer.py select", source)
        self.assertIn("needs.select-baseline.outputs.mode == 'legacy'", source)
        self.assertIn("needs.select-baseline.outputs.mode == 'ota'", source)
        self.assertIn("check-ota-feature-abi.py", source)
        self.assertIn("ccache-ota-*", source)
        self.assertIn("ota-custom-output/", source)
        self.assertIn("XIAOMI_AK3_MODE=ota-custom", source)

    def test_new_ota_artifact_never_advertised_as_lkg(self):
        source = self.read("xiaomi-sm8850-os4-custom.yml")
        self.assertIn('UNVERIFIED-AnyKernel3.zip', source)
        self.assertIn('ota-custom-abi-report.json', source)
        self.assertIn('不建议进行 AnyKernel3 持久安装', source)

    def test_lkg_promotion_is_explicitly_r62_only(self):
        source = self.read("xiaomi-sm8850-os4-promote-lkg.yml")
        self.assertIn('ARTIFACT_NAME="pandora-OS4-R62-CUSTOM-run-$SOURCE_RUN_ID"', source)
        self.assertIn("此晋升流程仍使用 R62 固定 ABI/KMI", source)
        self.assertIn('确认该构建已完成真机启动与持久化使用验证', source)

    def test_os4_docs_do_not_contain_superseded_claims(self):
        base = (DOCS / "xiaomi-17-pro-os4-ota-auto-baseline.md").read_text()
        howto = (DOCS / "xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md").read_text()
        lkg = (DOCS / "xiaomi-17-pro-os4-full-parity-lkg.md").read_text()
        self.assertIn("三份", base)
        self.assertIn("AnyKernel3", base)
        self.assertIn("不需要再回报一次", base)
        self.assertIn("实际 uname", howto)
        self.assertIn("模块数量", howto)
        self.assertIn("仅限来自 R62", lkg)
        for old in ("仅提交 .github/config/ota-verified/<新 build>/fixture.json 与 verification.json 两个新文件",
                    "新 OTA 首次功能版不会自动生成可持久刷入的 AnyKernel3"):
            self.assertNotIn(old, base)


if __name__ == "__main__":
    unittest.main()
