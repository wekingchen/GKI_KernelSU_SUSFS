#!/usr/bin/env bash
# Cross-OTA stable promotion: verify source -> locked rebuild -> archive -> PR.
set -euo pipefail
[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 2
[[ "$GITHUB_REF_NAME" == "dev" && "$GITHUB_EVENT_NAME" == "workflow_dispatch" ]] || exit 2
[[ "$SOURCE_RUN_ID" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$CONFIRM_BOOT" == true && "$CONFIRM_PERSISTENT" == true && "$CONFIRM_RUNTIME" == true ]] || {
  echo "::error::没有同时确认真机开机、持久使用和实际功能正常"; exit 2;
}
cd "$(dirname "$0")/../.."
export GH_REPO="$GITHUB_REPOSITORY"
BASE_SHA="$(git rev-parse HEAD)"
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || exit 1
WORK="$RUNNER_TEMP/ota-lkg-$GITHUB_RUN_ID"
SRC="$WORK/source"; BASE="$WORK/baseline"; OUT="$WORK/archive"; RES="$WORK/rebuilt"
mkdir -p "$SRC" "$BASE" "$OUT" "$RES" "$WORK/stock" "$WORK/manager" "$WORK/ak3"
RUN="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID")"
jq -e '.status=="completed" and .conclusion=="success" and .event=="workflow_dispatch" and
  .head_branch=="dev" and .path==".github/workflows/xiaomi-sm8850-os4-custom.yml"' <<<"$RUN" >/dev/null
SOURCE_SHA="$(jq -r .head_sha <<<"$RUN")"
[[ "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ ]] || exit 1
A="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID/artifacts?per_page=100")"
ARTIFACT="$(jq -r --arg id "$SOURCE_RUN_ID" '
  [.artifacts[] | select(.expired==false) | .name |
   select(test("^pandora-OTA-CUSTOM-OS[0-9A-Z.]+-run-"+$id+"$"))] |
  if length==1 then .[0] else empty end' <<<"$A")"
[[ -n "$ARTIFACT" ]] || { echo "::error::缺少唯一、未过期的新 OTA 自定义包"; exit 1; }
gh run download "$SOURCE_RUN_ID" --name "$ARTIFACT" --dir "$SRC"
python3 scripts/xiaomi-os4/cross-ota-lkg.py verify --artifact-dir "$SRC" \
  --run-id "$SOURCE_RUN_ID" --head-sha "$SOURCE_SHA"
[[ -s "$SRC/image-reproducibility.env" ]] || { echo "::error::未知 Image 随机区域，禁止晋升"; exit 1; }
BUILD="$(jq -r .stock_build "$SRC/ota-custom-source.json")"
[[ "$(jq -r .build .github/config/ota-development-current.json)" == "$BUILD" ]] || exit 1
cmp -s "$SRC/verified-baseline.json" ".github/config/ota-verified/$BUILD/verification.json"
cmp -s "$SRC/fixture.json" ".github/config/ota-verified/$BUILD/fixture.json"
STOCK="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/pandora-os4-stock-input")"
ASSET="$(jq -r '[.assets[]|select(.name|endswith("xm.zip"))]|
 if length==1 then .[0].id else empty end' <<<"$STOCK")"
[[ "$ASSET" == "$(jq -r .stock_release_asset_id "$SRC/ota-custom-source.json")" ]] || exit 1
gh release download pandora-os4-stock-input --pattern '*xm.zip' --dir "$WORK/stock"
ZIP="$(find "$WORK/stock" -maxdepth 1 -name '*xm.zip' -type f -print -quit)"
[[ -s "$ZIP" ]] || exit 1
python3 scripts/xiaomi-os4/inspect-ota-stock-input.py --zip "$ZIP" \
  --stock-config .github/config/pandora-os4-stock-input.env \
  --github-asset-id "$ASSET" --output "$WORK/stock.json"
[[ "$(jq -r .ota_source_id "$WORK/stock.json")" == \
  "$(jq -r .stock_input_sha256 "$SRC/ota-custom-source.json")" ]] || exit 1
gh release download "pandora-os4-ota-candidate-$BUILD" --dir "$BASE"
(cd "$BASE" && sha256sum -c RELEASE-SHA256SUMS.txt)
python3 scripts/xiaomi-os4/ota-development-pointer.py prepare --stock-report "$WORK/stock.json" \
  --candidate-dir "$BASE" --output "$WORK/gki.env"
python3 scripts/xiaomi-os4/export-ota-lkg-rebuild-env.py --manifest "$SRC/ota-custom-source.json" \
  --output "$WORK/features.env"
set -a
source "$WORK/gki.env"
source "$WORK/features.env"
set +a
export XIAOMI_OS4_VERIFIED_OTA_ENV="$WORK/gki.env"
bash scripts/xiaomi-os4/build-r62-features.sh
BUILT="$RUNNER_TEMP/xiaomi-os4-integrated/results"
for f in Image Module.symvers final.config build-metadata.txt; do
  [[ -s "$BUILT/$f" ]] || exit 1
  cp "$BUILT/$f" "$RES/$f"
done
python3 scripts/xiaomi-os4/check-ota-feature-abi.py --baseline-symvers "$BASE/Module.symvers" \
  --feature-symvers "$RES/Module.symvers" \
  --baseline-record ".github/config/ota-verified/$BUILD/verification.json" \
  --feature-metadata "$RES/build-metadata.txt" --report "$RES/ota-custom-abi-report.json"
python3 scripts/xiaomi-os4/describe-image-reproducibility.py "$RES/Image" \
  --output-env "$RES/image-reproducibility.env"
python3 scripts/xiaomi-os4/cross-ota-lkg.py compare --source-dir "$SRC" --rebuild-dir "$RES" \
  --run-id "$SOURCE_RUN_ID" --head-sha "$SOURCE_SHA" \
  --output "$RES/reproduction-report.json"
REL="$(jq -r .kernel_release "$SRC/ota-custom-source.json")"
python3 scripts/xiaomi-os4/repack-fastboot-boot-v4-from-fixture.py \
  ".github/config/ota-verified/$BUILD/fixture.json" "$RES/Image" "$RES/REBUILT-boot.img" \
  --expected-image-sha256 "$(sha256sum "$RES/Image" | cut -d' ' -f1)" \
  --expected-release "$REL" --expected-build "$BUILD"
XIAOMI_AK3_MODE=ota-custom XIAOMI_AK3_BUILD="$BUILD" XIAOMI_AK3_RELEASE="$REL" \
XIAOMI_AK3_OTA_BASELINE_RECORD=".github/config/ota-verified/$BUILD/verification.json" \
XIAOMI_AK3_OTA_FIXTURE=".github/config/ota-verified/$BUILD/fixture.json" \
XIAOMI_AK3_OTA_ABI_REPORT="$RES/ota-custom-abi-report.json" \
XIAOMI_AK3_OTA_METADATA="$RES/build-metadata.txt" \
  bash scripts/xiaomi-os4/package-validated-anykernel3.sh "$RES/Image" "$WORK/ak3"
REBUILT_AK3="$(find "$WORK/ak3" -maxdepth 1 -name '*-UNVERIFIED-AnyKernel3.zip' -type f -print -quit)"
[[ -s "$REBUILT_AK3" ]] || exit 1
[[ "$(unzip -p "$REBUILT_AK3" Image | sha256sum | cut -d' ' -f1)" == \
   "$(sha256sum "$RES/Image" | cut -d' ' -f1)" ]] || exit 1
MODE="$(jq -r .selections.ROOT_MODE "$SRC/ota-custom-source.json")"
if [[ "$MODE" != none ]]; then
  gh run download "$SOURCE_RUN_ID" --name "BakaSU-Manager-pandora-OS4-run-$SOURCE_RUN_ID" --dir "$WORK/manager"
  [[ -s "$WORK/manager/manager-metadata.txt" ]] || exit 1
  (cd "$WORK/manager" && sha256sum -c MANAGER-SHA256SUMS.txt)
  [[ "$(sed -n 's/^MANAGER_HEAD_SHA=//p' "$WORK/manager/manager-metadata.txt")" == \
   "$(jq -r .upstream_commits.BAKASU "$SRC/ota-custom-source.json")" ]] || exit 1
fi
POINTER="$WORK/promotion.json"
python3 scripts/xiaomi-os4/cross-ota-lkg.py promote --source-dir "$SRC" \
  --rebuild-report "$RES/reproduction-report.json" \
  --current .github/config/ota-lkg-current.json --run-id "$SOURCE_RUN_ID" \
  --head-sha "$SOURCE_SHA" --promotion-run-id "$GITHUB_RUN_ID" \
  --note "$PROMOTION_NOTE" --output "$POINTER"
GEN="$(jq -r .generation "$POINTER")"
TAG="pandora-os4-lkg-gen$GEN"
[[ "$TAG" == "$(jq -r .archive_tag "$POINTER")" ]] || exit 1
ORIG_BOOT="$(jq -r .boot_name "$SRC/ota-custom-source.json")"
ORIG_ZIP="$(jq -r .anykernel_name "$SRC/ota-custom-source.json")"
cp "$SRC/$ORIG_BOOT" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-boot.img"
cp "$SRC/$ORIG_ZIP" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-AnyKernel3.zip"
cp "$RES/REBUILT-boot.img" "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-boot.img"
cp "$REBUILT_AK3" "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-AnyKernel3.zip"
cp "$POINTER" "$OUT/ota-lkg-promotion-record.json"
tar -I 'zstd -T2 -6' -cf "$OUT/$BUILD-Gen$GEN-original-evidence.tar.zst" -C "$SRC" .
tar -I 'zstd -T2 -6' -cf "$OUT/$BUILD-Gen$GEN-rebuilt-evidence.tar.zst" -C "$RES" .
if [[ "$MODE" != none ]]; then
  tar -I 'zstd -T2 -6' -cf "$OUT/$BUILD-Gen$GEN-manager-evidence.tar.zst" -C "$WORK/manager" .
fi
cat > "$OUT/README-RECOVERY.md" <<EOF
Device pandora / HyperOS $BUILD / Gen $GEN / kernel $REL
Original Run: $SOURCE_RUN_ID ; Promotion Run: $GITHUB_RUN_ID
ORIGINAL files were user-attested booted and persistently stable.
REBUILT-CI-ONLY are normalized Image / exact config and ABI verified,
but HAVE NOT been independently run on a real device.
Never install on another OTA. Keep your same-version known-good boot.
EOF
(cd "$OUT" && find . -maxdepth 1 -type f ! -name "SHA256SUMS-$TAG.txt" -printf '%f\0' \
 | LC_ALL=C sort -z | xargs -0 sha256sum > "SHA256SUMS-$TAG.txt")
(cd "$OUT" && sha256sum -c "SHA256SUMS-$TAG.txt")
cat > "$WORK/notes.md" <<EOF
SOURCE_RUN_ID=$SOURCE_RUN_ID
PROMOTION_RUN_ID=$GITHUB_RUN_ID
STOCK_BUILD=$BUILD
USER_ATTESTED_ORIGINAL_AND_CI_REPRODUCED=YES
A Release published before the new current LKG pointer; no old Gen3 changes.
EOF
if gh release view "$TAG" >/dev/null 2>&1; then
  CHECK="$(gh release view "$TAG" --json isDraft,body)"
  jq -e --arg s "SOURCE_RUN_ID=$SOURCE_RUN_ID" --arg p "PROMOTION_RUN_ID=$GITHUB_RUN_ID" \
   '.isDraft==true and (.body|contains($s)) and (.body|contains($p))' <<<"$CHECK" >/dev/null
else
  gh release create "$TAG" --target "$BASE_SHA" --draft --latest=false \
   --title "pandora $BUILD Gen $GEN user-attested LKG" --notes-file "$WORK/notes.md"
fi
for file in "$OUT"/*; do
  name="$(basename "$file")"
  if ! gh release view "$TAG" --json assets --jq '.assets[].name' | grep -Fxq "$name"; then
    gh release upload "$TAG" "$file"
  fi
done
mkdir -p "$WORK/check-release"
gh release download "$TAG" --dir "$WORK/check-release"
cmp -s "$OUT/SHA256SUMS-$TAG.txt" "$WORK/check-release/SHA256SUMS-$TAG.txt"
(cd "$WORK/check-release" && sha256sum -c "SHA256SUMS-$TAG.txt")
gh release edit "$TAG" --draft=false --latest=false
[[ "$(gh release view "$TAG" --json isDraft --jq .isDraft)" == false ]] || exit 1

# Pointer moves last, only after successful independent Release verification.
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || {
 echo "::error::dev changed during build; recovery Release preserved, pointer untouched"; exit 1;
}
CURRENT=".github/config/ota-lkg-current.json"
HISTORY=""
if [[ -f "$CURRENT" ]]; then
  OLD="$(jq -r .generation "$CURRENT")"
  HISTORY=".github/config/ota-lkg-history/gen$OLD.json"
  [[ ! -e "$HISTORY" ]] || exit 1
  mkdir -p "$(dirname "$HISTORY")"
  cp "$CURRENT" "$HISTORY"
fi
cp "$POINTER" "$CURRENT"
BRANCH="ota/lkg-gen$GEN-run$GITHUB_RUN_ID"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch -c "$BRANCH"
git add "$CURRENT"
COUNT=1
if [[ -n "$HISTORY" ]]; then git add "$HISTORY"; COUNT=2; fi
[[ "$(git diff --cached --name-only | wc -l)" -eq "$COUNT" ]] || exit 1
git diff --cached --name-only | grep -Fxq "$CURRENT"
if [[ -n "$HISTORY" ]]; then git diff --cached --name-only | grep -Fxq "$HISTORY"; fi
git commit -m "xiaomi(os4): promote cross-OTA LKG Gen $GEN / $BUILD"
bash scripts/xiaomi-os4/check-upstream-isolation.sh "$BASE_SHA" --committed
git push origin "$BRANCH"
HEAD_SHA="$(git rev-parse HEAD)"
URL="$(gh pr create --base dev --head "$BRANCH" \
 --title "xiaomi(os4): cross-OTA Gen $GEN $BUILD" \
 --body "Source Run $SOURCE_RUN_ID user-attested stable; reproducibility passed; Release $TAG independently downloaded and SHA checked. Historical Gen3 unchanged.")"
NUM="$(basename "$URL")"
PR="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM")"
jq -e --arg h "$HEAD_SHA" --arg b "$BRANCH" \
 '.state=="open" and .draft==false and .base.ref=="dev" and .head.ref==$b and .head.sha==$h' <<<"$PR" >/dev/null
FILES="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM/files?per_page=100" --jq '.[].filename')"
[[ "$(wc -l <<<"$FILES")" -eq "$COUNT" ]] || exit 1
grep -Fxq "$CURRENT" <<<"$FILES"
if [[ -n "$HISTORY" ]]; then grep -Fxq "$HISTORY" <<<"$FILES"; fi
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || exit 1
for i in {1..12}; do
  MERGEABLE="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM" --jq .mergeable)"
  [[ "$MERGEABLE" != null ]] && break
  sleep 3
done
[[ "$MERGEABLE" == true ]] || exit 1
gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$NUM/merge" \
 -f merge_method=squash -f sha="$HEAD_SHA" -f commit_title="xiaomi(os4): LKG Gen $GEN $BUILD" \
 | jq -e '.merged==true and (.sha|length)==40' >/dev/null
gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" >/dev/null || true
echo "CROSS_OTA_LKG=PASS generation=$GEN build=$BUILD release=$TAG"
echo "Cross OTA LKG Gen $GEN: source attested; strict CI rebuild and Release verified; $URL" >> "$GITHUB_STEP_SUMMARY"
