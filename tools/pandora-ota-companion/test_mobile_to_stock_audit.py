#!/usr/bin/env python3
"""Synthetic positive bridge: Android device capture -> xm.zip -> existing OEM stock-input audit.

No firmware, releases, secrets, or actual stock input are touched.
"""
from __future__ import annotations
import io
import json
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from normalize_mobile_capture import normalize

BASE = Path(__file__).resolve().parent
STOCK_AUDIT = BASE.parents[1] / "scripts" / "xiaomi-os4" / "inspect-ota-stock-input.py"
BUILD = "OS4.0.6.0.XBLCNXM"
KERNEL = "6.12.70-android16-6-gabcdef01-4k"


def boot_v4() -> bytes:
    kernel_size = 8192
    image = bytearray(os.urandom(4096 + kernel_size))
    image[:8] = b"ANDROID!"
    struct.pack_into("<IIII", image, 8, kernel_size, 0, 0, 1584)
    struct.pack_into("<I", image, 40, 4)
    struct.pack_into("<I", image, 1580, 0)
    marker = f"Linux version {KERNEL} #1 SMP PREEMPT".encode()
    image[4096:4096 + len(marker)] = marker
    return bytes(image)


def capture(path: Path, *, build: str = BUILD) -> None:
    manifest = (
        "schema=pandora-ota-capture-v1\n"
        "source=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\n"
        "device=pandora\n"
        "ro.product.device=pandora\n"
        f"ro.mi.os.version.incremental={build}\n"
        "ro.boot.slot_suffix=_a\nslot=_a\n"
        f"uname={KERNEL}\n"
    )
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as archive:
        data = b"\x7fELF" + os.urandom(512)
        item = tarfile.TarInfo("vendor_dlkm/lib/modules/synthetic.ko")
        item.size = len(data)
        archive.addfile(item, io.BytesIO(data))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr("manifest.txt", manifest)
        outer.writestr("kernel-release.txt", KERNEL + "\n")
        outer.writestr("oem-modules.tar", tar_stream.getvalue())
        for part in ("boot", "init_boot", "vendor_boot", "dtbo"):
            outer.writestr(part + "_a.img",
                           boot_v4() if part == "boot" else os.urandom(8192))


class MobileIntakeIntegration(unittest.TestCase):
    def test_mobile_normalized_bundle_passes_real_stock_audit(self):
        self.assertTrue(STOCK_AUDIT.is_file(), STOCK_AUDIT)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            input_zip = base / "mobile.zip"
            xm = base / f"pandora-stock-{BUILD}-_a-xm.zip"
            config = base / "stock.env"
            result = base / "stock-audit.json"
            config.write_text(
                "OS4_STOCK_INPUT_BUILD=OS4.0.5.0.XBLCNXM\n"
                "OS4_STOCK_BOOT_SHA256=" + "0" * 64 + "\n", encoding="utf-8"
            )
            capture(input_zip)
            meta = normalize(input_zip, xm)
            self.assertEqual(meta["modules"], 1)
            run = subprocess.run(
                [sys.executable, str(STOCK_AUDIT), "--zip", str(xm),
                 "--stock-config", str(config), "--output", str(result),
                 "--github-asset-id", "12345"],
                check=False, text=True, capture_output=True
            )
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            report = json.loads(result.read_text())
            self.assertEqual(report["device"], "pandora")
            self.assertEqual(report["status"], "NEW_OTA_CANDIDATE")
            self.assertEqual(report["build"], BUILD)
            self.assertEqual(report["header_version"], 4)
            self.assertEqual(report["kernel_version"], "6.12.70")
            self.assertTrue(report["kernel_marker_verified"])
            self.assertTrue(report["may_build_gki_candidate"])
            self.assertFalse(report["safe_to_flash"])
            self.assertEqual(report["github_asset_id"], "12345")
            self.assertEqual(report["source_provenance"], "BOOT_KERNEL_MARKER_AND_README_AGREE")

    def test_same_build_boot_drift_stops_before_release_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            input_zip, xm = base / "mobile.zip", base / "mobile-xm.zip"
            config, report = base / "old.env", base / "report.json"
            capture(input_zip, build="OS4.0.5.0.XBLCNXM")
            normalize(input_zip, xm)
            config.write_text(
                "OS4_STOCK_INPUT_BUILD=OS4.0.5.0.XBLCNXM\n"
                "OS4_STOCK_BOOT_SHA256=" + "f" * 64 + "\n",
                encoding="utf-8"
            )
            p = subprocess.run(
                [sys.executable, str(STOCK_AUDIT), "--zip", str(xm),
                 "--stock-config", str(config), "--output", str(report)],
                check=False, capture_output=True, text=True
            )
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("same HyperOS build but stock boot changed",
                          p.stderr + p.stdout)


if __name__ == "__main__":
    unittest.main()
