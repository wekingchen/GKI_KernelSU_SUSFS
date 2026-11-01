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
  '.id == $id and .draft == true and (.tag_name | startswith("pandora-ota-capture-"))' \
  <<< "$RELEASE" >/dev/null
TAG="$(jq -r .tag_name <<< "$RELEASE")"
ASSET="$(jq -e --argjson id "$STAGED_ASSET_ID" \
  '[.assets[] | select(.id == $id)] | if length == 1 then .[0] else error("missing asset") end' \
  <<< "$RELEASE")"
ASSET_NAME="$(jq -r .name <<< "$ASSET")"
[[ "$ASSET_NAME" =~ ^pandora-os4-capture-[0-9]{8}-[0-9]{6}(-[0-9]{3})?\.zip$ ]] || exit 3
test "$(jq -r .size <<< "$ASSET")" = "$CLIENT_BYTES"
gh release download "$TAG" --repo "$R" --pattern "$ASSET_NAME" --dir "$DIR/input"
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
