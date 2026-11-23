#!/usr/bin/env python3
"""Tests for replaying exact upstream commits without changing inherited files."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("check-inherited-files.py")
spec = importlib.util.spec_from_file_location("inherited", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class InheritedFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "sync-test@example.invalid")
        self.git("config", "user.name", "Sync Test")
        self.path = Path(".github/workflows/get-manager.yml")
        self.path.parent.mkdir(parents=True)
        self.path.write_text("version=0\n")
        self.git("add", ".")
        self.git("commit", "-qm", "common")
        self.common = self.git("rev-parse", "HEAD")
        self.git("switch", "-q", "-c", "upstream")
        self.path.write_text("version=1\n")
        self.git("commit", "-qam", "new upstream manager")
        self.path.write_text("version=2\n")
        self.git("commit", "-qam", "new upstream arm64 manager")
        self.upstream = self.git("rev-parse", "HEAD")
        self.git("switch", "-q", "-c", "fork", self.common)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    @staticmethod
    def git(*args):
        return subprocess.check_output(["git", *args], text=True).strip()

    def test_identical_content_different_history_is_allowed(self):
        self.path.write_text("version=2\n")
        self.git("commit", "-qam", "pre-ported same new manager")
        fork = self.git("rev-parse", "HEAD")
        self.assertEqual(check.differing_inherited_files(
            self.common, fork, self.upstream), [])

    def test_real_private_override_is_rejected(self):
        self.path.write_text("version=bad\n")
        self.git("commit", "-qam", "bad local override")
        fork = self.git("rev-parse", "HEAD")
        self.assertEqual(check.differing_inherited_files(
            self.common, fork, self.upstream),
            [".github/workflows/get-manager.yml"])

    def test_changed_file_mode_is_rejected(self):
        self.path.write_text("version=2\n")
        self.path.chmod(0o755)
        self.git("add", ".")
        self.git("commit", "-qm", "same content but unsafe executable")
        fork = self.git("rev-parse", "HEAD")
        self.assertEqual(check.differing_inherited_files(
            self.common, fork, self.upstream),
            [".github/workflows/get-manager.yml"])

    def test_deletion_not_allowed_when_upstream_keeps_file(self):
        self.path.unlink()
        self.git("add", "-u")
        self.git("commit", "-qm", "deleted shared manager")
        fork = self.git("rev-parse", "HEAD")
        self.assertEqual(check.differing_inherited_files(
            self.common, fork, self.upstream),
            [".github/workflows/get-manager.yml"])

    def test_fork_only_added_files_not_blocked(self):
        new = Path("scripts/pandora-only.sh")
        new.parent.mkdir(exist_ok=True)
        new.write_text("echo harmless\n")
        self.git("add", ".")
        self.git("commit", "-qm", "private new path")
        fork = self.git("rev-parse", "HEAD")
        self.assertEqual(check.differing_inherited_files(
            self.common, fork, self.upstream), [])


if __name__ == "__main__":
    unittest.main()
