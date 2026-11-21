#!/usr/bin/env python3
"""Regression tests for the GitHub Release asset upload endpoint used by OTA intake."""
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "stock_input_transaction", Path(__file__).with_name("stock-input-transaction.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeHTTPResponse(io.BytesIO):
    status = 201

    def __init__(self, asset):
        super().__init__(json.dumps(asset).encode())


class ReleaseAssetUpload(unittest.TestCase):
    def test_uses_real_uploads_host_and_verifies_downloaded_bytes(self):
        payload = b"stock input backup"
        asset = dict(id=123, name="stock-backup-44887787130.zip",
                     size=len(payload), state="uploaded")
        captured = []

        def fake_urlopen(request, timeout=None):
            captured.append((request, timeout))
            return FakeHTTPResponse(asset)

        api = module.GitHub()
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
             patch.object(module, "urlopen", side_effect=fake_urlopen), \
             patch.object(api, "download", return_value=payload) as download, \
             patch.object(module.subprocess, "check_output",
                          side_effect=AssertionError("gh api must not handle asset upload")):
            self.assertEqual(api.upload(453565849, asset["name"], payload), asset)

        request, timeout = captured[0]
        self.assertEqual(request.full_url,
            "https://uploads.github.com/repos/wekingchen/GKI_KernelSU_SUSFS/"
            "releases/453565849/assets?name=stock-backup-44887787130.zip")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, payload)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(request.get_header("Content-type"), "application/octet-stream")
        self.assertEqual(timeout, 300)
        download.assert_called_once_with(123)

    def test_rejects_unverified_asset_bytes(self):
        payload = b"correct"
        asset = dict(id=123, name="backup.zip", size=len(payload), state="uploaded")
        api = module.GitHub()
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
             patch.object(module, "urlopen", return_value=FakeHTTPResponse(asset)), \
             patch.object(api, "download", return_value=b"wrong"):
            with self.assertRaisesRegex(ValueError, "download verification"):
                api.upload(2, "backup.zip", payload)

    def test_rejects_unexpected_upload_metadata(self):
        payload = b"correct"
        asset = dict(id=123, name="backup.zip", size=len(payload)-1, state="uploaded")
        api = module.GitHub()
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
             patch.object(module, "urlopen", return_value=FakeHTTPResponse(asset)), \
             patch.object(api, "download", side_effect=AssertionError("must not download")):
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                api.upload(2, "backup.zip", payload)

    def test_missing_token_or_invalid_name_fails_before_network(self):
        api = module.GitHub()
        with patch.dict(os.environ, {"GH_TOKEN": ""}), \
             patch.object(module, "urlopen", side_effect=AssertionError("no network")):
            with self.assertRaisesRegex(RuntimeError, "GH_TOKEN required"):
                api.upload(2, "backup.zip", b"data")
        with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
             patch.object(module, "urlopen", side_effect=AssertionError("no network")):
            with self.assertRaisesRegex(ValueError, "invalid release upload arguments"):
                api.upload(2, "../invalid.zip", b"data")


if __name__ == "__main__":
    unittest.main()
