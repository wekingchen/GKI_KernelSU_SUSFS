#!/usr/bin/env bash
# One-time, read-only source capture for historical OEM ABI replay.
# NEVER replaces pandora-os4-stock-input or publishes a flashable kernel.
set -euo pipefail
[[ "${GITHUB_REPOSITORY:-}" == "wekingchen/GKI_KernelSU_SUSFS" &&
   "${GITHUB_REF_NAME:-}" == "dev" ]] || {
  echo "::error::Only the owner's protected dev workflow can freeze this reference"; exit 2;
}
: "${GH_TOKEN:?GitHub Actions token required}"
TAG="pandora-ota-v2-os406-raw-stock-reference"
NAME="pandora-stock-OS4.0.6.0.XBLCNXM-_b-xm.zip"
REF="scripts/xiaomi-os4/ota-v2-references/pandora-os4-406-raw-oem-abi.json"
EXPECTED="$(jq -er '.source.stock_input_sha256' "$REF")"
BUILD="$(jq -er '.source.stock_build' "$REF")"
[[ "$EXPECTED" =~ ^[a-f0-9]{64}$ && "$BUILD" == "OS4.0.6.0.XBLCNXM" ]] || exit 2
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/download"
# Use the authenticated releases list because GitHub's "get by tag" API
# intentionally hides drafts; never assume a 404 means a draft is absent.
LIST="$(gh api "repos/$GITHUB_REPOSITORY/releases?per_page=100")"
MATCHES="$(jq --arg tag "$TAG" '[.[] | select(.tag_name == $tag)]' <<<"$LIST")"
[[ "$(jq 'length' <<<"$MATCHES")" -le 1 ]] || {
  echo "::error::Ambiguous immutable archive Release identity"; exit 1;
}
EXISTING="$(jq -c '.[0] // empty' <<<"$MATCHES")"
if [[ -n "$EXISTING" ]]; then
  jq -e --arg tag "$TAG" --arg sha "$EXPECTED" '
    .tag_name == $tag and .prerelease == true
    and (.body | contains($sha))
    and ((.assets | length) <= 1)
  ' <<<"$EXISTING" >/dev/null || {
    echo "::error::Existing historical Release identity changed"; exit 1;
  }
fi
ASSET_ID=""
if [[ -n "$EXISTING" ]]; then
  ASSET_ID="$(jq -r --arg name "$NAME" '.assets[]? | select(.name == $name) | .id' <<<"$EXISTING")"
fi
if [[ -z "$ASSET_ID" ]]; then
  SOURCE="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/pandora-os4-stock-input")"
  jq -e --arg name "$NAME" --arg sha "$EXPECTED" '
    .draft == false and .tag_name == "pandora-os4-stock-input"
    and ([.assets[] | select(.name == $name and .state == "uploaded"
      and .digest == ("sha256:" + $sha) and .size > 0)] | length == 1)
    and ([.assets[] | select(.name | endswith("xm.zip"))] | length == 1)
  ' <<<"$SOURCE" >/dev/null || {
    echo "::error::Current fixed OTA stock no longer matches the frozen OS4.0.6 source"; exit 1;
  }
  CURRENT_ASSET="$(jq -er --arg name "$NAME" '.assets[] | select(.name == $name) | .id' <<<"$SOURCE")"
  CURRENT_SIZE="$(jq -er --arg name "$NAME" '.assets[] | select(.name == $name) | .size' <<<"$SOURCE")"
  [[ "$CURRENT_ASSET" =~ ^[1-9][0-9]*$ && "$CURRENT_SIZE" =~ ^[1-9][0-9]*$ ]] || exit 1
  curl --fail --location --silent --show-error --retry 3 \
    --header "Authorization: Bearer $GH_TOKEN" \
    --header "Accept: application/octet-stream" \
    --output "$WORK/$NAME" \
    "https://api.github.com/repos/$GITHUB_REPOSITORY/releases/assets/$CURRENT_ASSET"
  [[ "$(stat -c%s "$WORK/$NAME")" == "$CURRENT_SIZE" ]] || exit 1
  [[ "$(sha256sum "$WORK/$NAME" | cut -d' ' -f1)" == "$EXPECTED" ]] || exit 1
  python3 - "$WORK/$NAME" "$BUILD" <<'PY'
import hashlib,sys,zipfile
archive,build=sys.argv[1:]
required={"boot.img","init_boot.img","vendor_boot.img","dtbo.img",
          "oem-modules.zip","oem-modules-count.txt","README.txt","SHA256SUMS.txt"}
with zipfile.ZipFile(archive) as z:
    if set(z.namelist())!=required or z.testzip() is not None:
        raise SystemExit("historic stock archive entries/CRC do not match")
    desc=z.read("README.txt").decode("utf-8",errors="strict")
    if f"device=pandora\nbuild={build}\n" not in desc:
        raise SystemExit("historic stock build or device mismatched")
    records={}
    for line in z.read("SHA256SUMS.txt").decode("ascii").splitlines():
        fields=line.split()
        if len(fields)!=2 or fields[1] in records:
            raise SystemExit("unsafe SHA256SUMS record")
        records[fields[1]]=fields[0]
    if set(records)!={"boot.img","init_boot.img","vendor_boot.img","dtbo.img","oem-modules.zip"}:
        raise SystemExit("missing historical kernel image/module digest")
    for name,digest in records.items():
        sha=hashlib.sha256()
        with z.open(name) as data:
            while chunk:=data.read(256*1024):
                sha.update(chunk)
        if sha.hexdigest()!=digest:
            raise SystemExit("historical input ZIP contains a changed component")
PY
  if [[ -z "$EXISTING" ]]; then
    cat >"$WORK/notes.md" <<EOF
Permanent read-only reference for historical Xiaomi 17 Pro / pandora / $BUILD OEM ABI BLOCKED regression.
EXACT_HISTORICAL_STOCK_SHA256=$EXPECTED
Origin: formerly fixed pandora-os4-stock-input Release, copied before any future OTA replacement.
Source is ROOTED_ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK, NOT a factory-original image.
NOT_FLASHABLE; no automatic boot, persistent installation or LKG authorization.
This historical replay reference is immutable by protocol and never follows future stock-input.
EOF
    echo "::notice::Creating private-by-default Draft by numeric GitHub Release API"
    EXISTING="$(gh api -X POST "repos/$GITHUB_REPOSITORY/releases" \
      -f tag_name="$TAG" -f target_commitish="$GITHUB_SHA" \
      -f name="pandora OS4.0.6 historical OEM ABI raw reference (NO FLASH)" \
      -f body="$(cat "$WORK/notes.md")" -F draft=true -F prerelease=true)"
  fi
  RELEASE_ID="$(jq -er '.id' <<<"$EXISTING")"
  [[ "$RELEASE_ID" =~ ^[1-9][0-9]*$ ]] || exit 1
  jq -e --arg tag "$TAG" --arg sha "$EXPECTED" '
    .tag_name == $tag and .draft == true and .prerelease == true and
    (.body | contains($sha))
  ' <<<"$EXISTING" >/dev/null || {
    echo "::error::Archive must be unpublished before its asset is uploaded"; exit 1;
  }
  echo "::notice::Uploading verified stock bytes to Draft by numeric Release ID"
  UPLOADED="$(curl --fail --location --silent --show-error --retry 2 \
    --request POST \
    --header "Authorization: Bearer $GH_TOKEN" \
    --header "Accept: application/vnd.github+json" \
    --header "Content-Type: application/zip" \
    --data-binary "@$WORK/$NAME" \
    "https://uploads.github.com/repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID/assets?name=$NAME")"
  ASSET_ID="$(jq -er --arg name "$NAME" '.id as $id |
    select(.name == $name and .state == "uploaded" and .size > 0) | $id' <<<"$UPLOADED")"
  [[ "$ASSET_ID" =~ ^[1-9][0-9]*$ ]] || exit 1
fi
# A complete already-published archive is also checked here; never overwrite it.
RELEASE_ID="$(jq -er '.id' <<<"$EXISTING")"
[[ "$RELEASE_ID" =~ ^[1-9][0-9]*$ && "$ASSET_ID" =~ ^[1-9][0-9]*$ ]] || exit 1
RELEASE="$(gh api "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID")"
jq -e --arg tag "$TAG" --arg name "$NAME" --arg sha "$EXPECTED" --argjson asset "$ASSET_ID" '
  .tag_name == $tag and .prerelease == true and (.body | contains($sha))
  and (.assets | length == 1)
  and ([.assets[] | select(.id == $asset and .name == $name
    and .state == "uploaded" and .digest == ("sha256:" + $sha)
    and .size > 0)] | length == 1)
' <<<"$RELEASE" >/dev/null || { echo "::error::Frozen reference identity incorrect"; exit 1; }
echo "::notice::Downloading the numeric archive asset for independent SHA check"
curl --fail --location --silent --show-error --retry 2 \
  --header "Authorization: Bearer $GH_TOKEN" \
  --header "Accept: application/octet-stream" \
  --output "$WORK/download/$NAME" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/releases/assets/$ASSET_ID"
test -s "$WORK/download/$NAME"
[[ "$(sha256sum "$WORK/download/$NAME" | cut -d' ' -f1)" == "$EXPECTED" ]] || exit 1
if [[ "$(jq -r '.draft' <<<"$RELEASE")" == true ]]; then
  echo "::notice::SHA matched; publishing the complete read-only prerelease"
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID" \
    -F draft=false -F prerelease=true >/dev/null
fi
RELEASE="$(gh api "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID")"
jq -e --arg tag "$TAG" --arg name "$NAME" --arg sha "$EXPECTED" '
  .tag_name == $tag and .draft == false and .prerelease == true and
  (.assets | length == 1) and
  ([.assets[] | select(.name == $name and .digest == ("sha256:" + $sha))] | length == 1)
' <<<"$RELEASE" >/dev/null || {
  echo "::error::Archive Release was not safely published"; exit 1;
}
echo "PANDORA_OS406_HISTORICAL_STOCK_ARCHIVE=PASS tag=$TAG SHA=$EXPECTED"
{
  echo "### Pandora OTA V2 historical input frozen (read-only)"
  echo "- Immutable reference: $TAG"
  echo "- Source SHA-256: $EXPECTED"
  echo "- Full ZIP entries and checksums validated"
  echo "- Downloaded Release asset and checked its SHA independently"
  echo "- Never changes the active stock-input, OEM ABI, any phone partition or LKG"
} >> "$GITHUB_STEP_SUMMARY"
