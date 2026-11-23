#!/usr/bin/env python3
"""Offline regression for the OS4.0.6 compatibility AnyKernel3 upgrade path.

Execute the package generator's actual shell fragments against synthetic
existing boot cmdlines, including those from earlier custom kernels.
No phone partitions are accessed.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PACKAGE_SCRIPT = HERE / "package-validated-anykernel3.sh"


def installer_fragments():
    source = PACKAGE_SCRIPT.read_text(encoding="utf-8")
    common_start = source.index("split_boot;\n\n") + len("split_boot;\n\n")
    common_end = source.index("\n@@COMPAT_PATCH@@", common_start)
    common = source[common_start:common_end]
    compat_start = source.index('    compat_patch = r"""') + len('    compat_patch = r"""')
    compat_end = source.index('"""', compat_start)
    return common, source[compat_start:compat_end]


# Pin-compatible patch_cmdline from osm0sis/AnyKernel3
# dca9dc370838d919d56c1f59ec78b27a14a72c68, tools/ak3-core.sh.
PATCH_CMDLINE = r'''
patch_cmdline() {
  local cmdfile cmdtmp match;
  if [ -f "$SPLITIMG/cmdline.txt" ]; then
    cmdfile=$SPLITIMG/cmdline.txt;
  else
    cmdfile=$AKHOME/cmdtmp;
    grep "^cmdline=" $SPLITIMG/header | cut -d= -f2- > $cmdfile;
  fi;
  if ! grep -q "$1" $cmdfile; then
    cmdtmp=$(cat $cmdfile);
    echo "$cmdtmp $2" > $cmdfile;
    sed -i -e 's;^[ \t]*;;' -e 's;  *; ;g' -e 's;[ \t]*$;;' $cmdfile;
  else
    match=$(grep -o "$1.*$" $cmdfile | cut -d\  -f1);
    sed -i -e "s;${match};${2};" -e 's;^[ \t]*;;' -e 's;  *; ;g' -e 's;[ \t]*$;;' $cmdfile;
  fi;
  if [ -f "$AKHOME/cmdtmp" ]; then
    sed -i "s|^cmdline=.*|cmdline=$(cat $cmdfile)|" $SPLITIMG/header;
    rm -f $cmdfile;
  fi;
}
'''


class CompatibilityInstallerCmdline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common, cls.compat = installer_fragments()

    def execute(self, initial, *, cmdline_file):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            split = root / "split"
            split.mkdir()
            (split / "header").write_text("cmdline=" + initial + "\n")
            if cmdline_file:
                (split / "cmdline.txt").write_text(initial + "\n")
            shell = (
                'abort() { echo "ABORT:$1" >&2; exit 23; }\n'
                + PATCH_CMDLINE + "\n"
                + self.common + "\n"
                + self.compat + "\n"
                + 'if [ -f "$SPLITIMG/cmdline.txt" ]; then '
                  'cat "$SPLITIMG/cmdline.txt"; '
                  'else grep "^cmdline=" "$SPLITIMG/header" | cut -d= -f2-; fi\n'
            )
            env = dict(os.environ, SPLITIMG=str(split), AKHOME=str(root))
            return subprocess.run(["bash", "-c", shell], env=env,
                                  text=True, capture_output=True, check=False)

    def test_template_newline_escape_is_not_double_escaped(self):
        self.assertNotIn(r"\\n", self.compat)
        self.assertIn(r"'\n'", self.compat)

    def test_upgrade_existing_custom_with_valid_flags(self):
        for cmdline_file in (True, False):
            with self.subTest(cmdline_file=cmdline_file):
                result = self.execute(
                    "console=tty0 module_blacklist=kernelsu "
                    "pandora_rust_binder_eexist=1", cmdline_file=cmdline_file)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.count("module_blacklist="), 1)

    def test_upgrade_append_kernelsu_to_other_blacklist_entries(self):
        result = self.execute(
            "console=tty0 module_blacklist=foo pandora_rust_binder_eexist=1",
            cmdline_file=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("module_blacklist=foo,kernelsu", result.stdout)

    def test_upgrade_add_missing_blacklist_and_eexist(self):
        result = self.execute("console=tty0", cmdline_file=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("module_blacklist=kernelsu", result.stdout)
        self.assertIn("pandora_rust_binder_eexist=1", result.stdout)

    def test_duplicate_blacklist_is_rejected(self):
        result = self.execute(
            "module_blacklist=kernelsu module_blacklist=foo "
            "pandora_rust_binder_eexist=1", cmdline_file=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous", result.stderr)

    def test_rust_binder_blacklist_is_rejected(self):
        result = self.execute(
            "module_blacklist=kernelsu,rust_binder "
            "pandora_rust_binder_eexist=1", cmdline_file=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rust_binder", result.stderr)

    def test_conflicting_eexist_is_rejected(self):
        result = self.execute(
            "module_blacklist=kernelsu pandora_rust_binder_eexist=0",
            cmdline_file=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Conflicting", result.stderr)

    def test_duplicate_eexist_is_rejected(self):
        result = self.execute(
            "module_blacklist=kernelsu pandora_rust_binder_eexist=1 "
            "pandora_rust_binder_eexist=1", cmdline_file=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous", result.stderr)


if __name__ == "__main__":
    unittest.main()
