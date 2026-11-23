#!/usr/bin/env python3
import copy
import importlib.util
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("oem_abi", BASE / "check-ota-oem-abi.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def rec(path, name, digest, note, imports=1):
    return {
        "path": path,
        "module_name": name,
        "sha256": digest,
        "note_sha256": note,
        "imported": {f"sym_{name}_{digest[0]}": 0x12345678 + imports},
        "provided": {},
    }


class RuntimeSelectedOEMGate(unittest.TestCase):
    def setUp(self):
        self.vendor_node = "a" * 64
        self.vendor_zram = "b" * 64
        self.vendor_zsmalloc = "c" * 64
        self.system_zram = "d" * 64
        self.system_zsmalloc = "e" * 64
        self.rust = "f" * 64
        self.selection = {
            "gate_scope": "EXACT_OS406_EEXIST_RUNTIME_SELECTED_MODULE_GRAPH",
            "standard_workflow": {
                "run_id": 45047763911,
                "image_sha256": "1" * 64,
            },
            "module_identity_evidence": {
                "selected_modules": {
                    "node_cache": {
                        "module_sha256": self.vendor_node,
                        "runtime_note_sha256": "2" * 64,
                    },
                    "zram": {
                        "module_sha256": self.vendor_zram,
                        "runtime_note_sha256": "3" * 64,
                    },
                    "zsmalloc": {
                        "module_sha256": self.vendor_zsmalloc,
                        "runtime_note_sha256": "4" * 64,
                    },
                }
            },
            "suppressed_modules": {
                "rust_binder": {
                    "module_sha256": self.rust,
                    "mechanism": "EXACT_EEXIST_AFTER_BLACKLIST_BEFORE_MODVERSION",
                }
            },
        }
        self.records = [
            rec("vendor_dlkm/node_cache.ko", "node_cache", self.vendor_node, "2" * 64, 73),
            rec("vendor_dlkm/zram.ko", "zram", self.vendor_zram, "3" * 64, 243),
            rec("vendor_dlkm/zsmalloc.ko", "zsmalloc", self.vendor_zsmalloc, "4" * 64, 46),
            rec("system_dlkm/zram.ko", "zram", self.system_zram, "5" * 64, 177),
            rec("system_dlkm/zsmalloc.ko", "zsmalloc", self.system_zsmalloc, "6" * 64, 53),
            rec("system_dlkm/rust_binder.ko", "rust_binder", self.rust, "7" * 64, 240),
            rec("vendor_dlkm/other.ko", "other", "8" * 64, None, 4),
        ]
        self.report = {"stock_rust_binder_sha256": self.rust}

    def test_selects_vendor_runtime_variants_and_suppresses_rust_binder(self):
        report = copy.deepcopy(self.report)
        active = abi.apply_runtime_module_selection(
            copy.deepcopy(self.records), copy.deepcopy(self.selection), report)
        paths = [x["path"] for x in active]
        self.assertIn("vendor_dlkm/node_cache.ko", paths)
        self.assertIn("vendor_dlkm/zram.ko", paths)
        self.assertIn("vendor_dlkm/zsmalloc.ko", paths)
        self.assertIn("vendor_dlkm/other.ko", paths)
        self.assertNotIn("system_dlkm/zram.ko", paths)
        self.assertNotIn("system_dlkm/zsmalloc.ko", paths)
        self.assertNotIn("system_dlkm/rust_binder.ko", paths)
        self.assertEqual(report["runtime_selection_status"], "APPLIED_FAIL_CLOSED")
        self.assertEqual(
            {x["module_name"] for x in report["runtime_inactive_duplicate_modules"]},
            {"zram", "zsmalloc"},
        )
        self.assertEqual(report["runtime_suppressed_modules"][0]["imports"], 1)
        self.assertEqual(report["runtime_suppressed_modules"][0]["module_name"], "rust_binder")

    def test_note_mismatch_fails_closed(self):
        selection = copy.deepcopy(self.selection)
        selection["module_identity_evidence"]["selected_modules"]["zsmalloc"]["runtime_note_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "GNU Note mismatch"):
            abi.apply_runtime_module_selection(copy.deepcopy(self.records), selection,
                                               copy.deepcopy(self.report))

    def test_missing_selected_binary_fails_closed(self):
        records = [x for x in copy.deepcopy(self.records)
                   if x["sha256"] != self.vendor_zram]
        with self.assertRaisesRegex(ValueError, "binary not unique: zram"):
            abi.apply_runtime_module_selection(records, copy.deepcopy(self.selection),
                                               copy.deepcopy(self.report))

    def test_rust_binder_binary_drift_fails_closed(self):
        report = {"stock_rust_binder_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "differs from stock audit"):
            abi.apply_runtime_module_selection(copy.deepcopy(self.records),
                                               copy.deepcopy(self.selection), report)

    def test_second_unattested_rust_binder_fails_closed(self):
        records = copy.deepcopy(self.records)
        records.append(rec("other/rust_binder.ko", "rust_binder", "9" * 64, None, 1))
        with self.assertRaisesRegex(ValueError, "unexpected second rust_binder|not unique"):
            abi.apply_runtime_module_selection(records, copy.deepcopy(self.selection),
                                               copy.deepcopy(self.report))

    def test_exact_same_crc_vmlinux_oem_overlap_is_accepted_only_by_identity(self):
        consumer = "system_dlkm/kernel/net/9p/9pnet.ko"
        provider = "system_dlkm/kernel/fs/netfs/netfs.ko"
        crc = 0xce8adb59
        selection = copy.deepcopy(self.selection)
        selection["equivalent_provider_overlaps"] = [{
            "consumer": consumer,
            "symbol": "netfs_write_subrequest_terminated",
            "expected_crc": "0xce8adb59",
            "vmlinux_crc": "0xce8adb59",
            "oem_provider": provider,
            "oem_provider_crc": "0xce8adb59",
            "justification": "EXACT_FEATURE_IMAGE_BOOTED_AND_ALL_PROVIDER_CRCS_MATCH",
        }]
        got = abi.resolve_runtime_equivalent_overlap(
            selection, consumer, "netfs_write_subrequest_terminated",
            crc, crc, [(provider, crc)])
        self.assertEqual(got, selection["equivalent_provider_overlaps"][0])

    def test_same_crc_overlap_with_different_provider_is_not_accepted(self):
        consumer = "system_dlkm/kernel/net/9p/9pnet.ko"
        provider = "system_dlkm/kernel/fs/netfs/netfs.ko"
        crc = 0xce8adb59
        selection = copy.deepcopy(self.selection)
        selection["equivalent_provider_overlaps"] = [{
            "consumer": consumer,
            "symbol": "netfs_write_subrequest_terminated",
            "expected_crc": "0xce8adb59",
            "vmlinux_crc": "0xce8adb59",
            "oem_provider": provider,
            "oem_provider_crc": "0xce8adb59",
            "justification": "EXACT_FEATURE_IMAGE_BOOTED_AND_ALL_PROVIDER_CRCS_MATCH",
        }]
        got = abi.resolve_runtime_equivalent_overlap(
            selection, consumer, "netfs_write_subrequest_terminated",
            crc, crc, [("different/netfs.ko", crc)])
        self.assertIsNone(got)

    def test_same_identity_overlap_with_crc_drift_is_not_accepted(self):
        consumer = "system_dlkm/kernel/net/9p/9pnet.ko"
        provider = "system_dlkm/kernel/fs/netfs/netfs.ko"
        crc = 0xce8adb59
        selection = copy.deepcopy(self.selection)
        selection["equivalent_provider_overlaps"] = [{
            "consumer": consumer,
            "symbol": "netfs_write_subrequest_terminated",
            "expected_crc": "0xce8adb59",
            "vmlinux_crc": "0xce8adb59",
            "oem_provider": provider,
            "oem_provider_crc": "0xce8adb59",
            "justification": "EXACT_FEATURE_IMAGE_BOOTED_AND_ALL_PROVIDER_CRCS_MATCH",
        }]
        self.assertIsNone(abi.resolve_runtime_equivalent_overlap(
            selection, consumer, "netfs_write_subrequest_terminated",
            crc, crc ^ 1, [(provider, crc)]))


if __name__ == "__main__":
    unittest.main()
