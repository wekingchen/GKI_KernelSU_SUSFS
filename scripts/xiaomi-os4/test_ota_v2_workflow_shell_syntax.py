#!/usr/bin/env python3
"""Bash -n every literal shell run block on the OTA V2 route.

This is a syntax test, not a GitHub Actions parser or a proof that GitHub API
credentials/assets exist. It catches the here-doc/quoting errors missed by
Python unit tests of individual helpers.
"""
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ".github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml",
    ".github/workflows/pandora-os4-ota-diagnostic-intake.yml",
    ".github/workflows/pandora-os4-ota-v2-evidence-replay.yml",
    ".github/workflows/pandora-os4-stage-status.yml",
]


def literal_run_blocks(text):
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        match = re.match(r"^(\s*)run:\s*\|[-+]?\s*$", line)
        if not match:
            continue
        indent = len(match.group(1))
        body = []
        for content in lines[i+1:]:
            if content.strip() and len(content)-len(content.lstrip(" ")) <= indent:
                break
            body.append(content)
        if body:
            yield i+1, textwrap.dedent("".join(body))


class WorkflowShellSyntaxTest(unittest.TestCase):
    def test_all_literal_run_blocks_parse_as_bash(self):
        checked=0
        for path in WORKFLOWS:
            text=(ROOT/path).read_text(encoding="utf-8")
            for line, script in literal_run_blocks(text):
                with self.subTest(file=path, line=line):
                    run=subprocess.run(["bash","-n"],input=script,text=True,
                                       capture_output=True,check=False)
                    self.assertEqual(run.returncode,0,run.stderr)
                checked+=1
        self.assertGreaterEqual(checked,15,"Too few shell blocks checked; update YAML extractor")

    def test_diagnostic_intake_never_dispatches_rebuild(self):
        text=(ROOT/WORKFLOWS[1]).read_text(encoding="utf-8")
        self.assertIn("plan-ota-v2-recovery.py",text)
        self.assertIn("verify-ota-v2-diagnostic-evidence.py",text)
        self.assertNotIn("gh workflow run xiaomi-sm8850-os4-ota-auto-candidate.yml",text)
        self.assertNotIn("fastboot flash",text)


if __name__=="__main__":
    unittest.main()
