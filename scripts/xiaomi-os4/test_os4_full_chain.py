#!/usr/bin/env python3
"""Real script-to-script synthetic OS4 pipeline; no hardware, network or flashing.

Each stage consumes files actually emitted by the previous stage, including:
stock xm.zip -> inspect -> OEM ELF/CRC -> boot v4 -> user-attributed
fixture -> development pointer -> source prepare -> feature ABI -> experimental
package -> source capture -> rebuild comparison -> LKG generation -> Release.
The "user report" and "compiler" are synthetic, NEVER device validation.
"""
from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

DIR = Path(__file__).resolve().parent
FIXED_BUILD = "OS4.0.6.0.XBLCNXM"
FIXED_UNAME = "6.12.80-android16-6-integration-4k"
RUN_ID = "872001"
RUN_HEAD = "b" * 40
GKI = "c" * 40
BASE = ("sym_%d" % i for i in range(160))
CRC = {k: i + 500 for i, k in enumerate(BASE)}


def digest(b):
    return hashlib.sha256(b).hexdigest()


def read_module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), DIR / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CROSS = read_module("cross-ota-lkg.py")
VERIFY_RELEASE = read_module("verify-ota-lkg-release.py")


def fake_elf(vermagic, symbol="sym_1", crc=501):
    """ELF64/AArch64 with real section table, .modinfo and basic modversions."""
    shstr = b"\0.shstrtab\0.modinfo\0__versions\0"
    info = b"vermagic=" + vermagic.encode() + b" SMP mod_unload\0"
    versions = struct.pack("<I", crc) + b"\0" * 4 + symbol.encode().ljust(56, b"\0")
    payload = [shstr, info, versions]
    offsets = []
    data = bytearray(b"\0" * 64)
    for body in payload:
        offsets.append(len(data))
        data.extend(body)
    while len(data) % 8:
        data.append(0)
    shoff = len(data)
    names = [0, shstr.index(b".shstrtab"), shstr.index(b".modinfo"),
             shstr.index(b"__versions")]
    shdr = struct.Struct("<IIQQQQIIQQ")
    data.extend(shdr.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    for i, body in enumerate(payload):
        data.extend(shdr.pack(names[i + 1], 3 if i == 0 else 1, 0, 0,
                              offsets[i], len(body), 0, 0, 1, 0))
    ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    hdr = struct.Struct("<16sHHIQQQIHHHHHH")
    hdr.pack_into(data, 0, ident, 1, 183, 1, 0, 0, shoff, 0, 64, 0, 0, 64, 4, 1)
    return bytes(data)


class OS4FullChain(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.stock = self.root / "xm.zip"
        self.stock_report = self.root / "stock.json"
        self.stock_config = self.root / "stock-config.env"
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.versioned = self.root / ".github/config/ota-verified" / FIXED_BUILD
        self.versioned.mkdir(parents=True)
        self.pointer = self.root / ".github/config/ota-development-current.json"
        self.features = self.root / "features"
        self.features.mkdir()
        self.rebuild = self.root / "rebuild"
        self.rebuild.mkdir()
        self.image = b"Linux version " + FIXED_UNAME.encode() + b"\0" + b"X" * 19000
        self.symvers = "".join(f"0x{v:08x}\t{k}\tvmlinux\tEXPORT_SYMBOL\n"
                               for k, v in CRC.items()).encode()
        self.gki_report = self.root / "gki-candidate.json"
        self.oem = self.root / "oem-report.json"
        self.gki_metadata = self.root / "gki-metadata.txt"
        self.base_image = self.candidate / "Image"
        self.baseline_symvers = self.candidate / "Module.symvers"
        self.base_image.write_bytes(self.image)
        self.baseline_symvers.write_bytes(self.symvers)
        (self.candidate / "final.config").write_text("CONFIG_MODVERSIONS=y\n")
        header = bytearray(4096)
        header[:8] = b"ANDROID!"
        struct.pack_into("<I", header, 8, len(self.image))
        struct.pack_into("<I", header, 12, 0)
        struct.pack_into("<I", header, 20, 1584)
        struct.pack_into("<I", header, 40, 4)
        self.boot = bytes(header) + self.image
        self.boot += b"\0" * (65536 - len(self.boot))
        self.stock_config.write_text("OS4_STOCK_INPUT_BUILD=OS4.0.5.0.XBLCNXM\n"
                                     "OS4_STOCK_BOOT_SHA256=" + "0" * 64 + "\n")
        self.ref = dict()
        for i, name in enumerate(CROSS.COMPONENTS):
            kind = "branch" if name in ("BAKASU", "SUSFS", "NTSYNC") else "tag"
            self.ref[name] = dict(kind=kind, ref="main" if kind == "branch" else "v2.0.0",
                                  commit=format(i+10, "040x"))
        self.feature_meta = None

    def run_py(self, script, *args, ok=True):
        res = subprocess.run([sys.executable, str(DIR / script), *map(str, args)],
                             cwd=self.root, text=True, capture_output=True)
        if ok:
            self.assertEqual(res.returncode, 0, res.stderr + "\n" + res.stdout)
        else:
            self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def stock_zip(self, vermagic=FIXED_UNAME, symbol="sym_1", crc=501,
                  module_count=1, omit_modules=False, uname=FIXED_UNAME):
        modules = io.BytesIO()
        with zipfile.ZipFile(modules, "w") as z:
            z.writestr("vendor_dlkm/rust_binder.ko", fake_elf(vermagic, symbol, crc))
        with zipfile.ZipFile(self.stock, "w") as z:
            z.writestr("boot.img", self.boot)
            z.writestr("init_boot.img", b"init")
            z.writestr("vendor_boot.img", b"vendor")
            z.writestr("dtbo.img", b"dtbo")
            z.writestr("README.txt",
                       f"device=pandora\nbuild={FIXED_BUILD}\nslot=_a\nuname={uname}\n")
            if not omit_modules:
                z.writestr("oem-modules.zip", modules.getvalue())
                z.writestr("oem-modules-count.txt", f"MODULE_COUNT={module_count}\n")

    def intake(self):
        self.run_py("inspect-ota-stock-input.py", "--zip", self.stock,
                    "--stock-config", self.stock_config,
                    "--github-asset-id", "3711", "--output", self.stock_report)
        stock = json.loads(self.stock_report.read_text())
        self.assertEqual(stock["status"], "NEW_OTA_CANDIDATE")
        self.assertTrue(stock["kernel_marker_verified"])
        self.assertFalse(stock["safe_to_flash"])
        self.gki_report.write_text(json.dumps({
            "ota_source_id": stock["ota_source_id"],
            "candidate_commit": GKI}))
        self.gki_metadata.write_text(
            "STOCK_INPUT_SHA256=" + stock["ota_source_id"] + "\n"
            "SOURCE_GKI_COMMIT=" + GKI + "\nSTOCK_KMI=android16-6\n"
            "STOCK_BUILD=" + FIXED_BUILD + "\nKERNEL_RELEASE=" + FIXED_UNAME + "\n"
            "IMAGE_SHA256=" + digest(self.image) + "\n"
            "SYMVERS_SHA256=" + digest(self.symvers) + "\n")
        return stock

    def oem_gate(self):
        self.run_py("check-ota-oem-abi.py",
                    "--stock-zip", self.stock, "--stock-report", self.stock_report,
                    "--candidate-report", self.gki_report,
                    "--metadata", self.gki_metadata,
                    "--symvers", self.baseline_symvers,
                    "--output", self.oem)
        return json.loads(self.oem.read_text())

    def boot_confirm(self):
        stock = json.loads(self.stock_report.read_text())
        abi = self.oem_gate()
        self.assertEqual(abi["gate"], "CRC_AND_VERMAGIC_MATCH_CANDIDATE")
        self.assertTrue(abi["eligible_for_fastboot_boot"])
        testboot = self.root / "gki-boot.img"
        self.run_py("package-ota-testboot-v4.py", "--stock-zip", self.stock,
                    "--stock-report", self.stock_report, "--abi-report", self.oem,
                    "--metadata", self.gki_metadata, "--candidate-image", self.base_image,
                    "--output", testboot)
        # This is simulated human attestation; never a real boot claim.
        self.run_py("finalize-ota-baseline.py",
                    "--stock-zip", self.stock, "--stock-report", self.stock_report,
                    "--gki-candidate", self.gki_report, "--abi-report", self.oem,
                    "--metadata", self.gki_metadata, "--image", self.base_image,
                    "--symvers", self.baseline_symvers, "--testboot", testboot,
                    "--output-dir", self.versioned, "--source-run-id", "872000",
                    "--source-head-sha", RUN_HEAD, "--asset-id", "3711",
                    "--tested-sha256", digest(testboot.read_bytes()),
                    "--observed-uname", FIXED_UNAME, "--observed-build", FIXED_BUILD,
                    "--actor", "SIMULATED-NOT-REAL-DEVICE", "--verification-run-id", "872003",
                    "--verified-at", "2026-11-01T00:00:00Z")
        record = json.loads((self.versioned / "verification.json").read_text())
        self.assertEqual(record["status"], "HUMAN_ATTESTED_BASELINE_BOOTED")
        # Everything is synthetic: this status is for exercising business logic.
        self.assertFalse(record["full_parity_lkg_promoted"])
        return record

    def route(self):
        from_rec = Path(".github/config/ota-verified") / FIXED_BUILD
        self.run_py("ota-development-pointer.py", "create",
                    "--record", from_rec / "verification.json",
                    "--fixture", from_rec / "fixture.json",
                    "--output", self.pointer)
        out = self.root / "selection.txt"
        self.run_py("ota-development-pointer.py", "select",
                    "--stock-report", self.stock_report,
                    "--root", self.root, "--pointer", self.pointer, "--output", out)
        self.assertEqual(out.read_text(), f"mode=ota\nbuild={FIXED_BUILD}\n")
        (self.candidate / "locked-candidate.env").write_text(
            "OTA_GKI_TAG=android16-6.12-2026-06_r8\n"
            "OTA_GKI_COMMIT=" + GKI + "\n"
            "OTA_KERNEL_VERSION=6.12.80\nOTA_KMI=android16-6\n"
            "OTA_BUILD=" + FIXED_BUILD + "\n"
            "OTA_INPUT_SHA256=" + json.loads(self.stock_report.read_text())["ota_source_id"] + "\n")
        (self.candidate / "build-metadata.txt").write_text(
            "SOURCE_GKI_TAG=android16-6.12-2026-06_r8\nSOURCE_GKI_COMMIT=" + GKI + "\n"
            "KERNEL_RELEASE=" + FIXED_UNAME + "\nIMAGE_SHA256=" + digest(self.image) + "\n"
            "SYMVERS_SHA256=" + digest(self.symvers) + "\n")
        shutil.copy2(self.gki_report, self.candidate / "gki-candidate.json")
        shutil.copy2(self.stock_report, self.candidate / "stock-report.json")
        self.run_py("ota-development-pointer.py", "prepare",
                    "--root", self.root, "--stock-report", self.stock_report,
                    "--pointer", self.pointer, "--candidate-dir", self.candidate,
                    "--output", self.root / "prepared.env")
        self.assertIn("OS4_GKI_COMMON_COMMIT=" + GKI,
                      (self.root / "prepared.env").read_text())

    def feature(self):
        shutil.copy2(self.base_image, self.features / "Image")
        shutil.copy2(self.baseline_symvers, self.features / "Module.symvers")
        (self.features / "final.config").write_text("CONFIG_MODVERSIONS=y\n")
        self.feature_meta = {
            "BUILD_KIND": "OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED",
            "NEW_OTA_MODE": "1", "SYSTEM_BUILD": FIXED_BUILD, "STOCK_RELEASE": FIXED_UNAME,
            "KERNEL_RELEASE": FIXED_UNAME, "SOURCE_COMMIT": GKI,
            "SELECTABLE_BUILD": "1", "FLASHABLE": "NO",
            "IMAGE_SHA256": digest(self.image), "SYMVERS_SHA256": digest(self.symvers),
            "ROOT_MODE": "bakasu-susfs", "SUSFS_EXTRA_FEATURES": "1",
            "USE_NOMOUNT": "1", "DROIDSPACES_ENABLED": "1",
            "USE_NTSYNC": "1", "USE_BBG": "1", "USE_REKERNEL": "1",
            "USE_NETWORKING": "1", "USE_CVE": "1",
            "KBUILD_BUILD_TIMESTAMP": "Sun Nov 01 00:00:00 UTC 2026",
            "UPSTREAM_CHANGED_COMPONENTS": "BAKASU,SUSFS",
        }
        pins = {}
        for name, obj in self.ref.items():
            pins["RESOLVED_" + name + "_COMMIT"] = obj["commit"]
            pins["RESOLVED_" + name + "_KIND"] = obj["kind"]
            pins["RESOLVED_" + name + "_REF"] = obj["ref"]
            self.feature_meta[name + "_REF_KIND"] = obj["kind"]
            self.feature_meta[name + "_REF"] = obj["ref"]
            self.feature_meta[name + "_COMMIT"] = obj["commit"]
        self.write_feature_metadata()
        (self.features / "locked-upstreams.env").write_text(
            "".join(f"{k}={v}\n" for k, v in pins.items()))
        shutil.copy2(self.versioned / "verification.json", self.features / "verified-baseline.json")
        shutil.copy2(self.versioned / "fixture.json", self.features / "fixture.json")
        return self.check_feature_abi()

    def write_feature_metadata(self):
        (self.features / "build-metadata.txt").write_text(
            "".join(f"{k}={v}\n" for k, v in self.feature_meta.items()))

    def check_feature_abi(self, *, ok=True):
        report = self.features / "ota-custom-abi-report.json"
        return self.run_py("check-ota-feature-abi.py",
                           "--baseline-symvers", self.baseline_symvers,
                           "--feature-symvers", self.features / "Module.symvers",
                           "--baseline-record", self.versioned / "verification.json",
                           "--feature-metadata", self.features / "build-metadata.txt",
                           "--report", report, ok=ok)

    def finish_artifacts(self):
        self.run_py("check-ota-anykernel-evidence.py",
                    "--record", self.features / "verified-baseline.json",
                    "--fixture", self.features / "fixture.json",
                    "--abi", self.features / "ota-custom-abi-report.json",
                    "--metadata", self.features / "build-metadata.txt",
                    "--image", self.features / "Image",
                    "--build", FIXED_BUILD, "--release", FIXED_UNAME)
        img = self.features / f"pandora-{FIXED_BUILD}-CUSTOM-run-{RUN_ID}-UNVERIFIED-FASTBOOT-BOOT-ONLY.img"
        self.run_py("repack-fastboot-boot-v4-from-fixture.py",
                    self.features / "fixture.json", self.features / "Image", img,
                    "--expected-image-sha256", digest(self.image),
                    "--expected-release", FIXED_UNAME, "--expected-build", FIXED_BUILD)
        zname = f"Xiaomi17Pro-pandora-{FIXED_BUILD}-CUSTOM-run-{RUN_ID}-UNVERIFIED-AnyKernel3.zip"
        self.zip = self.features / zname
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("Image", self.image)
            z.writestr("anykernel.sh", "ui_print experimental")
        (self.features / "image-reproducibility.env").write_text(
            f"IMAGE_SIZE={len(self.image)}\nIMAGE_SHA256={digest(self.image)}\n"
            f"NORMALIZED_IMAGE_SHA256={digest(self.image)}\n")
        self.run_py("cross-ota-lkg.py", "capture", "--artifact-dir", self.features,
                    "--run-id", RUN_ID, "--head-sha", RUN_HEAD)
        self.run_py("cross-ota-lkg.py", "verify", "--artifact-dir", self.features,
                    "--run-id", RUN_ID, "--head-sha", RUN_HEAD)
        return json.loads((self.features / "ota-custom-source.json").read_text())

    def reproduce(self):
        for file in ("Image", "Module.symvers", "final.config",
                     "build-metadata.txt", "image-reproducibility.env"):
            shutil.copy2(self.features / file, self.rebuild / file)
        out = self.root / "comparison.json"
        self.run_py("cross-ota-lkg.py", "compare", "--source-dir", self.features,
                    "--rebuild-dir", self.rebuild, "--run-id", RUN_ID,
                    "--head-sha", RUN_HEAD, "--output", out)
        return json.loads(out.read_text())

    def promoted(self):
        record = self.root / "new-lkg.json"
        self.run_py("cross-ota-lkg.py", "promote", "--source-dir", self.features,
                    "--rebuild-report", self.root / "comparison.json",
                    "--current", self.root / "missing-current.json",
                    "--run-id", RUN_ID, "--head-sha", RUN_HEAD,
                    "--promotion-run-id", "872999",
                    "--note", "SIMULATED_NOT_REAL_DEVICE",
                    "--output", record)
        return json.loads(record.read_text())

    def release_archive(self, promoted):
        release = self.root / "release"
        release.mkdir()
        pfx = f"{FIXED_BUILD}-Gen4-"
        payload = {
            pfx + "ORIGINAL-USER-ATTESTED-boot.img": b"original boot",
            pfx + "ORIGINAL-USER-ATTESTED-AnyKernel3.zip": self.zip.read_bytes(),
            pfx + "REBUILT-CI-ONLY-boot.img": b"repro boot",
            pfx + "REBUILT-CI-ONLY-AnyKernel3.zip": self.zip.read_bytes(),
            pfx + "original-evidence.tar.zst": b"synthetic original evidence",
            pfx + "rebuilt-evidence.tar.zst": b"synthetic rebuild evidence",
            pfx + "manager-evidence.tar.zst": b"synthetic manager evidence",
            "README-RECOVERY.md": b"SIMULATED -- NOT A REAL DEVICE",
            "ota-lkg-promotion-record.json": json.dumps(promoted).encode(),
        }
        for name, data in payload.items():
            (release / name).write_bytes(data)
        (release / "SHA256SUMS-pandora-os4-lkg-gen4.txt").write_text(
            "".join(f"{digest(data)}  {name}\n" for name, data in sorted(payload.items())))
        self.run_py("verify-ota-lkg-release.py", "--dir", release,
                    "--tag", "pandora-os4-lkg-gen4")
        return release

    def journey(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        self.feature()
        self.finish_artifacts()
        self.reproduce()
        return self.promoted()

    def test_positive_complete_real_script_handoff_with_synthetic_evidence(self):
        promoted = self.journey()
        self.assertEqual(promoted["generation"], 4)
        self.assertEqual(promoted["stock_build"], FIXED_BUILD)
        self.assertEqual(promoted["reproduction"]["rebuild_device_tested"], False)
        self.release_archive(promoted)

    def test_oem_crc_changed_blocks_before_boot(self):
        self.stock_zip(crc=999)
        self.intake()
        report = self.oem_gate()
        self.assertEqual(report["gate"], "BLOCKED")
        self.assertTrue(report["crc_mismatches"])
        self.assertFalse(report["eligible_for_fastboot_boot"])

    def test_oem_vermagic_changed_blocks_before_boot(self):
        self.stock_zip(vermagic="6.12.99-android16-6-foreign-4k")
        self.intake()
        report = self.oem_gate()
        self.assertEqual(report["gate"], "BLOCKED")
        self.assertTrue(report["failed_modules"])

    def test_missing_oem_module_inventory_blocks_before_boot(self):
        self.stock_zip(omit_modules=True)
        self.intake()
        self.assertEqual(self.oem_gate()["gate"], "BLOCKED")

    def test_oem_module_count_mismatch_blocks_before_boot(self):
        self.stock_zip(module_count=3)
        self.intake()
        self.assertEqual(self.oem_gate()["gate"], "BLOCKED")

    def test_wrong_system_uname_blocks_intake(self):
        self.stock_zip(uname="6.12.99-android16-6-wrong-4k")
        self.run_py("inspect-ota-stock-input.py", "--zip", self.stock,
                    "--stock-config", self.stock_config,
                    "--output", self.stock_report, ok=False)

    def test_new_ota_without_gki_human_attestation_blocks_route(self):
        self.stock_zip()
        self.intake()
        self.run_py("ota-development-pointer.py", "select",
                    "--stock-report", self.stock_report, "--root", self.root,
                    "--output", self.root / "selection.txt", ok=False)

    def test_stock_asset_changed_after_confirmation_blocks_router(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        obj = json.loads(self.stock_report.read_text())
        obj["github_asset_id"] = "50000"
        self.stock_report.write_text(json.dumps(obj))
        self.run_py("ota-development-pointer.py", "select", "--root", self.root,
                    "--stock-report", self.stock_report, "--pointer", self.pointer,
                    "--output", self.root / "selection.txt", ok=False)

    def test_feature_symvers_crc_drift_blocks_install_artifacts(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        self.feature()
        modified = (self.features / "Module.symvers").read_text().replace(
            "0x000001f5\tsym_1", "0x000001f9\tsym_1")
        (self.features / "Module.symvers").write_text(modified)
        self.feature_meta["SYMVERS_SHA256"] = digest(modified.encode())
        self.write_feature_metadata()
        self.check_feature_abi(ok=False)
        self.assertEqual(json.loads(
            (self.features / "ota-custom-abi-report.json").read_text())["gate"], "BLOCKED")

    def test_image_changes_after_artifact_capture_blocks_promote(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        self.feature()
        self.finish_artifacts()
        (self.features / "Image").write_bytes(b"TAMPERED")
        self.run_py("cross-ota-lkg.py", "verify", "--artifact-dir", self.features,
                    "--run-id", RUN_ID, "--head-sha", RUN_HEAD, ok=False)

    def test_upstream_ref_changed_after_artifact_capture_blocks_promote(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        self.feature()
        self.finish_artifacts()
        p = self.features / "locked-upstreams.env"
        p.write_text(p.read_text().replace("RESOLVED_SUSFS_REF=main",
                                          "RESOLVED_SUSFS_REF=old"))
        self.run_py("cross-ota-lkg.py", "verify", "--artifact-dir", self.features,
                    "--run-id", RUN_ID, "--head-sha", RUN_HEAD, ok=False)

    def test_rebuild_config_drift_blocks_stable_pointer(self):
        self.stock_zip()
        self.intake()
        self.boot_confirm()
        self.route()
        self.feature()
        self.finish_artifacts()
        self.reproduce()
        (self.rebuild / "final.config").write_text("CHANGED CONFIG\n")
        self.run_py("cross-ota-lkg.py", "compare", "--source-dir", self.features,
                    "--rebuild-dir", self.rebuild, "--run-id", RUN_ID,
                    "--head-sha", RUN_HEAD, "--output", self.root / "failed.json",
                    ok=False)

    def test_tampered_release_blocks_publication(self):
        promoted = self.journey()
        released = self.release_archive(promoted)
        (released / "README-RECOVERY.md").write_text("REPLACED")
        self.run_py("verify-ota-lkg-release.py", "--dir", released,
                    "--tag", "pandora-os4-lkg-gen4", ok=False)


if __name__ == "__main__":
    unittest.main()
