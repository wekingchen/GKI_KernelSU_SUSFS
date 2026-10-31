#!/usr/bin/env python3
"""Select a *candidate*, never a verified OEM match, from Google's public GKI release catalog."""
from __future__ import annotations
import argparse
import datetime
import hashlib
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

CATALOG_URL = "https://source.android.com/docs/core/architecture/kernel/gki-android16-6_12-release-builds.json"
GKI_TAG = re.compile(r"^android16-6\.12-[0-9]{4}-[0-9]{2}_r[1-9][0-9]*$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
    def handle_data(self, data: str):
        self.parts.append(data)


def load_catalog(url: str) -> tuple[dict, str]:
    req = Request(url, headers={"User-Agent": "pandora-os4-ota-candidate/1.0"})
    with urlopen(req, timeout=45) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("catalog exceeds 2MB")
    doc = raw.decode("utf-8", "replace")
    parser = Text()
    parser.feed(doc)
    text = " ".join(parser.parts)
    match = re.search(r'\{\s*"name"\s*:\s*"android16-6\.12"\s*,\s*"branches"\s*:\s*\[', text)
    if not match:
        raise ValueError("official catalog JSON could not be found; stop rather than guess")
    catalog, _ = json.JSONDecoder().raw_decode(text[match.start():])
    if catalog.get("name") != "android16-6.12" or not isinstance(catalog.get("branches"), list):
        raise ValueError("unexpected official GKI catalog")
    return catalog, hashlib.sha256(raw).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ota-report", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--env", required=True, type=Path)
    ap.add_argument("--catalog-url", default=CATALOG_URL)
    args = ap.parse_args()
    ota = json.loads(args.ota_report.read_text(encoding="utf-8"))
    if ota.get("status") != "NEW_OTA_CANDIDATE" or not ota.get("may_build_gki_candidate"):
        raise SystemExit("ERROR: GKI candidate requested for non-new/non-supported OTA")
    if ota.get("kmi") != "android16-6" or not re.fullmatch(r"6\.12\.[0-9]+", ota.get("kernel_version", "")):
        raise SystemExit("ERROR: unsupported KMI family")
    catalog, digest = load_catalog(args.catalog_url)
    matches = []
    for branch in catalog["branches"]:
        if branch.get("kernel_version") != ota["kernel_version"]:
            continue
        for rel in branch.get("releases", []):
            tag, sha, date = rel.get("tag", ""), rel.get("sha1", ""), rel.get("date", "")
            if GKI_TAG.fullmatch(tag) and SHA1.fullmatch(sha):
                try:
                    parsed_date = datetime.date.fromisoformat(date)
                except ValueError:
                    continue
                matches.append((parsed_date.isoformat(), int(tag.rsplit("_r", 1)[1]), rel, branch["name"]))
    if not matches:
        raise SystemExit("ERROR: no published GKI source for exact 6.12.x patch version; manual source review required")
    # Catalog has multiple respins; choose a reproducible investigation candidate,
    # NOT a claimed OEM-equivalent source. Build ID equality is additional evidence only.
    match_bid = re.search(r"abogki([0-9]+)", ota.get("uname", ""))
    requested_bid = match_bid.group(1) if match_bid else ""
    precise = [x for x in matches if x[2].get("kernel_bid") == requested_bid] if requested_bid else []
    candidates = precise or matches
    candidates.sort(key=lambda x: (x[0], x[1], x[2]["tag"]))
    _, _, rel, branch = candidates[-1]
    picked = {
        "schema": 1, "safe_to_flash": False, "not_oem_source_proven": True,
        "device": "pandora", "build": ota["build"], "kernel_version": ota["kernel_version"],
        "kmi": ota["kmi"], "ota_source_id": ota["ota_source_id"],
        "catalog_url": CATALOG_URL, "catalog_response_sha256": digest,
        "candidate_tag": rel["tag"], "candidate_commit": rel["sha1"], "candidate_branch": branch,
        "candidate_date": rel["date"], "candidate_kernel_bid": str(rel.get("kernel_bid", "")),
        "selection_reason": "EXACT_OFFICIAL_GKI_BUILD_ID" if precise else "SAME_PATCH_LATEST_OFFICIAL_GKI_CANDIDATE",
        "matching_official_releases": len(matches), "candidate_not_verified_by_device": True,
        "human_gate": "REAL_DEVICE_TEMP_BOOT_AND_VENDOR_ABI_REVIEW_REQUIRED",
        "lkg_unchanged": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(picked, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    # Strict fixed known alphabet only. Never source arbitrary README text into shell.
    variables = {
        "OTA_BUILD": picked["build"], "OTA_KERNEL_VERSION": picked["kernel_version"],
        "OTA_KMI": picked["kmi"], "OTA_GKI_TAG": picked["candidate_tag"],
        "OTA_GKI_COMMIT": picked["candidate_commit"], "OTA_SELECTION_REASON": picked["selection_reason"],
        "OTA_INPUT_SHA256": picked["ota_source_id"],
    }
    for value in variables.values():
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise SystemExit("ERROR: unsafe release metadata for shell")
    args.env.write_text("".join(f"{k}={v}\n" for k, v in variables.items()), encoding="utf-8")
    print(json.dumps(picked, ensure_ascii=False, indent=2))
    print("OTA_GKI_STATUS=UNVERIFIED_CANDIDATE_ONLY")


if __name__ == "__main__":
    main()
