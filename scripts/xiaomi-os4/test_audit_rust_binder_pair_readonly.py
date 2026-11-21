#!/usr/bin/env python3
"""Hermetic tests for the NON-FLASH Rust Binder / GKI pair check."""
import copy
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

verify = load("verify_rust_pair", "verify-rust-binder-gki-pair-readonly.py")
fixture = load("fixture_oem_provider", "test_audit_vendor_provider_graph.py")
FULL = fixture.FULL
STOCK_SHA = "bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8"


class RustPairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.symvers = Path(self.tmp.name) / "Module.symvers"
        self.symvers.write_text(
            "0x12345678\tcore_export\tvmlinux\tEXPORT_SYMBOL\n" +
            "".join(f"0x{n:08x}\ttest_export_{n}\tvmlinux\tEXPORT_SYMBOL\n"
                    for n in range(100, 201)))
        self.metadata = {
            "STOCK_BUILD": "OS4.0.6.0.XBLCNXM",
            "STOCK_INPUT_SHA256": STOCK_SHA,
            "SOURCE_GKI_TAG": "android16-6.12-2026-03_r74",
            "SOURCE_GKI_COMMIT": "a" * 40,
            "KERNEL_RELEASE": FULL,
            "FLASHABLE": "NO",
            "FASTBOOT_BOOT": "NOT_BUILT",
            "ANYKERNEL3": "NOT_BUILT",
            "LKG_PROMOTION": "FORBIDDEN",
            "SYMVERS_SHA256": hashlib.sha256(self.symvers.read_bytes()).hexdigest(),
        }
        self.stock = {
            "stock_build": "OS4.0.6.0.XBLCNXM",
            "stock_input_sha256": STOCK_SHA,
            "kernel_release": FULL,
            "gate": "BLOCKED",
            "eligible_for_fastboot_boot": False,
            "unresolved_rust_binder": 71,
            "stock_rust_binder_imports": 240,
            "ambiguous_same_crc": 24,
            "ambiguous_split_crc": 3,
            "stock_rust_binder_sha256":
                "ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c",
        }
        self.config = ("CONFIG_RUST=y\nCONFIG_MODVERSIONS=y\n"
                       "CONFIG_ANDROID_BINDER_IPC_RUST=m\n")

    def run_pair(self, imports=None, **kwargs):
        if imports is None:
            imports = {"core_export": 0x12345678}
        candidate = fixture.elf(imports=imports, release=kwargs.get("release", FULL))
        return verify.analyze(candidate, self.symvers,
                              kwargs.get("config", self.config),
                              kwargs.get("metadata", self.metadata),
                              kwargs.get("stock", self.stock))

    def test_pair_pass_never_unlocks_oem(self):
        result = self.run_pair()
        self.assertEqual(result["rust_gki_pair"], "PASS_GKI_PAIR_ONLY")
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertIs(result["eligible_for_fastboot_boot"], False)
        self.assertIs(result["flashable"], False)
        self.assertTrue(result["zsmalloc_vendor_system_separate"])
        self.assertEqual(result["stock_zsmalloc_ambiguous_same_crc"], 24)
        self.assertEqual(result["stock_zsmalloc_ambiguous_split_crc"], 3)

    def test_candidate_crc_mismatch_blocks(self):
        result = self.run_pair({"core_export": 0x99999999})
        self.assertEqual(result["rust_gki_pair"], "BLOCKED")
        self.assertEqual(result["mismatched_candidate_imports"], ["core_export"])

    def test_candidate_missing_symbol_blocks(self):
        result = self.run_pair({"not_in_gki": 0x12345678})
        self.assertEqual(result["rust_gki_pair"], "BLOCKED")
        self.assertEqual(result["unresolved_candidate_imports"], ["not_in_gki"])

    def test_stock_rust_gap_cannot_be_hidden(self):
        stock = copy.deepcopy(self.stock)
        stock["unresolved_rust_binder"] = 0
        self.assertEqual(self.run_pair(stock=stock)["rust_gki_pair"], "BLOCKED")

    def test_vendor_system_conflict_cannot_be_collapsed(self):
        stock = copy.deepcopy(self.stock)
        stock["ambiguous_split_crc"] = 0
        self.assertEqual(self.run_pair(stock=stock)["rust_gki_pair"], "BLOCKED")

    def test_candidate_must_be_modular(self):
        self.assertEqual(self.run_pair(config=self.config.replace(
            "CONFIG_ANDROID_BINDER_IPC_RUST=m",
            "CONFIG_ANDROID_BINDER_IPC_RUST=y"))["rust_gki_pair"], "BLOCKED")

    def test_changed_symvers_provenance_blocks(self):
        metadata = dict(self.metadata, SYMVERS_SHA256="0" * 64)
        self.assertEqual(self.run_pair(metadata=metadata)["rust_gki_pair"], "BLOCKED")

    def test_release_mismatch_blocks(self):
        self.assertEqual(self.run_pair(release="6.12.69-android16-6-other-4k")[
            "rust_gki_pair"], "BLOCKED")

    def test_wrong_oem_source_identity_blocks(self):
        stock = copy.deepcopy(self.stock)
        stock["stock_rust_binder_sha256"] = "0" * 64
        self.assertEqual(self.run_pair(stock=stock)["rust_gki_pair"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
