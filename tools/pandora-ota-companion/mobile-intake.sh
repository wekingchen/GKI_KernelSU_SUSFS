#!/usr/bin/env bash
# No flashing; validate mobile upload before replacing the single fixed OTA input.
set -Eeuo pipefail
: "$GITHUB_REPOSITORY" "$GH_TOKEN" "$RUNNER_TEMP" "$STAGED_RELEASE_ID" "$STAGED_ASSET_ID" "$CLIENT_SHA" "$CLIENT_BYTES"
[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 2
[[ "$STAGED_RELEASE_ID" =~ ^[0-9]+$ && "$STAGED_ASSET_ID" =~ ^[0-9]+$ ]] || exit 2
[[ "$CLIENT_SHA" =~ ^[0-9a-f]{64}$ && "$CLIENT_BYTES" =~ ^[0-9]+$ ]] || exit 2
[[ "$CLIENT_BYTES" -gt 0 && "$CLIENT_BYTES" -lt 996147200 ]] || exit 2
R="$GITHUB_REPOSITORY"
DIR="$RUNNER_TEMP/pandora-mobile-intake"
mkdir -p "$DIR/input" "$DIR/converted" "$DIR/check"
echo '## 手机 OTA 只读采集安全接收' >> "$GITHUB_STEP_SUMMARY"
echo '本工作流不会刷机、更新 LKG 或跳过原 OEM ABI/KMI 门禁。' >> "$GITHUB_STEP_SUMMARY"

RELEASE="$(gh api "repos/$R/releases/$STAGED_RELEASE_ID")"
jq -e --argjson id "$STAGED_RELEASE_ID" \
  --argjson asset "$STAGED_ASSET_ID" --arg sha "$CLIENT_SHA" \
  -f tools/pandora-ota-companion/mobile-release-gate.jq \
  <<< "$RELEASE" >/dev/null
TAG="$(jq -r .tag_name <<< "$RELEASE")"
ASSET="$(jq -e --argjson id "$STAGED_ASSET_ID" \
  '[.assets[] | select(.id == $id)] | if length == 1 then .[0] else error("missing asset") end' \
  <<< "$RELEASE")"
ASSET_NAME="$(jq -r .name <<< "$ASSET")"
[[ "$ASSET_NAME" =~ ^pandora-os4-capture-[0-9]{8}-[0-9]{6}(-[0-9]{3})?\.zip$ ]] || exit 3
test "$(jq -r .size <<< "$ASSET")" = "$CLIENT_BYTES"

# Machine-readable source Draft Release receipt. This is NOT GKI or LKG verification.
RECEIPT_VALID=1
publish_receipt() {
  local state="$1"
  local body
  printf -v body 'MOBILE_OTA_INTAKE=%s\nMOBILE_ASSET_ID=%s\nMOBILE_SOURCE_SHA256=%s\nMOBILE_BUILD=%s\nMOBILE_INTAKE_RUN=%s\nSOURCE_PROVENANCE=ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK\n' \
    "$state" "$STAGED_ASSET_ID" "$CLIENT_SHA" "${BUILD:-UNKNOWN}" "$GITHUB_RUN_ID"
  # GitHub may replace draft tag_name with untagged-* when updating its body.
  # Restore a stable app-owned tag so existing APK receipt queries still work.
  gh api -X PATCH "repos/$R/releases/$STAGED_RELEASE_ID" \
    -f tag_name="pandora-ota-capture-$STAGED_RELEASE_ID" -f body="$body" >/dev/null
}
on_intake_exit() {
  local code=$?
  trap - EXIT
  if [[ "$code" -ne 0 && "${RECEIPT_VALID:-0}" == "1" ]]; then
    publish_receipt REJECTED || true
  fi
  exit "$code"
}
trap on_intake_exit EXIT
# Draft Releases may not resolve by tag (GitHub gives untagged-* links).
# Fetch the exact authenticated asset by ID; a SHA-256 and size match is mandatory.
gh api -H "Accept: application/octet-stream" \
  "repos/$R/releases/assets/$STAGED_ASSET_ID" > "$DIR/input/$ASSET_NAME"
SOURCE="$DIR/input/$ASSET_NAME"
test -s "$SOURCE"
echo "$CLIENT_SHA  $SOURCE" | sha256sum -c -
test "$(stat -c '%s' "$SOURCE")" = "$CLIENT_BYTES"

python3 tools/pandora-ota-companion/normalize_mobile_capture.py \
  --input "$SOURCE" --output "$DIR/converted/incoming-xm.zip" \
  > "$DIR/normalize-report.json"
BUILD="$(jq -r .build "$DIR/normalize-report.json")"
SLOT="$(jq -r .slot "$DIR/normalize-report.json")"
NEW_NAME="pandora-stock-$BUILD-$SLOT-xm.zip"
NEW="$DIR/converted/$NEW_NAME"
mv "$DIR/converted/incoming-xm.zip" "$NEW"
python3 scripts/xiaomi-os4/inspect-ota-stock-input.py \
  --zip "$NEW" \
  --stock-config .github/config/pandora-os4-stock-input.env \
  --output "$DIR/stock-audit.json"
STATE="$(jq -r .status "$DIR/stock-audit.json")"
if [[ "$STATE" == "SAME_PINNED_BUILD" ]]; then
  echo '当前固定输入已匹配，跳过重复 OTA 转换。' >> "$GITHUB_STEP_SUMMARY"
  publish_receipt ALREADY_CURRENT
  exit 0
fi
[[ "$STATE" == "NEW_OTA_CANDIDATE" ]] || {
  echo "::error::OTA 来源身份审计阻断，固定输入完全不变"; exit 4;
}

# Validate canonical manifest and count before touching the fixed release.
python3 - "$NEW" <<'PY'
import hashlib, io, re, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    names = ["boot.img","init_boot.img","vendor_boot.img","dtbo.img","oem-modules.zip"]
    # These mandatory labels prevent the Root-patched active init_boot from
    # being silently promoted as a factory-original / flashable OEM image.
    readme = dict(line.split("=", 1) for line in
                  z.read("README.txt").decode("utf-8").splitlines()
                  if "=" in line)
    expected = {
        "boot_oem_original_verified": "NO",
        "boot_role": "GKI_KERNEL_ANALYSIS_INPUT",
        "init_boot_source": "ROOTED_ACTIVE_SLOT_MAY_BE_PATCHED",
        "init_boot_oem_original_verified": "NO",
        "init_boot_role": "DIAGNOSTIC_ONLY_NOT_FACTORY_IMAGE",
    }
    if any(readme.get(key) != value for key, value in expected.items()):
        raise SystemExit("source provenance missing: rooted init_boot is not factory OEM input")
    records = {}
    for line in z.read("SHA256SUMS.txt").decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in records:
            raise SystemExit("invalid SHA256SUMS")
        records[match[2]] = match[1]
    if set(names) != set(records):
        raise SystemExit("incomplete SHA256SUMS")
    for name in names:
        if hashlib.sha256(z.read(name)).hexdigest() != records[name]:
            raise SystemExit("sha256 mismatch")
    count = int(z.read("oem-modules-count.txt").decode().strip().split("=")[1])
    with zipfile.ZipFile(io.BytesIO(z.read("oem-modules.zip"))) as nested:
        actual = sum(bool(re.search(r"\.ko(\.(zst|xz|gz))?$", n, re.I))
                     for n in nested.namelist())
    if not (1 <= count == actual <= 4096):
        raise SystemExit("OEM module count mismatch")
PY

FIXED_TAG="pandora-os4-stock-input"
FIXED="$(gh api "repos/$R/releases/tags/$FIXED_TAG")"
jq -e --arg tag "$FIXED_TAG" '.draft == false and .tag_name == $tag' <<< "$FIXED" >/dev/null
mapfile -t OLD_IDS < <(jq -r '.assets[] | select(.name | endswith("xm.zip")) | .id' <<< "$FIXED")
[[ 1 -eq "$(printf '%s\n' "$FIXED" | jq '[.assets[] | select(.name | endswith("xm.zip"))] | length')" ]] || exit 5
OLD_ID="$OLD_IDS"
OLD_NAME="$(jq -r --argjson id "$OLD_ID" '.assets[] | select(.id == $id) | .name' <<< "$FIXED")"
FIXED_ID="$(jq -r .id <<< "$FIXED")"
gh release download "$FIXED_TAG" --repo "$R" --pattern "$OLD_NAME" --dir "$DIR/check"
test -s "$DIR/check/$OLD_NAME"
# Never silently replace the exact same OTA version with different bytes.
# Existing legacy pinned ZIP lacks README, and is intentionally exempt.
set +e
python3 - "$DIR/check/$OLD_NAME" "$NEW" "$BUILD" <<'PY'
import hashlib, sys, zipfile
previous, incoming, build = sys.argv[1:]
with zipfile.ZipFile(previous) as z:
    matches = [x for x in z.namelist() if x.rsplit("/", 1)[-1] == "README.txt"]
    old_build = ""
    if len(matches) == 1:
        for row in z.read(matches[0]).decode("utf-8", "replace").splitlines():
            if row.startswith("build="):
                old_build = row.split("=", 1)[1].strip()
if old_build == build:
    def digest(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(262144), b""):
                h.update(block)
        return h.hexdigest()
    if digest(previous) != digest(incoming):
        raise SystemExit("same OTA build, changed ZIP bytes: manual review required")
    print("identical current OTA ZIP; no replacement necessary")
    raise SystemExit(80)
PY
rc=$?
set -e
if [[ "$rc" -eq 80 ]]; then
  echo '与现有新 OTA 完全相同，禁止无意义替换资产 ID。' >> "$GITHUB_STEP_SUMMARY"
  publish_receipt ALREADY_CURRENT
  exit 0
fi
[[ "$rc" -eq 0 ]] || { echo "::error::同版本完整 ZIP 漂移或损坏"; exit 8; }

# Stage first under a name that DOES NOT match the original *xm.zip filter.
PENDING="pandora-mobile-pending-$GITHUB_RUN_ID.upload"
cp "$NEW" "$DIR/converted/$PENDING"
gh release upload "$FIXED_TAG" "$DIR/converted/$PENDING" --repo "$R"
NEW_ID="$(gh api "repos/$R/releases/$FIXED_ID" | jq -r --arg name "$PENDING" '.assets[] | select(.name == $name) | .id')"
[[ "$NEW_ID" =~ ^[0-9]+$ ]] || exit 6
gh release download "$FIXED_TAG" --repo "$R" --pattern "$PENDING" --dir "$DIR/check"
if ! cmp -s "$NEW" "$DIR/check/$PENDING"; then
  gh api -X DELETE "repos/$R/releases/assets/$NEW_ID" || true
  echo "::error::固定 Release 暂存附件下载 SHA 检查失败，旧输入未改动"; exit 6
fi

# New asset is fully verified before renaming; the old one is only then removed.
gh api -X PATCH "repos/$R/releases/assets/$NEW_ID" -f name="$NEW_NAME" >/dev/null
if ! gh api -X DELETE "repos/$R/releases/assets/$OLD_ID"; then
  gh api -X DELETE "repos/$R/releases/assets/$NEW_ID" || true
  echo "::error::旧资产删除失败，已回滚新资产"; exit 7
fi
FINAL="$(gh api "repos/$R/releases/$FIXED_ID")"
jq -e --argjson id "$NEW_ID" \
  '([.assets[] | select(.name | endswith("xm.zip"))] |
  length == 1 and .[0].id == $id)' <<< "$FINAL" >/dev/null

echo "固定 Release 已切换到：$NEW_NAME" >> "$GITHUB_STEP_SUMMARY"
echo "来源：ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK（非出厂原版保证）" >> "$GITHUB_STEP_SUMMARY"
echo "Asset ID: $NEW_ID" >> "$GITHUB_STEP_SUMMARY"
gh api -X PATCH "repos/$R/releases/$FIXED_ID" \
  -f body="pandora current OTA stock-input: $BUILD; active device capture (NOT factory-original proof); asset $NEW_ID" >/dev/null
if gh workflow run xiaomi-sm8850-os4-ota-auto-candidate.yml --repo "$R" --ref dev; then
  echo "已主动触发原 OS4 OTA 自动 GKI 候选检查" >> "$GITHUB_STEP_SUMMARY"
else
  echo "::warning::固定输入成功切换，但即时工作流触发失败；每日定时补查仍可接管"
fi
publish_receipt ACCEPTED
