#!/usr/bin/env python3
import copy, importlib.util, json, tempfile, unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("shadow",BASE/"assess-runtime-selected-testboot.py")
shadow=importlib.util.module_from_spec(spec); spec.loader.exec_module(shadow)
RUNTIME=json.loads((BASE.parent.parent/".github/config/pandora-os4-406-runtime-selection.json").read_text())

def abi_fixture():
    c=RUNTIME["shadow_blocker_contract"]
    rust=c["rust_binder_path"]
    # Unit fixture preserves exact counts/hash through synthetic strings only by
    # loading a real captured summary in CI; focused negative tests here exercise
    # fail-closed branches with a minimal valid-by-construction object.
    return None

class ShadowGate(unittest.TestCase):
    def setUp(self):
        self.runtime=copy.deepcopy(RUNTIME)

    def valid_from_contract(self):
        # Reconstruct exact immutable lists from constants committed below.
        unresolved=json.loads((BASE/"fixtures-pandora-406-rust-binder-unresolved.json").read_text())
        ambiguous=json.loads((BASE/"fixtures-pandora-406-zsmalloc-ambiguities.json").read_text())
        c=self.runtime["shadow_blocker_contract"]
        return {
            "gate":"BLOCKED",
            "stock_build":self.runtime["stock_build"],
            "stock_input_sha256":self.runtime["stock_input_sha256"],
            "kernel_release":self.runtime["stock_uname"],
            "candidate_commit":self.runtime["candidate_gki_commit"],
            "failed_modules":[],
            "crc_mismatches":[],
            "unresolved_kernel_imports":unresolved,
            "unresolved_rust_binder":71,
            "unresolved_rust_mangled":71,
            "ambiguous_providers":[x["key"] for x in ambiguous],
            "ambiguous_same_crc":24,
            "ambiguous_split_crc":3,
            "ambiguous_provider_details":[x["detail"] for x in ambiguous],
        }

    def test_exact_contract_passes_only_experimental_gate(self):
        r=shadow.assess(self.valid_from_contract(),self.runtime)
        self.assertTrue(r["eligible_for_fastboot_boot_experiment"])
        self.assertEqual(r["experimental_gate"],"RUNTIME_SELECTED_EEXIST_SHIM_TEST_ELIGIBLE")
        self.assertEqual(r["formal_oem_gate"],"BLOCKED")
        self.assertFalse(r["flashable"])
        self.assertFalse(r["eligible_for_persistent_flash"])
        self.assertFalse(r["lkg_promotion"])

    def test_any_extra_unresolved_symbol_blocks(self):
        a=self.valid_from_contract()
        a["unresolved_kernel_imports"].append("evil.ko:not_rust")
        r=shadow.assess(a,self.runtime)
        self.assertFalse(r["eligible_for_fastboot_boot_experiment"])

    def test_any_crc_mismatch_blocks(self):
        a=self.valid_from_contract(); a["crc_mismatches"]=["x:y"]
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

    def test_runtime_binder_must_be_c(self):
        rt=copy.deepcopy(self.runtime); rt["runtime_selection"]["binder_requested_impl"]="rust"
        self.assertFalse(shadow.assess(self.valid_from_contract(),rt)["eligible_for_fastboot_boot_experiment"])

    def test_vendor_zsmalloc_selection_must_not_drift(self):
        rt=copy.deepcopy(self.runtime); rt["runtime_selection"]["zsmalloc_source"]="system"
        self.assertFalse(shadow.assess(self.valid_from_contract(),rt)["eligible_for_fastboot_boot_experiment"])

    def test_formal_gate_must_stay_blocked(self):
        a=self.valid_from_contract(); a["gate"]="CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

if __name__=="__main__":
    unittest.main()
