#!/usr/bin/env python3
"""Safety regression for fork-only Android 12 custom build overlay."""
import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows"
SCRIPT = ROOT / "scripts/generic-custom/prepare-host-linker.sh"


class ForkBuildChecks(unittest.TestCase):
    def test_upstream_shared_generic_workflows_are_not_rerouted(self):
        upstream = (WF / "kernel-custom.yml").read_text()
        fork = (WF / "kernel-custom-fork.yml").read_text()
        mode = json.loads((ROOT / ".github/config/generic-custom-route.json").read_text())["mode"]
        if mode == "fork":
            self.assertEqual(fork, upstream.replace(
                "name: Android 内核构建-自定义",
                "name: Android 内核构建-自定义（本仓隔离修复版）").replace(
                "    uses: ./.github/workflows/build.yml",
                "    uses: ./.github/workflows/build-fork-custom.yml"))
        # Once native upstream has been restored, its menu may evolve
        # independently of the frozen emergency fallback selector.
        self.assertIn("uses: ./.github/workflows/build.yml", upstream)
        self.assertIn("uses: ./.github/workflows/build-fork-custom.yml", fork)

    def test_fork_only_build_has_bounded_resources_and_real_timeout(self):
        original = (WF / "build.yml").read_text()
        fork = (WF / "build-fork-custom.yml").read_text()
        self.assertIn("    timeout-minutes:", original)
        self.assertIn("    timeout-minutes: 360", fork)
        self.assertIn("          timeout_minutes: 120", fork)
        self.assertIn("          max_attempts: 2", fork)
        self.assertIn('      JOBS: "2"', fork)
        self.assertIn('      MAKEFLAGS: "-j2 -l2"', fork)
        self.assertIn("prepare-host-linker.sh", fork)
        self.assertIn("sudo swapon", fork)
        self.assertIn("CONFIG_LTO_CLANG_THIN=y", fork)
        self.assertIn("BUILD_CONFIG=common/build.config.gki.aarch64 build/build.sh", fork)
        self.assertNotIn("prepare-host-linker.sh", original)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gki = Path(self.temp.name) / "gki"
        self.bin = self.gki / "build/build-tools/path/linux-x86"
        self.bin.mkdir(parents=True)
        self.ld = Path(self.temp.name) / "host-ld"
        self.ld.write_text("#!/bin/sh\nprintf 'mock GNU ld\\n'\n")
        self.ld.chmod(0o755)

    def run_script(self, *, ld_override=None):
        env = dict(os.environ, HOST_LD_OVERRIDE=str(ld_override or self.ld))
        return subprocess.run(["bash", str(SCRIPT), str(self.gki)],
                              env=env, capture_output=True, text=True)

    def test_host_ld_added_only_to_downloaded_tree(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.bin / "ld").resolve(), self.ld)

    def test_idempotent_and_preserve_existing_ld(self):
        target = self.bin / "ld"
        target.symlink_to(self.ld)
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(target.resolve(), self.ld)

    def test_missing_host_ld_fails_closed(self):
        result = self.run_script(ld_override=self.gki / "missing")
        self.assertNotEqual(result.returncode, 0)

    def test_broken_link_fails_closed(self):
        (self.bin / "ld").symlink_to(self.gki / "missing")
        self.assertNotEqual(self.run_script().returncode, 0)

    def test_existing_nonexecutable_linker_fails_closed(self):
        (self.bin / "ld").write_text("not executable")
        self.assertNotEqual(self.run_script().returncode, 0)

    def test_missing_build_tools_fails_closed(self):
        self.bin.rmdir()
        self.assertNotEqual(self.run_script().returncode, 0)


if __name__ == "__main__":
    unittest.main()
