#!/usr/bin/env python3
import importlib.util, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("shim",BASE/"apply-pandora-rust-binder-eexist-shim.py")
shim=importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)

SAMPLE=r'''static char *module_blacklist;
core_param(module_blacklist, module_blacklist, charp, 0400);

/* Module within temporary copy, this doesn't do any allocation */
static int early_mod_check(struct load_info *info, int flags)
{
	int err;

	/*
	 * Now that we know we have the correct module name, check
	 * if it's blacklisted.
	 */
	if (blacklisted(info->name)) {
		pr_err("Module %s is blacklisted\n", info->name);
		return -EPERM;
	}

	err = rewrite_section_headers(info, flags);
	if (err)
		return err;

	if (!check_modstruct_version(info, info->mod))
		return -ENOEXEC;

	err = check_modinfo(info->mod, info, flags);
	if (err)
		return err;
	return 0;
}
'''

class Shim(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name); (self.root/"kernel/module").mkdir(parents=True)
        (self.root/"kernel/module/main.c").write_text(SAMPLE)

    @patch("subprocess.check_output",return_value=shim.COMMIT+"\n")
    def test_exact_patch_is_opt_in_and_before_modversion_work(self,_):
        shim.patch(self.root)
        text=(self.root/"kernel/module/main.c").read_text()
        self.assertIn("core_param(pandora_rust_binder_eexist",text)
        self.assertIn('!strcmp(info->name, "rust_binder")',text)
        self.assertIn("return -EEXIST;",text)
        self.assertLess(text.index("if (blacklisted(info->name))"),
                        text.index("pandora_rust_binder_eexist &&"))
        self.assertLess(text.index("pandora_rust_binder_eexist &&"),
                        text.index("rewrite_section_headers(info, flags)"))
        self.assertLess(text.index("pandora_rust_binder_eexist &&"),
                        text.index("check_modinfo(info->mod, info, flags)"))
        self.assertNotIn("module_blacklist=rust_binder",text)

    @patch("subprocess.check_output",return_value="0"*40+"\n")
    def test_wrong_source_commit_fails_closed(self,_):
        with self.assertRaises(SystemExit):
            shim.patch(self.root)

    @patch("subprocess.check_output",return_value=shim.COMMIT+"\n")
    def test_anchor_drift_fails_closed(self,_):
        p=self.root/"kernel/module/main.c"
        p.write_text(SAMPLE.replace("return -EPERM;","return -EINVAL;"))
        with self.assertRaises(SystemExit):
            shim.patch(self.root)

if __name__=="__main__":
    unittest.main()
