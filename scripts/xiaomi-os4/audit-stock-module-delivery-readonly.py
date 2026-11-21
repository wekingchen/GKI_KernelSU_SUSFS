#!/usr/bin/env python3
"""Read-only pandora OS4.0.6 original module-delivery provenance.

Source ZIP contains extracted OTA .ko inventory, NOT a trusted full
system_dlkm filesystem or a live module loading trace. Never grants boot
eligibility; specifically never collapses vendor and system zsmalloc.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import struct
import re
import sys
import zipfile
from pathlib import Path

_abi_spec = importlib.util.spec_from_file_location(
    "pandora_oem_abi", Path(__file__).with_name("check-ota-oem-abi.py"))
_abi = importlib.util.module_from_spec(_abi_spec)
_abi_spec.loader.exec_module(_abi)

STOCK_SHA = "bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8"
EXPECTED_SHA = {
    "system:rust_binder": "ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c",
    "vendor:zsmalloc": "350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e",
    "system:zsmalloc": "b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465",
}
ZS_CRC = {"vendor": 0x1804f5bc, "system": 0x36f39fe1}
MAGIC = b"~Module signature appended~.\n"
MAX_STOCK_ZIP = 950 * 1024 * 1024
MAX_OEM_ZIP = 600 * 1024 * 1024
MAX_MODULE_SIZE = 40 * 1024 * 1024
REQUIRED = {
    "system:rust_binder", "vendor:zsmalloc", "system:zsmalloc",
    "vendor:zram", "vendor:node_cache", "system:zram",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_of_path(path: str) -> str:
    """Source is derived from the *collected archive path*, never basename."""
    parts = path.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("unsafe or ambiguous archive member path")
    locations = set(parts) & {"vendor_dlkm", "system_dlkm", "odm_dlkm"}
    if len(locations) != 1:
        raise ValueError("unknown or ambiguous DLKM source path")
    return {"vendor_dlkm": "vendor", "system_dlkm": "system",
            "odm_dlkm": "odm"}[next(iter(locations))]


def module_fields(sections: dict[str, bytes]) -> dict[str, str]:
    result = {}
    for raw in sections.get(".modinfo", b"").split(b"\0"):
        if not raw or b"=" not in raw:
            continue
        k, v = raw.split(b"=", 1)
        key = k.decode("ascii", "strict")
        value = v.decode("utf-8", "replace")
        # parmtype/parm/alias/firmware may legitimately appear repeatedly
        # for distinct exported parameters. Treat only identity/ABI fields as
        # single-valued; never let a later record override a conflict there.
        singleton = {"vermagic", "scmversion", "depends", "signer",
                     "sig_key", "sig_hashalgo", "license", "name", "intree"}
        if key in result:
            if key in singleton and result[key] != value:
                raise ValueError("conflicting duplicate module identity field: " + key)
            continue
        result[key] = value
    return result


def gnu_build_id_note(sections: dict[str, bytes]) -> dict:
    """Identify ELF module SHT_NOTE bytes, not the loaded binary's full identity.

    Linux /sys/module/<name>/notes/.note.gnu.build-id may expose these bytes
    for an *actually loaded* module. Missing/unsupported notes are UNKNOWN.
    """
    raw = sections.get(".note.gnu.build-id", b"")
    if not raw:
        return {"status": "NOT_PRESENT", "note_sha256": None,
                "build_id_hex": None}
    if len(raw) < 16 or len(raw) > 4096:
        return {"status": "INVALID", "note_sha256": None,
                "build_id_hex": None}
    namesz, descsz, kind = struct.unpack_from("<III", raw)
    name_end = 12 + namesz
    desc_off = (name_end + 3) & ~3
    desc_end = desc_off + descsz
    if (namesz != 4 or descsz not in (16, 20, 32)
            or kind != 3 or name_end > len(raw)
            or raw[12:name_end] != bytes((71, 78, 85, 0))
            or desc_end > len(raw)):
        return {"status": "INVALID", "note_sha256": None,
                "build_id_hex": None}
    return {"status": "ELF_GNU_BUILD_ID_PRESENT", "note_sha256": sha(raw),
            "note_length": len(raw),
            "build_id_hex": raw[desc_off:desc_end].hex()}


def inspect_module(path: str, data: bytes) -> dict:
    sections = _abi.elf_sections(data)
    info = module_fields(sections)
    name = path.rsplit("/", 1)[-1]
    source = source_of_path(path)
    result = {
        "archive_path": path,
        "collected_source": source,
        "basename": name,
        "sha256": sha(data),
        "byte_count": len(data),
        "vermagic": _abi.module_vermagic(sections),
        "depends": [x for x in info.get("depends", "").split(",") if x],
        "module_license": info.get("license", "UNKNOWN"),
        "scmversion": info.get("scmversion", "NOT_RECORDED"),
        "signature_trailer_magic_present": data.endswith(MAGIC),
        "signer_modinfo": info.get("signer", "NOT_RECORDED"),
        "sig_key_modinfo": info.get("sig_key", "NOT_RECORDED"),
        "sig_hashalgo_modinfo": info.get("sig_hashalgo", "NOT_RECORDED"),
        "signing_trust_verified": False,
        "gnu_build_id_note": gnu_build_id_note(sections),
    }
    return result


def audit(stock_zip: Path, expected_sha: str = STOCK_SHA,
          expected_modules: dict[str, str] = EXPECTED_SHA,
          expected_zs_crc: dict[str, int] = ZS_CRC) -> dict:
    result = {
        "schema": 1, "device": "pandora", "build": "OS4.0.6.0.XBLCNXM",
        "flashable": False, "eligible_for_fastboot_boot": False,
        "gate": "BLOCKED", "oem_abi_gate_unchanged": True,
        "module_delivery_verified": False,
        "runtime_selected_binder_implementation": "UNKNOWN",
        "actual_loaded_rust_binder_sha256": "NOT_PROVEN",
        "actual_loaded_zsmalloc_sha256": "NOT_PROVEN",
        "system_dlkm_load_order": "NOT_PROVEN",
        "system_dlkm_avb_verified": False,
        "vendor_system_zsmalloc_interchangeable": False,
        "stock_zip_sha256": "NOT_CHECKED",
        "reason": "unverified",
    }
    try:
        if not stock_zip.is_file() or stock_zip.stat().st_size > MAX_STOCK_ZIP:
            raise ValueError("stock input ZIP missing or oversized")
        stock_bytes = stock_zip.read_bytes()
        result["stock_zip_sha256"] = sha(stock_bytes)
        if result["stock_zip_sha256"] != expected_sha:
            raise ValueError("pinned stock ZIP SHA256 mismatch")
        with zipfile.ZipFile(io.BytesIO(stock_bytes)) as outer:
            originals = [x for x in outer.infolist() if
                         not x.is_dir() and x.filename.rsplit("/", 1)[-1] == "oem-modules.zip"]
            if len(originals) != 1 or originals[0].file_size > MAX_OEM_ZIP:
                raise ValueError("missing, duplicate or oversized OEM module archive")
            inner_bytes = outer.read(originals[0])
            result["system_dlkm_partition_image_in_stock_input"] = any(
                x.filename.rsplit("/", 1)[-1] in
                ("system_dlkm.img", "system_dlkm_a.img", "system_dlkm_b.img")
                for x in outer.infolist())
        matched = {}
        total_modules = 0
        manifest_paths = []
        with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
            seen = set()
            for member in inner.infolist():
                path = member.filename.replace("\\", "/")
                if member.is_dir():
                    continue
                if path in seen:
                    raise ValueError("duplicate OEM inventory path")
                seen.add(path)
                if re.search(r"modules\.(load|dep)(?:\.recovery)?$", path):
                    manifest_paths.append(path)
                if not _abi.KO_NAME.search(path):
                    continue
                total_modules += 1
                if member.file_size > MAX_MODULE_SIZE:
                    raise ValueError("oversized OEM .ko")
                source = source_of_path(path)
                basename = path.rsplit("/", 1)[-1]
                simple = re.sub(r"\.ko(?:\.zst|\.xz|\.gz)?$", "", basename, flags=re.I)
                key = f"{source}:{simple}"
                if key not in REQUIRED:
                    continue
                if key in matched:
                    raise ValueError("duplicate source-qualified module: " + key)
                data = _abi.unpack_module(inner.read(member), path)
                inspected = inspect_module(path, data)
                imported = _abi.imported_versions(_abi.elf_sections(data))
                inspected["zs_malloc_import_crc"] = (
                    f"0x{imported['zs_malloc']:08x}" if "zs_malloc" in imported else "NOT_IMPORTED")
                if key.endswith(":zsmalloc"):
                    exports = _abi.module_export_crcs(data)
                    if "zs_malloc" not in exports:
                        raise ValueError("missing actual zs_malloc export CRC in " + key)
                    inspected["zs_malloc_export_crc"] = f"0x{exports['zs_malloc']:08x}"
                    if exports["zs_malloc"] != expected_zs_crc[source]:
                        raise ValueError("source-qualified zsmalloc provider CRC changed: " + key)
                if key in expected_modules and inspected["sha256"] != expected_modules[key]:
                    raise ValueError("pinned binary SHA mismatch for " + key)
                matched[key] = inspected
        if total_modules != 505 or set(matched) != REQUIRED:
            raise ValueError("original 505 modules or required vendor/system inventory incomplete")
        for key in ("vendor:zram", "vendor:node_cache", "system:zram"):
            source = key.split(":", 1)[0]
            if matched[key]["zs_malloc_import_crc"] != f"0x{expected_zs_crc[source]:08x}":
                raise ValueError("zram/node_cache consumes incompatible zsmalloc source: " + key)
        if matched["vendor:zsmalloc"]["sha256"] == matched["system:zsmalloc"]["sha256"]:
            raise ValueError("vendor and system zsmalloc unexpectedly identical")
        result.update(
            inventory_module_count=total_modules,
            selected_source_qualified_modules=matched,
            module_manifests_in_collected_inventory=sorted(manifest_paths),
            inventory_provenance_checked=True,
            reason=("Original source-qualified module SHAs and CRCs verified. "
                    "Neither actual runtime loading, system_dlkm image AVB chain "
                    "nor replacement module signature trust is established."),
        )
    except Exception as exc:
        result["reason"] = str(exc)[:350]
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-zip", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    report = audit(a.stock_zip)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n")
    print("MODULE_PROVENANCE=" + str(report.get("inventory_provenance_checked", False)))
    print("OEM_ABI_GATE=BLOCKED")
    print("NO_FLASH=YES")
    return 0 if report.get("inventory_provenance_checked") else 1


if __name__ == "__main__":
    sys.exit(main())
