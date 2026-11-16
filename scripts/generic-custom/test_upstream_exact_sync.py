#!/usr/bin/env python3
"""Safety contracts for exact-upstream automated merging."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTO = ROOT / ".github/workflows/upstream-exact-auto-sync.yml"
SCRIPT = ROOT / "scripts/upstream-sync/sync-exact-upstream.sh"
GENERIC = ROOT / ".github/workflows/generic-custom-auto-sync.yml"

class ExactUpstreamSync(unittest.TestCase):
    def test_scheduled_sync_requires_explicit_pat(self):
        wf = AUTO.read_text()
        self.assertIn('cron: "37 2 * * *"', wf)
        self.assertIn("refs/heads/dev", wf)
        self.assertIn("secrets.UPSTREAM_SYNC_PAT", wf)
        self.assertIn("actions/checkout@v7", wf)
        self.assertIn("contents: read", wf)

    def test_k50_sync_does_not_use_github_app_token_for_workflow_writes(self):
        wf = GENERIC.read_text()
        self.assertIn("secrets.UPSTREAM_SYNC_PAT", wf)
        self.assertNotIn("GH_TOKEN: ${{ github.token }}", wf)
        self.assertIn("缺少 UPSTREAM_SYNC_PAT", wf)

    def test_no_bypass_of_upstream_integrity_or_ci(self):
        s = SCRIPT.read_text()
        for key in (
            "git merge --no-ff --no-commit",
            "scripts/xiaomi-os4/check-upstream-isolation.sh",
            "--diff-filter=DMT",
            "gh pr create",
            "event=pull_request&head_sha=$CANDIDATE_SHA",
            'CONCLUSION" == success',
            "LIVE_UPSTREAM",
            "LIVE_DEV",
            'git push origin "$BRANCH"',
        ):
            self.assertIn(key, s)
        self.assertNotIn("git push origin HEAD:dev", s)
        self.assertNotIn("git push --force", s)
        self.assertNotIn("gh pr merge --admin", s)

    def test_shell_and_workflow_yaml_parse(self):
        bash = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(bash.returncode, 0, bash.stderr)
        ruby = subprocess.run(["ruby", "-ryaml", "-e", "YAML.parse_file(ARGV[0])",
                               str(AUTO)], capture_output=True, text=True)
        self.assertEqual(ruby.returncode, 0, ruby.stderr)

if __name__ == "__main__":
    unittest.main()
