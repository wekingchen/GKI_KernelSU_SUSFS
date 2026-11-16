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
                "    uses: ./.github/workflows/build-fork-custom.yml").replace(
                "    uses: ./.github/workflows/get-manager.yml",
                "    uses: ./.github/workflows/get-manager-fork.yml"))
        # Once native upstream has been restored, its menu may evolve
        # independently of the frozen emergency fallback selector.
        self.assertIn("uses: ./.github/workflows/build.yml", upstream)
        self.assertIn("uses: ./.github/workflows/build-fork-custom.yml", fork)

    def test_private_manager_is_exact_upstream_plus_patch(self):
        upstream = (WF / "get-manager.yml").read_text()
        private = (WF / "get-manager-fork.yml").read_text()
        self.assertIn("BAKASU_APKS", private)
        self.assertNotIn("BAKASU_APKS", upstream)
        check = subprocess.run(
            ["python3", str(ROOT / "scripts/generic-custom/sync_fork_manager.py"), "--check"],
            capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_susfs_compatibility_only_in_private_build(self):
        private = (WF / "build-fork-custom.yml").read_text()
        upstream = (WF / "build.yml").read_text()
        self.assertIn("generic-custom/susfs-compat-overlay.sh", private)
        self.assertNotIn("generic-custom/susfs-compat-overlay.sh", upstream)

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
        self.assertIn("prepare-lto-resources.sh", fork)
        self.assertIn("monitor-lto-build.sh", fork)
        self.assertIn("BUILD_CONFIG=common/build.config.gki.aarch64 build/build.sh", fork)
        self.assertNotIn("LTO=thin BUILD_CONFIG=", fork)
        self.assertIn("CONFIG_LTO_CLANG_THIN=y", fork)
        self.assertIn("BUILD_CONFIG=common/build.config.gki.aarch64 build/build.sh", fork)
        self.assertNotIn("prepare-host-linker.sh", original)

    def test_swap_planning_never_consumes_build_headroom(self):
        resource = ROOT / "scripts/generic-custom/prepare-lto-resources.sh"
        expected = ((20, 0), (31, 0), (32, 8), (35, 8),
                    (36, 12), (43, 12), (44, 16), (64, 16))
        for disk, swap in expected:
            with self.subTest(disk=disk):
                env = dict(os.environ,
                           GKI_RESOURCE_DRY_RUN="1",
                           GKI_TEST_DISK_GIB=str(disk))
                proc = subprocess.run(
                    ["bash", str(resource), "5.10"],
                    env=env, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn(f"GKI_SWAP_PLAN_GIB={swap}", proc.stdout)

    def test_resource_scripts_parse_without_host_privileges(self):
        for name in ("prepare-lto-resources.sh", "monitor-lto-build.sh"):
            with self.subTest(name=name):
                proc = subprocess.run(
                    ["bash", "-n", str(ROOT / "scripts/generic-custom" / name)],
                    capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_monitor_handles_cgroup_v2_v1_and_explicit_proc_fallback(self):
        monitor = ROOT / "scripts/generic-custom/monitor-lto-build.sh"
        for mode in ("v2", "v1", "proc"):
            with self.subTest(mode=mode):
                root = Path(self.temp.name) / f"monitor-{mode}"
                cg = root / "cgroup"
                proc = root / "proc"
                logs = root / "logs"
                cg.mkdir(parents=True)
                proc.mkdir(parents=True)
                (proc / "meminfo").write_text(
                    "MemTotal: 8192000 kB\nMemAvailable: 4096000 kB\n"
                    "SwapFree: 2048000 kB\n")
                (proc / "vmstat").write_text("oom_kill 3\n")
                if mode == "v2":
                    for name, value in {
                        "memory.current": "1234\n",
                        "memory.peak": "4567\n",
                        "memory.max": "8192\n",
                        "memory.events": "low 0\noom_kill 0\n",
                        "memory.swap.current": "200\n",
                    }.items():
                        (cg / name).write_text(value)
                elif mode == "v1":
                    mem = cg / "memory"
                    mem.mkdir()
                    for name, value in {
                        "memory.usage_in_bytes": "2048\n",
                        "memory.max_usage_in_bytes": "4096\n",
                        "memory.limit_in_bytes": "8192\n",
                        "memory.failcnt": "0\n",
                        "memory.memsw.usage_in_bytes": "2100\n",
                    }.items():
                        (mem / name).write_text(value)
                env = dict(os.environ,
                           GKI_MONITOR_CGROUP_ROOT=str(cg),
                           GKI_MONITOR_PROC_ROOT=str(proc),
                           RUNNER_TEMP=str(root))
                result = subprocess.run(
                    ["bash", str(monitor), str(logs), "--once"],
                    env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                expected_source = {"v2": "cgroup_v2", "v1": "cgroup_v1",
                                   "proc": "host_proc_only"}[mode]
                self.assertIn(f"memory_source={expected_source}", result.stdout)
                self.assertIn("host_mem_total_kb=8192000", result.stdout)
                self.assertIn("host_mem_available_kb=4096000", result.stdout)
                self.assertIn("host_oom_kill=3", result.stdout)
                if mode == "v2":
                    self.assertIn("memory_current_bytes=1234", result.stdout)
                    self.assertIn("memory_peak_bytes=4567", result.stdout)
                    self.assertIn("memory_events=[low 0 oom_kill 0 ", result.stdout)
                elif mode == "v1":
                    self.assertIn("memory_current_bytes=2048", result.stdout)
                    self.assertIn("memory_peak_bytes=4096", result.stdout)
                    self.assertIn("memory_events=[failcnt=0]", result.stdout)
                else:
                    self.assertIn("memory_current_bytes=unavailable", result.stdout)
                self.assertEqual((logs / "resource-samples.log").read_text().strip(),
                                 result.stdout.strip())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gki = Path(self.temp.name) / "gki"
        self.bin = self.gki / "build/build-tools/path/linux-x86"
        self.bin.mkdir(parents=True)
        self.ld = Path(self.temp.name) / "host-ld"
        self.ld.write_text("#!/bin/sh\nprintf 'mock GNU ld\n'\n")
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
