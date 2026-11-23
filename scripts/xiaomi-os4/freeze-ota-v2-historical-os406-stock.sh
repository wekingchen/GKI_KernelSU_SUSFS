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
EXISTING=""
if EXISTING="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TAG" 2>/dev/null)"; then
  jq -e --arg tag "$TAG" '
    .tag_name == $tag and .draft == false and .prerelease == true
  ' <<<"$EXISTING" >/dev/null || {
    echo "::error::Existing historical Release is not the exact published prerelease"; exit 1;
  }
fi
CURRENT_ASSET=""
if [[ -z "$EXISTING" ]] || [[ "$(jq '.assets | length' <<<"$EXISTING")" == 0 ]]; then
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
    gh release create "$TAG" --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" \
      --prerelease --latest=false --title "pandora OS4.0.6 historical OEM ABI raw reference (NO FLASH)" \
      --notes-file "$WORK/notes.md"
  fi
  gh release upload "$TAG" "$WORK/$NAME" --repo "$GITHUB_REPOSITORY"
fi
RELEASE="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TAG")"
jq -e --arg tag "$TAG" --arg name "$NAME" --arg sha "$EXPECTED" '
  .tag_name == $tag and .draft == false and .prerelease == true
  and (.assets | length == 1)
  and ([.assets[] | select(.name == $name and .state == "uploaded"
    and .digest == ("sha256:" + $sha) and .size > 0)] | length == 1)
' <<<"$RELEASE" >/dev/null || { echo "::error::Frozen reference identity incorrect"; exit 1; }
gh release download "$TAG" --repo "$GITHUB_REPOSITORY" --pattern "$NAME" --dir "$WORK/download"
test -s "$WORK/download/$NAME"
[[ "$(sha256sum "$WORK/download/$NAME" | cut -d' ' -f1)" == "$EXPECTED" ]] || exit 1
echo "PANDORA_OS406_HISTORICAL_STOCK_ARCHIVE=PASS tag=$TAG SHA=$EXPECTED"
{
  echo "### Pandora OTA V2 historical input frozen (read-only)"
  echo "- Immutable reference: $TAG"
  echo "- Source SHA-256: $EXPECTED"
  echo "- Full ZIP entries and checksums validated"
  echo "- Downloaded Release asset and checked its SHA independently"
  echo "- Never changes the active stock-input, OEM ABI, any phone partition or LKG"
} >> "$GITHUB_STEP_SUMMARY"
