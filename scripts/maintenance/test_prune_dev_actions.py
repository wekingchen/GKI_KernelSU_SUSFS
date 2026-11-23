#!/usr/bin/env python3
"""Offline safety tests; does not require GitHub or delete actual runs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("prune-dev-actions.py")
spec = importlib.util.spec_from_file_location("prune_actions", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def run(i, name="小米内核 / 上游文件隔离门禁",
        status="completed", conclusion="success", event="pull_request"):
    return {
        "id": i, "name": name, "status": status,
        "conclusion": conclusion, "event": event,
        "created_at": f"2026-11-{i:02d}T01:00:00Z",
    }


class SafeActionPrune(unittest.TestCase):
    def test_old_repetitive_ci_only_beyond_retention(self):
        samples = [run(i) for i in range(1, 21)]
        deleted, _ = m.make_plan(samples, set(), 9999)
        self.assertEqual(set(deleted), set(range(2, 13)))
        self.assertNotIn(1, deleted)
        for i in range(13, 21):
            self.assertNotIn(i, deleted)
        self.assertGreater(len(deleted), 0)

    def test_manual_and_actual_ota_events_are_never_candidates(self):
        samples = [run(i) for i in range(1, 21)]
        samples[2]["event"] = "workflow_dispatch"
        samples[3]["event"] = "repository_dispatch"
        samples[4]["event"] = "workflow_run"
        samples[5]["event"] = "release"
        samples[6]["status"] = "in_progress"
        deleted, _ = m.make_plan(samples, set(), 9999)
        for run_id in (3, 4, 5, 6, 7):
            self.assertNotIn(run_id, deleted)

    def test_referenced_run_and_important_failure_preserved(self):
        samples = [run(i) for i in range(1, 25)]
        for i in (4, 9, 11, 15):
            samples[i-1]["conclusion"] = "failure"
        deleted, _ = m.make_plan(samples, {8}, 10)
        for i in (8, 10, 9, 11, 15):
            self.assertNotIn(i, deleted)

    def test_nonallowlisted_runs_are_always_preserved(self):
        samples = [run(i, name="小米17 Pro OS4 / 自定义内核") for i in range(1, 25)]
        deleted, _ = m.make_plan(samples, set(), 9999)
        self.assertEqual(deleted, [])

    def test_ci_for_unmerged_pr_head_is_preserved(self):
        samples = [run(i) for i in range(1, 25)]
        samples[3]["head_sha"] = "a"*40
        deleted, _ = m.make_plan(samples, set(), 9999, active_pr_heads={"a"*40})
        self.assertNotIn(4, deleted)

    def test_invalid_workflow_yaml_only_completed_ci_is_disposable(self):
        # These failed before creating a job; they contain no OTA evidence.
        broken=".github/workflows/pandora-actions-history-hygiene.yml"
        samples=[
            run(1,name=broken,event="push"),
            run(2,name=broken,event="push"),
            run(3,name=broken,event="workflow_dispatch"),
            run(4,name=broken,event="pull_request",status="in_progress"),
        ]
        deleted,_=m.make_plan(samples,{45196414652},9999)
        self.assertEqual(set(deleted),{1,2})

    def test_document_references_pin_run_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "docs"
            path.mkdir()
            (path/"audit.md").write_text("source run 45124613997 and\n"
                                          "https://github.com/example/actions/runs/45139674561\n")
            refs = m.referenced_run_ids(Path(d))
            self.assertIn(45124613997, refs)
            self.assertIn(45139674561, refs)


    def test_cleanup_workflow_branch_gate_is_bash_valid_and_fail_closed(self):
        import re
        import subprocess
        import textwrap

        workflow = (Path(__file__).resolve().parents[2]
                    / ".github/workflows/pandora-actions-history-hygiene.yml"
                    ).read_text(encoding="utf-8")
        self.assertIn('test("^(fix|chore)/pandora-ota-v2-")', workflow)
        for required in ('.head.sha == $sha', '.head.repo.full_name == $repo',
                         '.protected == false', '.merged_at != null',
                         '.base.ref == "dev"', 'git/refs/heads/$branch'):
            self.assertIn(required, workflow)

        # Parse Bash syntax from every YAML literal run block, including the
        # cleanup job that will execute with contents:write on dev.
        lines = workflow.splitlines(keepends=True)
        checked = 0
        for i, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*\|[-+]?\s*$", line)
            if not match:
                continue
            indent = len(match.group(1))
            body = []
            for part in lines[i+1:]:
                if part.strip() and len(part) - len(part.lstrip(" ")) <= indent:
                    break
                body.append(part)
            if not body:
                continue
            checked += 1
            check = subprocess.run(["bash", "-n"], input=textwrap.dedent(
                "".join(body)), text=True, capture_output=True, check=False)
            self.assertEqual(0, check.returncode,
                             f"Actions inline Bash at line {i+1}: {check.stderr}")
        self.assertGreaterEqual(checked, 3)


if __name__ == "__main__":
    unittest.main()
