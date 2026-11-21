#!/usr/bin/env python3
"""Hermetic source-qualified stock module delivery tests; no device access."""
import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, BASE / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


audit = load("module_delivery", "audit-stock-module-delivery-readonly.py")
fixture = load("oem_fixture", "test_audit_vendor_provider_graph.py")


class ModuleDelivery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "stock.zip"
        self.modules = {
            "system_dlkm/lib/modules/rust_binder.ko":
                fixture.elf(imports={"core_export": 0x12345678}),
            "vendor_dlkm/lib/modules/zsmalloc.ko":
                fixture.elf(exports={"zs_malloc": 0x1804f5bc}),
            "system_dlkm/lib/modules/zsmalloc.ko":
                fixture.elf(exports={"zs_malloc": 0x36f39fe1}),
            "vendor_dlkm/lib/modules/zram.ko":
                fixture.elf(imports={"zs_malloc": 0x1804f5bc}),
            "vendor_dlkm/lib/modules/node_cache.ko":
                fixture.elf(imports={"zs_malloc": 0x1804f5bc}),
            "system_dlkm/lib/modules/zram.ko":
                fixture.elf(imports={"zs_malloc": 0x36f39fe1}),
        }
        for i in range(499):
            self.modules[f"vendor_dlkm/lib/modules/filler_{i:03d}.ko"] = (
                fixture.elf(imports={"core_export": 0x12345678}))
        self.expected = {
            "system:rust_binder": audit.sha(
                self.modules["system_dlkm/lib/modules/rust_binder.ko"]),
            "vendor:zsmalloc": audit.sha(
                self.modules["vendor_dlkm/lib/modules/zsmalloc.ko"]),
            "system:zsmalloc": audit.sha(
                self.modules["system_dlkm/lib/modules/zsmalloc.ko"]),
        }

    def run_audit(self, modules=None, expected=None):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in (modules or self.modules).items():
                z.writestr(name, data)
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("oem-modules.zip", mem.getvalue())
        return audit.audit(self.path, expected_sha=audit.sha(self.path.read_bytes()),
                           expected_modules=expected or self.expected)

    def test_success_is_evidence_only_and_never_flashable(self):
        result = self.run_audit()
        self.assertTrue(result["inventory_provenance_checked"], result["reason"])
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertFalse(result["flashable"])
        self.assertFalse(result["module_delivery_verified"])
        self.assertFalse(result["vendor_system_zsmalloc_interchangeable"])
        self.assertEqual(result["actual_loaded_zsmalloc_sha256"], "NOT_PROVEN")
        self.assertEqual(result["inventory_module_count"], 505)
        scoped = result["selected_source_qualified_modules"]
        self.assertNotEqual(scoped["vendor:zsmalloc"]["sha256"],
                            scoped["system:zsmalloc"]["sha256"])
        self.assertEqual(scoped["vendor:zsmalloc"]["zs_malloc_export_crc"],
                         "0x1804f5bc")
        self.assertEqual(scoped["system:zsmalloc"]["zs_malloc_export_crc"],
                         "0x36f39fe1")
        self.assertFalse(scoped["system:rust_binder"]["signing_trust_verified"])

    def test_reject_bad_origin(self):
        for name in ("unknown/rust_binder.ko", "system_dlkm/../rust_binder.ko",
                     "vendor_dlkm/system_dlkm/rust_binder.ko"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.source_of_path(name)

    def test_fail_closed_on_swapped_system_zram(self):
        changed = dict(self.modules)
        changed["system_dlkm/lib/modules/zram.ko"] = (
            fixture.elf(imports={"zs_malloc": 0x1804f5bc}))
        result = self.run_audit(modules=changed)
        self.assertFalse(result.get("inventory_provenance_checked"))
        self.assertIn("incompatible zsmalloc", result["reason"])
        self.assertEqual(result["gate"], "BLOCKED")

    def test_fail_closed_on_missing_vendor_node_cache(self):
        changed = dict(self.modules)
        del changed["vendor_dlkm/lib/modules/node_cache.ko"]
        result = self.run_audit(modules=changed)
        self.assertFalse(result.get("inventory_provenance_checked"))
        self.assertEqual(result["gate"], "BLOCKED")

    def test_fail_closed_on_wrong_exact_binder_hash(self):
        fake = dict(self.expected, **{"system:rust_binder": "f" * 64})
        result = self.run_audit(expected=fake)
        self.assertFalse(result.get("inventory_provenance_checked"))
        self.assertIn("SHA mismatch", result["reason"])
        self.assertEqual(result["gate"], "BLOCKED")

    def test_repeated_parmtype_allowed_but_conflicting_identity_fails(self):
        sections={".modinfo": (b"parmtype=param_a:int\0parmtype=param_b:bool\0"
                              b"vermagic=6.12.69-android16-6-4k\0")}
        fields=audit.module_fields(sections)
        self.assertEqual(fields["parmtype"], "param_a:int")
        sections[".modinfo"] += b"vermagic=6.12.68-android16-6-4k\0"
        with self.assertRaisesRegex(ValueError, "identity"):
            audit.module_fields(sections)

    def test_build_id_note_parser_valid_and_unavailable(self):
        import struct
        raw = struct.pack("<III", 4, 20, 3) + bytes((71, 78, 85, 0)) + bytes(range(20))
        result = audit.gnu_build_id_note({".note.gnu.build-id": raw})
        self.assertEqual(result["status"], "ELF_GNU_BUILD_ID_PRESENT")
        self.assertEqual(result["note_sha256"], audit.sha(raw))
        self.assertEqual(result["build_id_hex"], bytes(range(20)).hex())
        self.assertEqual(audit.gnu_build_id_note({})["status"], "NOT_PRESENT")

    def test_build_id_note_malformed_cannot_be_claimed_as_match(self):
        import struct
        raw = struct.pack("<III", 4, 20, 3) + b"EVIL" + bytes(range(20))
        result = audit.gnu_build_id_note({".note.gnu.build-id": raw})
        self.assertEqual(result["status"], "INVALID")
        self.assertIsNone(result["note_sha256"])

    def test_modinfo_and_signature_marker_not_trust_verification(self):
        binary = fixture.elf(imports={"core_export": 0x12345678})
        mod = audit.inspect_module("system_dlkm/lib/modules/rust_binder.ko", binary)
        self.assertEqual(mod["collected_source"], "system")
        self.assertFalse(mod["signature_trailer_magic_present"])
        self.assertFalse(mod["signing_trust_verified"])
        self.assertEqual(mod["signer_modinfo"], "NOT_RECORDED")


if __name__ == "__main__":
    unittest.main()
