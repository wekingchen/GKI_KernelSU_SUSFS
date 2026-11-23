#!/usr/bin/env python3
"""Unpublished LKG Release identity and authenticated asset metadata regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "draft_assets", HERE / "check-ota-lkg-draft-assets.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TAG = "pandora-os4-lkg-gen7"
BUILD = "OS4.0.6.0.XBLCNXM"
STEM = f"{BUILD}-Gen7-"
NAMES = (
    STEM + "original-evidence.tar.zst",
    STEM + "rebuilt-evidence.tar.zst",
    STEM + "manager-evidence.tar.zst",
    STEM + "ORIGINAL-USER-ATTESTED-boot.img",
    STEM + "ORIGINAL-USER-ATTESTED-AnyKernel3.zip",
    STEM + "REBUILT-CI-ONLY-boot.img",
    STEM + "REBUILT-CI-ONLY-AnyKernel3.zip",
    "README-RECOVERY.md",
    "ota-lkg-promotion-record.json",
    f"SHA256SUMS-{TAG}.txt",
)


class DraftAssets(unittest.TestCase):
    def setUp(self):
        self.release = {
            "id": 455102692,
            "tag_name": TAG,
            "draft": True,
            "assets": [
                {"id": 781970438 + i, "name": name, "size": 100 + i,
                 "digest": "sha256:" + format(i + 1, "064x"), "state": "uploaded"}
                for i, name in enumerate(NAMES)
            ],
        }

    def verify(self):
        return mod.verify_assets(self.release, TAG, BUILD)

    def test_current_gen7_draft_with_original_and_rebuilt_evidence(self):
        out = self.verify()
        self.assertEqual(len(out), 10)
        self.assertEqual(out[0][1], sorted(NAMES)[0])
        self.assertEqual({x[1] for x in out}, set(NAMES))

    def test_no_manager_supported_for_root_disabled(self):
        self.release["assets"] = [
            a for a in self.release["assets"] if "manager-evidence" not in a["name"]
        ]
        self.assertEqual(len(self.verify()), 9)

    def test_rejects_no_draft_or_wrong_release_id(self):
        self.release["draft"] = False
        with self.assertRaises(ValueError):
            self.verify()
        self.release["draft"] = True
        self.release["id"] = 0
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_unlisted_extra_and_missing_assets(self):
        self.release["assets"].append({
            "id": 10000, "name": "unknown-script.sh", "size": 100,
            "digest": "sha256:" + "0" * 64, "state": "uploaded",
        })
        with self.assertRaises(ValueError):
            self.verify()
        self.release["assets"].pop()
        self.release["assets"].pop()
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_duplicate_asset_ids_and_names(self):
        self.release["assets"][0]["id"] = self.release["assets"][1]["id"]
        with self.assertRaises(ValueError):
            self.verify()
        self.release["assets"][0]["id"] = 781970438
        self.release["assets"][0]["name"] = self.release["assets"][1]["name"]
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_missing_digest_or_wrong_asset_size(self):
        self.release["assets"][0]["digest"] = None
        with self.assertRaises(ValueError):
            self.verify()
        self.release["assets"][0]["digest"] = "sha256:" + "a" * 64
        self.release["assets"][0]["size"] = -1
        with self.assertRaises(ValueError):
            self.verify()
        self.release["assets"][0]["size"] = 100
        self.release["assets"][0]["state"] = "starter"
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_name_path_traversal_or_foreign_gen(self):
        self.release["assets"][0]["name"] = "../etc/passwd"
        with self.assertRaises(ValueError):
            self.verify()
        self.release["assets"][0]["name"] = STEM.replace("Gen7", "Gen8") + "original-evidence.tar.zst"
        with self.assertRaises(ValueError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
