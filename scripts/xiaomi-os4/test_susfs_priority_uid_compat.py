#!/usr/bin/env python3
"""SUSFS priority UID helper guard regression; no full kernel build required."""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("susfs-priority-uid-compat.py")
spec = importlib.util.spec_from_file_location("susfs_priority_uid_compat", MODULE)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


def example(optional=True):
    helpers = """/* Switches to the KSU domain and later uses susfs_restore_creds(). */
static struct cred *susfs_switch_to_ksu_domain(void) {
    return 0;
}

/* Restores creds saved by susfs_switch_to_ksu_domain(). */
static void susfs_restore_creds(struct cred *orig_cred) {
    commit_creds(orig_cred);
}

/* sus_path */
"""
    calls = """void set_filter(void) {
    orig_cred = susfs_switch_to_ksu_domain();
    susfs_restore_creds(orig_cred);
}
void recalc_filter(void) {
    orig_cred = susfs_switch_to_ksu_domain();
    susfs_restore_creds(orig_cred);
}
"""
    if optional:
        return helpers + f"""#ifdef {compat.SYMBOL}
{calls}#endif // #ifdef {compat.SYMBOL}
#ifdef {compat.SYMBOL}
void list_filter(void) {{}}
#endif // #ifdef {compat.SYMBOL}
"""
    return helpers + calls


class PriorityUidFilterCompatibilityTests(unittest.TestCase):
    def test_new_optional_filter_guards_only_its_private_cred_helpers(self):
        source = example()
        result, status = compat.transform(source)
        self.assertEqual(status, "WRAPPED_OPTIONAL_PRIORITY_UID_HELPERS")
        self.assertIn(compat.IFDEF + "\n" + compat.HELPER_SWITCH, result)
        self.assertIn(compat.ENDIF + "\n\n/* sus_path */", result)
        self.assertIn(source[source.index("/* sus_path */"):], result)
        self.assertEqual(result.count("orig_cred = susfs_switch_to_ksu_domain();"), 2)
        self.assertEqual(result.count("susfs_restore_creds(orig_cred);"), 2)

    def test_old_unconditional_filter_is_unchanged(self):
        source = example(optional=False)
        result, status = compat.transform(source)
        self.assertEqual(source, result)
        self.assertEqual(status, "UNCHANGED_OLD_LAYOUT")

    def test_second_application_is_idempotent(self):
        once, _ = compat.transform(example())
        twice, status = compat.transform(once)
        self.assertEqual(status, "ALREADY_GUARDED")
        self.assertEqual(once, twice)

    def test_upstream_callgraph_drift_is_rejected(self):
        drift = example().replace("    susfs_restore_creds(orig_cred);\n", "", 1)
        with self.assertRaises(compat.CompatibilityError):
            compat.transform(drift)

    def test_unconditional_call_outside_filter_is_rejected(self):
        drift = example().replace("/* sus_path */", "/* sus_path */\norig_cred = susfs_switch_to_ksu_domain();")
        with self.assertRaises(compat.CompatibilityError):
            compat.transform(drift)

    def test_conflicting_partial_guard_is_rejected(self):
        drift = example().replace("/* sus_path */", compat.ENDIF + "\n\n/* sus_path */")
        with self.assertRaises(compat.CompatibilityError):
            compat.transform(drift)


if __name__ == "__main__":
    unittest.main()
