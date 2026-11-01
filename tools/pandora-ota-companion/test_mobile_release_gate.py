#!/usr/bin/env python3
"""Offline contract for the GitHub Draft Release identity gate.

An auto-renamed untagged-* draft is trusted only with a matching prior
server-side attachment receipt. No real GitHub calls or OTA data involved.
"""
from __future__ import annotations
import json
import subprocess
import unittest
from pathlib import Path

FILTER = Path(__file__).with_name("mobile-release-gate.jq")
SHA = "a" * 64
ASSET_ID = 697520792
RELEASE_ID = 430401431


def document(*, tag="pandora-ota-capture-123456", body="",
             draft=True, name="Pandora OS4 OTA capture — private intake"):
    return {
        "id": RELEASE_ID, "tag_name": tag, "body": body,
        "draft": draft, "name": name,
    }


def receipt(asset=ASSET_ID, sha=SHA, state="REJECTED"):
    return (
        f"MOBILE_OTA_INTAKE={state}\n"
        f"MOBILE_ASSET_ID={asset}\n"
        f"MOBILE_SOURCE_SHA256={sha}\n"
    )


def accepted(release, *, asset=ASSET_ID, sha=SHA):
    result = subprocess.run(
        ["jq", "-e", "--argjson", "id", str(RELEASE_ID),
         "--argjson", "asset", str(asset), "--arg", "sha", sha,
         "-f", str(FILTER)],
        input=json.dumps(release), text=True, capture_output=True, check=False
    )
    if result.returncode > 3:
        raise AssertionError("jq filter invalid: " + result.stderr)
    return result.returncode == 0


class DraftIdentityGateTest(unittest.TestCase):
    def test_fresh_app_owned_draft(self):
        self.assertTrue(accepted(document()))

    def test_real_upload_retry_with_prior_rejected_receipt(self):
        self.assertTrue(accepted(document(tag="untagged-72b3f3", body=receipt())))

    def test_untagged_without_prior_receipt_cannot_enter(self):
        self.assertFalse(accepted(document(tag="untagged-other")))

    def test_untagged_with_other_asset_or_sha_cannot_enter(self):
        self.assertFalse(accepted(document(tag="untagged-other",
                                           body=receipt(asset=ASSET_ID + 1))))
        self.assertFalse(accepted(document(tag="untagged-other",
                                           body=receipt(sha="b" * 64))))

    def test_exact_lines_no_substring_impersonation(self):
        body = receipt(asset=ASSET_ID * 10)
        self.assertFalse(accepted(document(tag="untagged-other", body=body)))

    def test_non_draft_or_other_name_or_release_never_enter(self):
        self.assertFalse(accepted(document(draft=False)))
        self.assertFalse(accepted(document(name="arbitrary draft")))
        self.assertFalse(accepted(document(tag="untagged-other", body=receipt(),
                                           name="arbitrary draft")))
        invalid = document(tag="untagged-other", body=receipt())
        invalid["id"] = RELEASE_ID + 1
        self.assertFalse(accepted(invalid))


if __name__ == "__main__":
    unittest.main()
