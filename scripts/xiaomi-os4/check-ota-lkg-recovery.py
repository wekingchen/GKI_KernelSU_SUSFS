#!/usr/bin/env python3
"""Fail-closed offline identity validation for reusing an already SHA-verified LKG draft.

The original promotion job must have completed a reproducible Image/ABI build,
but failed *after* writing a verified draft. Recovery does not claim a new
independent rebuild; it rechecks exact source artifacts and archived evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPO = "wekingchen/GKI_KernelSU_SUSFS"
WORKFLOW = ".github/workflows/xiaomi-sm8850-os4-promote-lkg.yml"
SOURCE_WORKFLOW = ".github/workflows/xiaomi-sm8850-os4-custom.yml"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")


def require(ok: bool, reason: str):
    if not ok:
        raise ValueError("LKG DRAFT RECOVERY DENIED: " + reason)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(pointer: dict, record: dict, release: dict, source: dict,
           promotion: dict, manifest: dict, source_dir: Path,
           rebuild_dir: Path):
    gen = pointer.get("generation")
    require(isinstance(gen, int) and gen >= 4 and
            pointer.get("schema") == 1 and
            pointer.get("status") == "USER_PROMOTED_OTA_LKG",
            "current LKG pointer invalid")
    require(record.get("schema") == 1 and
            record.get("status") == "USER_PROMOTED_OTA_LKG" and
            record.get("generation") == gen + 1 and
            record.get("archive_tag") == f"pandora-os4-lkg-gen{gen + 1}",
            "draft generation not immediately after current LKG")
    require(record.get("device") == pointer.get("device") == "pandora" and
            record.get("stock_build") == pointer.get("stock_build") and
            record.get("kernel_release") == pointer.get("kernel_release") and
            record.get("gki_commit") == pointer.get("gki_commit") and
            record.get("stock_input_sha256") == pointer.get("stock_input_sha256") and
            record.get("stock_release_asset_id") == pointer.get("stock_release_asset_id"),
            "draft and currently trusted OTA/GKI identity differ")
    require(record.get("source_run_id") != pointer.get("source_run_id") and
            record.get("legacy_r62_lkg_unchanged") is True and
            record.get("attestation") ==
            "USER_CONFIRMED_BOOT_AND_PERSISTENT_STABILITY_NOT_REMOTE_HARDWARE_PROOF",
            "source reuse or attestation mismatch")
    require(release.get("draft") is True and
            release.get("tag_name") == record.get("archive_tag") and
            release.get("target_commitish") == promotion.get("head_sha"),
            "draft Release tag/target/head mismatch")
    src_id, prom_id = record.get("source_run_id"), record.get("promotion_run_id")
    require(isinstance(src_id, int) and src_id > 0 and
            isinstance(prom_id, int) and prom_id > 0 and src_id != prom_id,
            "invalid source and original promotion run IDs")
    require(source.get("id") == src_id and source.get("status") == "completed" and
            source.get("conclusion") == "success" and
            source.get("event") == "workflow_dispatch" and
            source.get("path") == SOURCE_WORKFLOW and
            source.get("head_branch") == "dev" and
            source.get("repository", {}).get("full_name") == REPO and
            SHA40.fullmatch(source.get("head_sha", "")) is not None and
            source["head_sha"] == record.get("source_head_sha"),
            "original custom run source SHA/identity mismatch")
    require(promotion.get("id") == prom_id and
            promotion.get("status") == "completed" and
            promotion.get("conclusion") == "failure" and
            promotion.get("event") == "workflow_dispatch" and
            promotion.get("path") == WORKFLOW and
            promotion.get("head_branch") == "dev" and
            promotion.get("repository", {}).get("full_name") == REPO and
            SHA40.fullmatch(promotion.get("head_sha", "")) is not None,
            "previous failed LKG workflow run identity mismatch")
    body = release.get("body", "")
    require(isinstance(body, str) and
            f"SOURCE_RUN_ID={src_id}\n" in body and
            f"PROMOTION_RUN_ID={prom_id}\n" in body and
            f"STOCK_BUILD={record['stock_build']}\n" in body and
            "USER_ATTESTED_ORIGINAL_AND_CI_REPRODUCED=YES" in body,
            "draft Release provenance text mismatch")
    require(manifest.get("source_run_id") == src_id and
            manifest.get("source_head_sha") == record["source_head_sha"] and
            manifest.get("stock_build") == record["stock_build"] and
            manifest.get("image_sha256") == record["image_sha256"] and
            manifest.get("boot_sha256") == record["boot_sha256"] and
            manifest.get("anykernel_sha256") == record["anykernel_sha256"] and
            manifest.get("gki_commit") == record["gki_commit"] and
            manifest.get("selections") == record.get("selections") and
            manifest.get("upstream_commits") == record.get("upstream_commits") and
            sha(source_dir / "ota-custom-source.json") ==
            record.get("source_manifest_sha256"),
            "original source manifest no longer matches promoted record")
    require(SHA64.fullmatch(record.get("image_sha256", "")) is not None and
            sha(source_dir / "Image") == record["image_sha256"] and
            SHA64.fullmatch(record.get("boot_sha256", "")) is not None and
            SHA64.fullmatch(record.get("anykernel_sha256", "")) is not None,
            "original kernel/Image/boot hashes invalid")
    reproduced = json.loads((rebuild_dir / "reproduction-report.json").read_text())
    require(reproduced == record.get("reproduction") and
            reproduced.get("source_image_sha256") == record["image_sha256"] and
            reproduced.get("rebuild_verification") ==
            "NORMALIZED_IMAGE_AND_EXACT_SYMVERS_CONFIG_PASS" and
            reproduced.get("rebuild_device_tested") is False,
            "archived rebuild proof does not match original promotion")
    require(manifest.get("real_device_feature_test") ==
            "USER_ATTESTED_AT_PROMOTION" and
            manifest.get("kind") == "PANDORA_OS4_OTA_COMPAT_CUSTOM_SOURCE" and
            manifest.get("compat_custom_promotion") is True,
            "draft recovery is restricted to separately tested COMPAT-CUSTOM")
    return True


def main():
    ap = argparse.ArgumentParser()
    for name in ("pointer", "record", "release", "source-run", "promotion-run",
                 "source-manifest"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--source-dir", type=Path, required=True)
    ap.add_argument("--rebuild-dir", type=Path, required=True)
    a = ap.parse_args()
    def read(arg: str) -> dict:
        return json.loads(getattr(a, arg).read_text(encoding="utf-8"))
    verify(read("pointer"), read("record"), read("release"), read("source_run"),
           read("promotion_run"), read("source_manifest"),
           a.source_dir, a.rebuild_dir)
    print("LKG_VERIFIED_DRAFT_RECOVERY_IDENTITY=PASS")


if __name__ == "__main__":
    main()
