#!/usr/bin/env python3
"""Static safety-critical transaction/workflow contracts not requiring a phone.

Unlike the synthetic file handoff test, these check GitHub workflow wiring,
permission boundaries and the exact ordering of irreversible mutations.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows"
SCRIPTS = ROOT / "scripts/xiaomi-os4"


class TransactionSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.promote = (SCRIPTS / "run-cross-ota-lkg.sh").read_text()
        cls.lifecycle = (WF / "xiaomi-sm8850-os4-cross-ota-lkg.yml").read_text()
        cls.custom = (WF / "xiaomi-sm8850-os4-custom.yml").read_text()
        cls.feedback = (WF / "xiaomi-sm8850-os4-ota-test-feedback.yml").read_text()
        cls.candidate = (WF / "xiaomi-sm8850-os4-ota-auto-candidate.yml").read_text()
        cls.legacy = (WF / "xiaomi-sm8850-os4-promote-lkg.yml").read_text()

    def test_promotion_requires_real_owner_confirmation_three_times(self):
        for s in ("confirm_boot", "confirm_persistent", "confirm_runtime"):
            self.assertIn("inputs." + s, self.lifecycle)
            self.assertIn(s.upper(), self.lifecycle)
        self.assertIn('github.repository ==', self.lifecycle)
        self.assertIn('github.repository ==', self.lifecycle)

    def test_pr_and_sha_check_strictly_after_draft_checksum(self):
        draft = self.promote.index('gh release create "$TAG"')
        download = self.promote.index('gh release download "$TAG" --dir "$WORK/check-release"')
        verified = self.promote.index('verify-ota-lkg-release.py --dir "$WORK/check-release"')
        git_diff = self.promote.index('git diff --cached --name-only')
        merge = self.promote.index('gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$NUM/merge"')
        pub = self.promote.index('gh release edit "$TAG" --draft=false')
        self.assertTrue(draft < download < verified < git_diff < merge < pub)

    def test_old_stable_lkg_is_never_written_by_new_ota_promotion(self):
        for old in ("pandora-os4-full-parity-lkg.env",
                    "pandora-os4-r62-tested-boot-v4-fixture.json"):
            self.assertNotIn('git add "' + old, self.promote)
        self.assertIn('ota-lkg-current.json', self.promote)
        self.assertIn('ota-lkg-history/gen', self.promote)

    def test_new_ota_source_run_is_verified_dev_dispatch(self):
        for exact in ('.head_branch=="dev"', '.event=="workflow_dispatch"',
                      '.conclusion=="success"',
                      '.path==".github/workflows/xiaomi-sm8850-os4-custom.yml"',
                      'git merge-base --is-ancestor "$SOURCE_SHA" "$BASE_SHA"'):
            self.assertIn(exact, self.promote)

    def test_rebuild_uses_original_source_code_not_current_dev(self):
        self.assertIn('git worktree add --detach "$WORK/pinned-source" "$SOURCE_SHA"',
                      self.promote)
        self.assertIn('bash "$WORK/pinned-source/scripts/xiaomi-os4/build-r62-features.sh"',
                      self.promote)
        self.assertIn('export-ota-lkg-rebuild-env.py', self.promote)
        self.assertIn('compare --source-dir "$SRC" --rebuild-dir "$RES"', self.promote)

    def test_all_source_identity_gates_before_persistent_archive(self):
        for name in ("stock_release_asset_id", "ota-development-current.json",
                     "ota-verified/$BUILD/fixture.json",
                     "ota-verified/$BUILD/verification.json",
                     "check-ota-feature-abi.py",
                     "original-evidence.tar.zst", "rebuilt-evidence.tar.zst"):
            self.assertIn(name, self.promote)
        self.assertLess(self.promote.index('check-ota-feature-abi.py'),
                        self.promote.index('gh release create "$TAG"'))

    def test_custom_does_not_auto_promote_any_feature_build(self):
        self.assertIn('XIAOMI_AK3_MODE=ota-custom', self.custom)
        self.assertIn('ota-custom-source.json', (SCRIPTS / "cross-ota-lkg.py").read_text())
        self.assertNotIn('gh release edit "$TAG" --draft=false', self.custom)
        self.assertIn("needs.select-baseline.outputs.mode == 'ota'", self.custom)
        self.assertIn("needs.select-baseline.outputs.mode == 'legacy'", self.custom)

    def test_first_new_ota_requires_manual_baseline_not_hardware_claim(self):
        self.assertIn('confirmed_boot_completed', self.feedback)
        self.assertIn('confirmed_modules', self.feedback)
        self.assertIn('tested_boot_sha256', self.feedback)
        self.assertIn('finalize-ota-baseline.py', self.feedback)
        self.assertIn('check-ota-oem-abi.py', self.candidate)

    def test_release_recovery_cannot_bypass_current_pointer_and_checksums(self):
        self.assertIn('inputs.repair_draft_release', self.lifecycle)
        self.assertIn('verify-ota-lkg-release.py --dir "$WORK" --tag "$TAG"',
                      self.lifecycle)
        self.assertIn('cmp -s "$POINTER" "$WORK/ota-lkg-promotion-record.json"',
                      self.lifecycle)
        self.assertLess(
            self.lifecycle.index('verify-ota-lkg-release.py --dir "$WORK" --tag "$TAG"'),
            self.lifecycle.rindex('gh release edit "$TAG" --draft=false'))
        self.assertIn('gh api "repos/$GITHUB_REPOSITORY/contents/.github/config/ota-lkg-current.json?ref=dev"',
                      self.lifecycle)

    def test_stable_lkg_cannot_be_forged_by_legacy_r62_after_first_ota(self):
        self.assertIn('[[ -e .github/config/ota-lkg-current.json ]]', self.legacy)
        self.assertIn('此晋升流程仍使用 R62 固定 ABI/KMI', self.legacy)

    def test_build_ci_does_not_run_flash_commands_on_device(self):
        for path in ("run-cross-ota-lkg.sh", "cross-ota-lkg.py",
                     "finalize-ota-baseline.py", "ota-development-pointer.py"):
            data = (SCRIPTS / path).read_text()
            self.assertNotIn("fastboot flash ", data)
            self.assertNotIn("fastboot erase ", data)
            self.assertNotIn("fastboot set_active ", data)

    def test_one_real_ota_qa_matrix_is_permanent_ci_gate(self):
        guard = (WF / "xiaomi-upstream-isolation-guard.yml").read_text()
        for suite in ("test_ota_baseline_feedback.py",
                      "test_ota_development_switch.py",
                      "test_ota_anykernel_evidence.py",
                      "test_cross_ota_lkg.py",
                      "test_ota_lkg_release.py",
                      "test_os4_full_chain.py",
                      "test_os4_transaction_invariants.py"):
            self.assertIn(suite, guard)


if __name__ == "__main__":
    unittest.main()
