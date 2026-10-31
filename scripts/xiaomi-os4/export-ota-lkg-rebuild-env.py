#!/usr/bin/env python3
"""Export source-validated OTA feature selections for deterministic rebuild.

Never source the candidate's free-form build-metadata.txt as a shell script.
Only validated boolean fields, controlled modes and 40-hex commit IDs are emitted.
"""
import argparse
import json
import re
from pathlib import Path

FLAG_MAP = {
    "SUSFS_EXTRA_FEATURES": "XIAOMI_OS4_SUSFS_EXTRA_FEATURES",
    "USE_NOMOUNT": "XIAOMI_OS4_USE_NOMOUNT",
    "DROIDSPACES_ENABLED": "XIAOMI_OS4_DROIDSPACES",
    "USE_NTSYNC": "XIAOMI_OS4_USE_NTSYNC",
    "USE_BBG": "XIAOMI_OS4_USE_BBG",
    "USE_REKERNEL": "XIAOMI_OS4_USE_REKERNEL",
    "USE_NETWORKING": "XIAOMI_OS4_USE_NETWORKING",
    "USE_CVE": "XIAOMI_OS4_USE_CVE",
}
COMMIT_MAP = {
    "BAKASU": "OS4_BAKASU_COMMIT",
    "SUSFS": "OS4_SUSFS_COMMIT",
    "NOMOUNT": "OS4_NOMOUNT_COMMIT",
    "DROIDSPACES": "OS4_DROIDSPACES_COMMIT",
    "NTSYNC": "OS4_NTSYNC_PATCH_COMMIT",
    "BBG": "OS4_BBG_COMMIT",
    "REKERNEL": "OS4_REKERNEL_COMMIT",
}
ap = argparse.ArgumentParser()
ap.add_argument("--manifest", type=Path, required=True)
ap.add_argument("--output", type=Path, required=True)
a = ap.parse_args()
m = json.loads(a.manifest.read_text())
assert m["kind"] == "PANDORA_OS4_OTA_CUSTOM_SOURCE"
flags, pins = m["selections"], m["upstream_commits"]
root = flags["ROOT_MODE"]
assert root in ("bakasu-susfs", "bakasu", "none")
out = ["XIAOMI_OS4_NEW_OTA=1", "XIAOMI_OS4_SELECTABLE_BUILD=1",
       "XIAOMI_OS4_ROOT_MODE=" + root]
for key, dest in FLAG_MAP.items():
    value = flags[key]
    assert value in ("0", "1"), key
    out.append(dest + "=" + value)
for key, dest in COMMIT_MAP.items():
    value = pins[key]
    assert re.fullmatch("[0-9a-f]{40}", value), key
    out.append(dest + "=" + value)
REF_MAP = {
    "BAKASU": ("OS4_BAKASU_REF_KIND", "OS4_BAKASU_REF"),
    "SUSFS": ("OS4_SUSFS_REF_KIND", "OS4_SUSFS_BRANCH"),
    "NOMOUNT": ("OS4_NOMOUNT_REF_KIND", "OS4_NOMOUNT_REF"),
    "DROIDSPACES": ("OS4_DROIDSPACES_REF_KIND", "OS4_DROIDSPACES_REF"),
    "NTSYNC": ("OS4_NTSYNC_REF_KIND", "OS4_NTSYNC_PATCH_REF"),
    "BBG": ("OS4_BBG_REF_KIND", "OS4_BBG_REF"),
    "REKERNEL": ("OS4_REKERNEL_REF_KIND", "OS4_REKERNEL_REF"),
}
refs = m["upstream_refs"]
for key, (kind_key, ref_key) in REF_MAP.items():
    k = refs[key]["kind"]
    ref = refs[key]["ref"]
    assert k in ("branch", "tag")
    assert re.fullmatch(r"[A-Za-z0-9._/+-]+", ref)
    out.extend((kind_key + "=" + k, ref_key + "=" + ref))
a.output.write_text("\n".join(out) + "\n")
print("PINNED_OTA_REBUILD_ENV=PASS")
