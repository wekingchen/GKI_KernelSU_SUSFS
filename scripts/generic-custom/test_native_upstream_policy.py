#!/usr/bin/env python3
"""Tests for CI-only automatic native upstream restoration."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "scripts/generic-custom/native_upstream_policy.py"
spec = importlib.util.spec_from_file_location("k50pro_native_policy", POLICY)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
ROUTE = ROOT / ".github/config/generic-custom-route.json"
NATIVE_CUSTOM = ROOT / ".github/workflows/kernel-custom.yml"
NATIVE_BUILD = ROOT / ".github/workflows/build.yml"


class NativeRestoration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.route = json.loads(ROUTE.read_text())
        cls.custom = NATIVE_CUSTOM.read_text()
        cls.build = NATIVE_BUILD.read_text()

    def test_route_retains_proven_real_build_in_both_modes(self):
        mod.validate_route(self.route)
        self.assertIn(self.route["mode"], ("fork", "upstream"))
        self.assertGreater(self.route.get("validated_kernel_run_id", 0), 0)

    def test_same_source_does_not_recompile(self):
        self.assertFalse(mod.needs_test(self.route, self.route["upstream_build_blob"],
                                        self.route["upstream_custom_blob"]))

    def test_either_upstream_file_change_retests(self):
        self.assertTrue(mod.needs_test(self.route, "a" * 40,
                                       self.route["upstream_custom_blob"]))
        self.assertTrue(mod.needs_test(self.route, self.route["upstream_build_blob"],
                                       "b" * 40))

    def test_native_original_workflow_compatibility(self):
        self.assertIn("uses: ./.github/workflows/build.yml", self.custom)
        mod.validate_native_source(self.build, self.custom)

    def test_old_thin_lto_upstream_rejected(self):
        sample = self.build + "\n        LTO=thin BUILD_CONFIG=common/build.config.gki.aarch64 build/build.sh\n"
        with self.assertRaisesRegex(ValueError, "Thin LTO"):
            mod.validate_native_source(sample, self.custom)

    def test_disabled_known_good_kernel_features_rejected(self):
        changed = self.custom.replace("use_bbg:", "use_alternative_flag:", 1)
        with self.assertRaisesRegex(ValueError, "menu removed"):
            mod.validate_native_source(self.build, changed)

    def test_removed_feature_forwarding_rejected(self):
        altered = self.custom.replace(
            "      use_bbg: ${{ inputs.use_bbg }}",
            "      use_bbg: false", 1)
        self.assertNotEqual(altered, self.custom)
        with self.assertRaisesRegex(ValueError, "stopped forwarding"):
            mod.validate_native_source(self.build, altered)

    def test_rewired_upstream_caller_rejected(self):
        changed = self.custom.replace("uses: ./.github/workflows/build.yml",
                                      "uses: ./.github/workflows/unknown.yml", 1)
        with self.assertRaisesRegex(ValueError, "native caller"):
            mod.validate_native_source(self.build, changed)

    def test_private_fork_patch_cannot_masquerade_as_upstream(self):
        with self.assertRaisesRegex(ValueError, "private fallback"):
            mod.validate_native_source(self.build + "gki-generic-build.swap\n",
                                       self.custom)

    def test_fail_invalid_state(self):
        for data in (dict(self.route, mode="blindly-switch"),
                     dict(self.route, upstream_custom_blob="bad"),
                     dict(self.route, schema=2)):
            with self.assertRaises(ValueError):
                mod.validate_route(data)

    def test_ci_success_promotes_without_device_flash_confirmation(self):
        out = mod.promoted_state(self.route, build_blob="a" * 40,
                                 custom_blob="b" * 40,
                                 commit="c" * 40, run_id=123456789)
        self.assertEqual(out["mode"], "upstream")
        self.assertEqual(out["validated_kernel_run_id"], 123456789)
        self.assertNotIn("confirm_flash", out)
        self.assertNotIn("confirm_boot", out)

    def test_fake_or_missing_ci_run_rejected(self):
        with self.assertRaisesRegex(ValueError, "unverified"):
            mod.promoted_state(self.route, build_blob="a" * 40,
                               custom_blob="b" * 40, commit="c" * 40, run_id=0)

    def test_upstream_mode_stops_private_patch_sync(self):
        run = (ROOT / "scripts/generic-custom/run_auto_sync.sh").read_text()
        self.assertIn('== upstream', run)
        self.assertIn("隔离修复版自动同步已停用", run)

    def test_native_release_requires_complete_build_artifacts_and_sources(self):
        run = (ROOT / "scripts/generic-custom/try_native_upstream.sh").read_text()
        for fragment in (
            'gh workflow run kernel-custom.yml',
            'gh api "repos/$GITHUB_REPOSITORY/actions/jobs/$KERNELJOB/logs"',
            'BakaSU_kernel-android12-5.10-209-AnyKernel3',
            'select(.conclusion=="success")',
            'CURRENT' if False else 'LIVE_DEV=',
            'LIVE_UPSTREAM=',
            'git push origin HEAD:dev',
            'gh api -X DELETE',
            'git switch -f dev',
            'CANDIDATE_SHA',
            '41239924766',
        ):
            self.assertIn(fragment, run)

    def test_scheduler_attempts_native_first_then_private(self):
        workflow = (ROOT / ".github/workflows/generic-custom-auto-sync.yml").read_text()
        self.assertIn("try_native_upstream.sh", workflow)
        self.assertIn("run_auto_sync.sh", workflow)
        run_body = workflow.split("run: |", 1)[-1]
        self.assertLess(run_body.index("try_native_upstream.sh"),
                        run_body.index("run_auto_sync.sh"))


if __name__ == "__main__":
    unittest.main()
