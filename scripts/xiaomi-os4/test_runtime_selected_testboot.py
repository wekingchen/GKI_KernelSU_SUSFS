#!/usr/bin/env python3
import copy, importlib.util, json, unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("shadow",BASE/"assess-runtime-selected-testboot.py")
shadow=importlib.util.module_from_spec(spec); spec.loader.exec_module(shadow)
RUNTIME=json.loads((BASE.parent.parent/".github/config/pandora-os4-406-runtime-selection.json").read_text())

class ShadowGate(unittest.TestCase):
    def setUp(self):
        self.runtime=copy.deepcopy(RUNTIME)
        c=self.runtime["shadow_blocker_contract"]
        rust=c["rust_binder_path"]
        self.unresolved=[rust+":_Rexample1",rust+":_Rexample2"]
        vp=c["zsmalloc_providers"][0]; sp=c["zsmalloc_providers"][1]
        consumer=c["zsmalloc_consumers"][0]
        self.details=[{
            "consumer":consumer,"symbol":"zs_malloc","expected_crc":"0x1804f5bc",
            "provider_crc_variants":2,
            "providers":[
                {"module":vp,"actual_crc":"0x1804f5bc","crc_matches":True},
                {"module":sp,"actual_crc":"0x36f39fe1","crc_matches":False},
            ],
        }]
        self.ambiguous=[consumer+":zs_malloc:multiple-OEM-providers"]
        c.update(
            unresolved_kernel_imports=len(self.unresolved),
            unresolved_rust_binder=len(self.unresolved),
            unresolved_rust_mangled=len(self.unresolved),
            unresolved_sorted_sha256=shadow.digest(self.unresolved),
            ambiguous_providers=len(self.ambiguous),
            ambiguous_same_crc=0,
            ambiguous_split_crc=1,
            ambiguous_sorted_sha256=shadow.digest(self.ambiguous),
        )

    def valid(self):
        c=self.runtime["shadow_blocker_contract"]
        return {
            "gate":"BLOCKED",
            "stock_build":self.runtime["stock_build"],
            "stock_input_sha256":self.runtime["stock_input_sha256"],
            "kernel_release":self.runtime["stock_uname"],
            "candidate_commit":self.runtime["candidate_gki_commit"],
            "failed_modules":[],
            "crc_mismatches":[],
            "unresolved_kernel_imports":list(self.unresolved),
            "unresolved_rust_binder":len(self.unresolved),
            "unresolved_rust_mangled":len(self.unresolved),
            "ambiguous_providers":list(self.ambiguous),
            "ambiguous_same_crc":0,
            "ambiguous_split_crc":1,
            "ambiguous_provider_details":copy.deepcopy(self.details),
        }

    def test_exact_contract_passes_only_experimental_gate(self):
        r=shadow.assess(self.valid(),self.runtime)
        self.assertTrue(r["eligible_for_fastboot_boot_experiment"])
        self.assertEqual(r["formal_oem_gate"],"BLOCKED")
        self.assertFalse(r["flashable"])
        self.assertFalse(r["eligible_for_persistent_flash"])
        self.assertFalse(r["lkg_promotion"])

    def test_any_extra_unresolved_symbol_blocks(self):
        a=self.valid(); a["unresolved_kernel_imports"].append("evil.ko:not_rust")
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

    def test_any_crc_mismatch_blocks(self):
        a=self.valid(); a["crc_mismatches"]=["x:y"]
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

    def test_runtime_binder_must_be_c(self):
        rt=copy.deepcopy(self.runtime); rt["runtime_selection"]["binder_requested_impl"]="rust"
        self.assertFalse(shadow.assess(self.valid(),rt)["eligible_for_fastboot_boot_experiment"])

    def test_vendor_zsmalloc_selection_must_not_drift(self):
        rt=copy.deepcopy(self.runtime); rt["runtime_selection"]["zsmalloc_source"]="system"
        self.assertFalse(shadow.assess(self.valid(),rt)["eligible_for_fastboot_boot_experiment"])

    def test_provider_set_must_not_drift(self):
        a=self.valid(); a["ambiguous_provider_details"][0]["providers"][1]["module"]="evil.ko"
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

    def test_formal_gate_must_stay_blocked(self):
        a=self.valid(); a["gate"]="CRC_AND_VERMAGIC_MATCH_CANDIDATE"
        self.assertFalse(shadow.assess(a,self.runtime)["eligible_for_fastboot_boot_experiment"])

if __name__=="__main__":
    unittest.main()
