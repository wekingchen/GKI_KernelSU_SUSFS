#!/usr/bin/env python3
"""Keep upstream synchronization automatic without silently bypassing local guards."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "scripts/generic-custom/sync_fork_build.py"
s = importlib.util.spec_from_file_location("generic_build_sync", GEN)
mod = importlib.util.module_from_spec(s)
sys.modules[s.name] = mod
s.loader.exec_module(mod)
META = ROOT / ".github/config/generic-custom-upstream-sync.json"
FORK = ROOT / ".github/workflows/build-fork-custom.yml"
SHARED = ROOT / ".github/workflows/build.yml"


class RebaseSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = json.loads(META.read_text())
        cls.base = SHARED.read_text()
        cls.custom = FORK.read_text()

    def test_initial_baseline_byte_for_byte(self):
        self.assertEqual(mod.git_blob_sha(self.base),
                         self.state["private_base_blob_sha"])
        self.assertEqual(mod.render(self.base), self.custom)
        self.assertEqual(mod.unrender(self.custom), self.base)

    def test_idempotent_overlay_preserves_patch_anchors(self):
        with self.assertRaises(ValueError):
            mod.render(self.custom)
        with self.assertRaises(ValueError):
            mod.unrender(self.base)

    def test_new_upstream_content_propagates_with_all_private_patches(self):
        # Synthetic upstream addition in a region untouched by local fork.
        old = self.base
        new = old.replace("    runs-on: ubuntu-24.04\n",
                          "    runs-on: ubuntu-24.04\n    # upstream-new-note\n", 1)
        meta = dict(self.state, upstream_blob_sha=mod.git_blob_sha(old))
        nstate, built, changed = mod.sync(meta, old, new, self.custom)
        self.assertTrue(changed)
        self.assertIn("# upstream-new-note", built)
        self.assertIn("prepare-host-linker.sh", built)
        self.assertIn("    timeout-minutes: 360", built)
        self.assertEqual(nstate["upstream_blob_sha"], mod.git_blob_sha(new))
        self.assertEqual(nstate["private_base_blob_sha"],
                         mod.git_blob_sha(mod.unrender(built)))

    def test_identical_upstream_is_noop(self):
        meta = dict(self.state, upstream_blob_sha=mod.git_blob_sha(self.base))
        state, build, changed = mod.sync(meta, self.base, self.base, self.custom)
        self.assertFalse(changed)
        self.assertEqual(build, self.custom)
        self.assertEqual(state, meta)

    def test_old_upstream_blob_must_match(self):
        with self.assertRaisesRegex(ValueError, "prior upstream"):
            mod.sync(self.state, self.base, self.base, self.custom)

    def test_tampered_private_overlay_fails_closed(self):
        damaged = self.custom.replace('      JOBS: "2"', '      JOBS: "8"', 1)
        meta = dict(self.state, upstream_blob_sha=mod.git_blob_sha(self.base))
        with self.assertRaises(ValueError):
            mod.sync(meta, self.base, self.base, damaged)

    def test_missing_safety_gate_never_automerge(self):
        old = self.base
        new = old.replace("        uses: nick-fields/retry@v4",
                          "        uses: different-owner/retry@v9", 1)
        meta = dict(self.state, upstream_blob_sha=mod.git_blob_sha(old))
        with self.assertRaises(ValueError):
            mod.sync(meta, old, new, self.custom)

    def test_deleted_private_anchor_rejected(self):
        old = self.base
        new = old.replace("      - name: 编译内核\n",
                          "      - name: 新的编译步骤名称\n", 1)
        meta = dict(self.state, upstream_blob_sha=mod.git_blob_sha(old))
        with self.assertRaises(ValueError):
            mod.sync(meta, old, new, self.custom)

    def test_untrusted_metadata_rejected(self):
        state = dict(self.state, schema=2, upstream_blob_sha=mod.git_blob_sha(self.base))
        with self.assertRaises(ValueError):
            mod.sync(state, self.base, self.base, self.custom)

    def test_private_base_drift_rejected(self):
        state = dict(self.state, upstream_blob_sha=mod.git_blob_sha(self.base),
                     private_base_blob_sha="a" * 40)
        with self.assertRaises(ValueError):
            mod.sync(state, self.base, self.base, self.custom)

    def test_yaml_parser_can_parse_fork_snapshot(self):
        result = subprocess.run(["ruby", "-ryaml", "-e",
                                 "YAML.parse_file(ARGV[0])", str(FORK)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
