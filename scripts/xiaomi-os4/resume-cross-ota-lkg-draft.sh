#!/usr/bin/env bash
# Recover an already fully verified draft after an unrelated dev-branch move.
# Do NOT re-label a CI rebuilt artifact as newly tested on a device.
set -euo pipefail
[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 2
[[ "$GITHUB_REF_NAME" == "dev" && "$GITHUB_EVENT_NAME" == "workflow_dispatch" ]] || exit 2
[[ "$CONFIRM_BOOT" == true && "$CONFIRM_PERSISTENT" == true && "$CONFIRM_RUNTIME" == true ]] || exit 2
[[ "$SOURCE_RUN_ID" =~ ^[1-9][0-9]*$ && "$SOURCE_SHA" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$PROMOTION_ROUTE_MODE" == "ota-compat-custom" ]] || {
  echo "::error::draft recovery is limited to the exact OS406 COMPAT-CUSTOM route"; exit 2;
}
cd "$(dirname "$0")/../.."
BASE_SHA="$(git rev-parse HEAD)"
WORK="$RUNNER_TEMP/lkg-draft-recovery-$GITHUB_RUN_ID"
OUT="$WORK/release"; SRC="$WORK/original"; RES="$WORK/rebuilt"; FRESH="$WORK/source-run"
mkdir -p "$OUT" "$SRC" "$RES" "$FRESH"
CURRENT=".github/config/ota-lkg-current.json"
[[ -s "$CURRENT" ]] || exit 1
GEN="$(jq -er '.generation+1' "$CURRENT")"
TAG="pandora-os4-lkg-gen$GEN"
BUILD="$(jq -er '.stock_build' "$CURRENT")"
RELEASE_JSON="$WORK/release.json"
# Draft releases are not reliably addressable via /releases/tags/<tag>.
# The authenticated list, then the immutable numeric release/asset IDs, work
# before publication. Never fall back to an untrusted tag download URL.
RELEASES_JSON="$WORK/releases.json"
gh api "repos/$GITHUB_REPOSITORY/releases?per_page=100" > "$RELEASES_JSON"
RELEASE_ID="$(jq -er --arg t "$TAG" '
  [.[] | select(.tag_name==$t)] |
  if length==1 and .[0].draft==true then .[0].id else error("missing/ambiguous draft") end
' "$RELEASES_JSON")"
[[ "$RELEASE_ID" =~ ^[1-9][0-9]*$ ]] || exit 1
gh api "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID" > "$RELEASE_JSON"
jq -e --arg t "$TAG" --argjson id "$RELEASE_ID" '
  .id==$id and .tag_name==$t and .draft==true
' "$RELEASE_JSON" >/dev/null || {
  echo "::error::draft Release ID/identity changed"; exit 1;
}
# Validate exactly the expected asset set, uploaded state, individual SHA-256
# digests and byte lengths before fetching any blob. GitHub's documented
# asset-by-ID octet-stream endpoint supports unpublished drafts.
python3 scripts/xiaomi-os4/check-ota-lkg-draft-assets.py \
  --release "$RELEASE_JSON" --tag "$TAG" --build "$BUILD" \
  --output "$WORK/draft-assets.tsv"
while IFS=
POINTER="$OUT/ota-lkg-promotion-record.json"
ORIGINAL_PROMOTION_RUN="$(jq -er .promotion_run_id "$POINTER")"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID" > "$WORK/source-run.json"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$ORIGINAL_PROMOTION_RUN" > "$WORK/promotion-run.json"
[[ "$(jq -r .head_sha "$WORK/source-run.json")" == "$SOURCE_SHA" ]] || exit 1
git merge-base --is-ancestor "$SOURCE_SHA" "$BASE_SHA" || exit 1
git merge-base --is-ancestor "$(jq -r .head_sha "$WORK/promotion-run.json")" "$BASE_SHA" || exit 1
tar -I zstd -xf "$OUT/$BUILD-Gen$GEN-original-evidence.tar.zst" -C "$SRC"
tar -I zstd -xf "$OUT/$BUILD-Gen$GEN-rebuilt-evidence.tar.zst" -C "$RES"
python3 scripts/xiaomi-os4/check-ota-lkg-recovery.py \
  --pointer "$CURRENT" --record "$POINTER" --release "$RELEASE_JSON" \
  --source-run "$WORK/source-run.json" --promotion-run "$WORK/promotion-run.json" \
  --source-manifest "$SRC/ota-custom-source.json" --source-dir "$SRC" --rebuild-dir "$RES"
cmp -s "$CURRENT" "$SRC/compat-custom-previous-lkg.json" || {
  echo "::error::trusted previous LKG has moved, refusing draft recovery"; exit 1;
}
python3 scripts/xiaomi-os4/cross-ota-lkg.py verify \
  --artifact-dir "$SRC" --run-id "$SOURCE_RUN_ID" --head-sha "$SOURCE_SHA"
python3 scripts/xiaomi-os4/cross-ota-lkg.py compare \
  --source-dir "$SRC" --rebuild-dir "$RES" --run-id "$SOURCE_RUN_ID" \
  --head-sha "$SOURCE_SHA" --output "$WORK/reverified-reproduction.json"
cmp -s "$WORK/reverified-reproduction.json" "$RES/reproduction-report.json" || {
  echo "::error::independent replay no longer matches the archived build proof"; exit 1;
}

# Do not blindly trust a self-consistent draft archive: independently retrieve
# the original immutable source-run artifact and compare all build-critical bytes.
ARTIFACT="pandora-OTA-COMPAT-CUSTOM-$BUILD-run-$SOURCE_RUN_ID"
ASSETS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID/artifacts?per_page=100")"
jq -e --arg name "$ARTIFACT" '
  [.artifacts[] | select(.expired==false and .name==$name)] | length==1
' <<<"$ASSETS" >/dev/null || {
  echo "::error::source Artifact expired/mismatched; do not trust archived copy"; exit 1;
}
gh run download "$SOURCE_RUN_ID" --name "$ARTIFACT" --dir "$FRESH"
for file in Image Module.symvers final.config build-metadata.txt \
            ota-custom-abi-report.json verified-baseline.json fixture.json locked-upstreams.env; do
  cmp -s "$SRC/$file" "$FRESH/$file" || {
    echo "::error::original Artifact differs from validated Release: $file"; exit 1;
  }
done
ORIG_BOOT="$(jq -er .boot_name "$SRC/ota-custom-source.json")"
ORIG_AK3="$(jq -er .anykernel_name "$SRC/ota-custom-source.json")"
cmp -s "$SRC/$ORIG_BOOT" "$FRESH/$ORIG_BOOT" || exit 1
cmp -s "$SRC/$ORIG_AK3" "$FRESH/$ORIG_AK3" || exit 1
[[ "$(sha256sum "$SRC/$ORIG_BOOT" | cut -d' ' -f1)" == "$(jq -r .boot_sha256 "$POINTER")" ]] || exit 1
[[ "$(sha256sum "$SRC/$ORIG_AK3" | cut -d' ' -f1)" == "$(jq -r .anykernel_sha256 "$POINTER")" ]] || exit 1
cmp -s "$SRC/$ORIG_BOOT" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-boot.img" || exit 1
cmp -s "$SRC/$ORIG_AK3" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-AnyKernel3.zip" || exit 1
[[ "$(sha256sum "$RES/REBUILT-boot.img" | cut -d' ' -f1)" == \
   "$(sha256sum "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-boot.img" | cut -d' ' -f1)" ]] || exit 1
[[ "$(unzip -p "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-AnyKernel3.zip" Image | sha256sum | cut -d' ' -f1)" == \
   "$(sha256sum "$RES/Image" | cut -d' ' -f1)" ]] || exit 1
STOCK="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/pandora-os4-stock-input")"
ASSET="$(jq -r '[.assets[] | select(.name | endswith("xm.zip"))] | if length==1 then .[0].id else empty end' <<<"$STOCK")"
[[ "$ASSET" == "$(jq -er .stock_release_asset_id "$POINTER")" ]] || exit 1
[[ "$(jq -er .build .github/config/ota-development-current.json)" == "$BUILD" ]] || exit 1
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || {
  echo "::error::dev moved while validating draft; leave existing draft untouched"; exit 1;
}
HISTORY=".github/config/ota-lkg-history/gen$((GEN-1)).json"
[[ ! -e "$HISTORY" ]] || { echo "::error::LKG history would be overwritten"; exit 1; }
mkdir -p "$(dirname "$HISTORY")"
cp "$CURRENT" "$HISTORY"
cp "$POINTER" "$CURRENT"
BRANCH="ota/lkg-gen$GEN-recovered-run$GITHUB_RUN_ID"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch -c "$BRANCH"
git add "$CURRENT" "$HISTORY"
[[ "$(git diff --cached --name-only | wc -l)" -eq 2 ]] || exit 1
git commit -m "xiaomi(os4): recover verified LKG Gen $GEN / $BUILD"
bash scripts/xiaomi-os4/check-upstream-isolation.sh "$BASE_SHA" --committed
git push origin "$BRANCH"
HEAD_SHA="$(git rev-parse HEAD)"
URL="$(gh pr create --base dev --head "$BRANCH" \
  --title "xiaomi(os4): recover SHA-verified Gen $GEN / $BUILD" \
  --body "Recover completed $TAG evidence from original failed promotion Run $ORIGINAL_PROMOTION_RUN (dev advanced only after independent rebuild and full SHA-verified Release). New recovery Run $GITHUB_RUN_ID revalidated original source-run Artifact byte-for-byte and independently rechecked normalized Image, config, ABI and Release SHA256. Does NOT claim new device testing.")"
NUM="$(basename "$URL")"
PR="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM")"
jq -e --arg h "$HEAD_SHA" --arg b "$BRANCH" \
 '.state=="open" and .draft==false and .base.ref=="dev" and .head.ref==$b and .head.sha==$h' <<<"$PR" >/dev/null
FILES="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM/files?per_page=100" --jq '.[].filename')"
[[ "$(wc -l <<<"$FILES")" -eq 2 ]] || exit 1
grep -Fxq "$CURRENT" <<<"$FILES"
grep -Fxq "$HISTORY" <<<"$FILES"
bash scripts/xiaomi-os4/await-pr-isolation.sh "$BRANCH" "$HEAD_SHA"
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || exit 1
for i in {1..12}; do
  MERGEABLE="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM" --jq .mergeable)"
  [[ "$MERGEABLE" != null ]] && break
  sleep 3
done
[[ "$MERGEABLE" == true ]] || exit 1
gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$NUM/merge" \
  -f merge_method=squash -f sha="$HEAD_SHA" \
  -f commit_title="xiaomi(os4): restore verified Gen $GEN / $BUILD" \
  | jq -e '.merged==true and (.sha|length)==40' >/dev/null
gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" >/dev/null || true
LIVE="$(gh api "repos/$GITHUB_REPOSITORY/contents/.github/config/ota-lkg-current.json?ref=dev" --jq .content | base64 -d)"
cmp -s <(printf '%s\n' "$LIVE") "$POINTER" || {
  echo "::error::merged LKG record changed; do not publish the draft"; exit 1;
}
# Publish by ID as well: tag-only lookups can remain 404 for drafts.
# This happens only after GitHub confirms the trusted LKG pointer merged.
gh api -X PATCH "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID" \
  -F draft=false -f make_latest=false > "$WORK/published-release.json"
jq -e --arg t "$TAG" --argjson id "$RELEASE_ID" '
  .id==$id and .tag_name==$t and .draft==false
' "$WORK/published-release.json" >/dev/null || {
  echo "::error::merged LKG pointer but draft publication not confirmed"; exit 1;
}
echo "LKG_VERIFIED_DRAFT_RECOVERY=PASS source=$SOURCE_RUN_ID original_promotion=$ORIGINAL_PROMOTION_RUN recovery_run=$GITHUB_RUN_ID generation=$GEN"
echo "Existing $TAG draft revalidated, Gen $GEN pointer merged; no redundant kernel rebuild. $URL" >> "$GITHUB_STEP_SUMMARY"
\t' read -r ASSET_ID ASSET_NAME ASSET_SHA ASSET_SIZE; do
  [[ "$ASSET_ID" =~ ^[1-9][0-9]*$ && "$ASSET_SIZE" =~ ^[1-9][0-9]*$ ]] || exit 1
  curl --fail --location --silent --show-error --retry 2 \
    --header "Authorization: Bearer $GH_TOKEN" \
    --header "Accept: application/octet-stream" \
    --output "$OUT/$ASSET_NAME" \
    "https://api.github.com/repos/$GITHUB_REPOSITORY/releases/assets/$ASSET_ID"
  [[ "$(stat -c%s "$OUT/$ASSET_NAME")" == "$ASSET_SIZE" ]] || {
    echo "::error::draft asset size differs from numeric Release metadata: $ASSET_NAME"; exit 1;
  }
  [[ "$(sha256sum "$OUT/$ASSET_NAME" | cut -d' ' -f1)" == "$ASSET_SHA" ]] || {
    echo "::error::draft asset SHA256 differs from numeric Release metadata: $ASSET_NAME"; exit 1;
  }
done < "$WORK/draft-assets.tsv"
python3 scripts/xiaomi-os4/verify-ota-lkg-release.py --dir "$OUT" --tag "$TAG"
POINTER="$OUT/ota-lkg-promotion-record.json"
ORIGINAL_PROMOTION_RUN="$(jq -er .promotion_run_id "$POINTER")"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID" > "$WORK/source-run.json"
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$ORIGINAL_PROMOTION_RUN" > "$WORK/promotion-run.json"
[[ "$(jq -r .head_sha "$WORK/source-run.json")" == "$SOURCE_SHA" ]] || exit 1
git merge-base --is-ancestor "$SOURCE_SHA" "$BASE_SHA" || exit 1
git merge-base --is-ancestor "$(jq -r .head_sha "$WORK/promotion-run.json")" "$BASE_SHA" || exit 1
tar -I zstd -xf "$OUT/$BUILD-Gen$GEN-original-evidence.tar.zst" -C "$SRC"
tar -I zstd -xf "$OUT/$BUILD-Gen$GEN-rebuilt-evidence.tar.zst" -C "$RES"
python3 scripts/xiaomi-os4/check-ota-lkg-recovery.py \
  --pointer "$CURRENT" --record "$POINTER" --release "$RELEASE_JSON" \
  --source-run "$WORK/source-run.json" --promotion-run "$WORK/promotion-run.json" \
  --source-manifest "$SRC/ota-custom-source.json" --source-dir "$SRC" --rebuild-dir "$RES"
cmp -s "$CURRENT" "$SRC/compat-custom-previous-lkg.json" || {
  echo "::error::trusted previous LKG has moved, refusing draft recovery"; exit 1;
}
python3 scripts/xiaomi-os4/cross-ota-lkg.py verify \
  --artifact-dir "$SRC" --run-id "$SOURCE_RUN_ID" --head-sha "$SOURCE_SHA"
python3 scripts/xiaomi-os4/cross-ota-lkg.py compare \
  --source-dir "$SRC" --rebuild-dir "$RES" --run-id "$SOURCE_RUN_ID" \
  --head-sha "$SOURCE_SHA" --output "$WORK/reverified-reproduction.json"
cmp -s "$WORK/reverified-reproduction.json" "$RES/reproduction-report.json" || {
  echo "::error::independent replay no longer matches the archived build proof"; exit 1;
}

# Do not blindly trust a self-consistent draft archive: independently retrieve
# the original immutable source-run artifact and compare all build-critical bytes.
ARTIFACT="pandora-OTA-COMPAT-CUSTOM-$BUILD-run-$SOURCE_RUN_ID"
ASSETS="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN_ID/artifacts?per_page=100")"
jq -e --arg name "$ARTIFACT" '
  [.artifacts[] | select(.expired==false and .name==$name)] | length==1
' <<<"$ASSETS" >/dev/null || {
  echo "::error::source Artifact expired/mismatched; do not trust archived copy"; exit 1;
}
gh run download "$SOURCE_RUN_ID" --name "$ARTIFACT" --dir "$FRESH"
for file in Image Module.symvers final.config build-metadata.txt \
            ota-custom-abi-report.json verified-baseline.json fixture.json locked-upstreams.env; do
  cmp -s "$SRC/$file" "$FRESH/$file" || {
    echo "::error::original Artifact differs from validated Release: $file"; exit 1;
  }
done
ORIG_BOOT="$(jq -er .boot_name "$SRC/ota-custom-source.json")"
ORIG_AK3="$(jq -er .anykernel_name "$SRC/ota-custom-source.json")"
cmp -s "$SRC/$ORIG_BOOT" "$FRESH/$ORIG_BOOT" || exit 1
cmp -s "$SRC/$ORIG_AK3" "$FRESH/$ORIG_AK3" || exit 1
[[ "$(sha256sum "$SRC/$ORIG_BOOT" | cut -d' ' -f1)" == "$(jq -r .boot_sha256 "$POINTER")" ]] || exit 1
[[ "$(sha256sum "$SRC/$ORIG_AK3" | cut -d' ' -f1)" == "$(jq -r .anykernel_sha256 "$POINTER")" ]] || exit 1
cmp -s "$SRC/$ORIG_BOOT" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-boot.img" || exit 1
cmp -s "$SRC/$ORIG_AK3" "$OUT/$BUILD-Gen$GEN-ORIGINAL-USER-ATTESTED-AnyKernel3.zip" || exit 1
[[ "$(sha256sum "$RES/REBUILT-boot.img" | cut -d' ' -f1)" == \
   "$(sha256sum "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-boot.img" | cut -d' ' -f1)" ]] || exit 1
[[ "$(unzip -p "$OUT/$BUILD-Gen$GEN-REBUILT-CI-ONLY-AnyKernel3.zip" Image | sha256sum | cut -d' ' -f1)" == \
   "$(sha256sum "$RES/Image" | cut -d' ' -f1)" ]] || exit 1
STOCK="$(gh api "repos/$GITHUB_REPOSITORY/releases/tags/pandora-os4-stock-input")"
ASSET="$(jq -r '[.assets[] | select(.name | endswith("xm.zip"))] | if length==1 then .[0].id else empty end' <<<"$STOCK")"
[[ "$ASSET" == "$(jq -er .stock_release_asset_id "$POINTER")" ]] || exit 1
[[ "$(jq -er .build .github/config/ota-development-current.json)" == "$BUILD" ]] || exit 1
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || {
  echo "::error::dev moved while validating draft; leave existing draft untouched"; exit 1;
}
HISTORY=".github/config/ota-lkg-history/gen$((GEN-1)).json"
[[ ! -e "$HISTORY" ]] || { echo "::error::LKG history would be overwritten"; exit 1; }
mkdir -p "$(dirname "$HISTORY")"
cp "$CURRENT" "$HISTORY"
cp "$POINTER" "$CURRENT"
BRANCH="ota/lkg-gen$GEN-recovered-run$GITHUB_RUN_ID"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch -c "$BRANCH"
git add "$CURRENT" "$HISTORY"
[[ "$(git diff --cached --name-only | wc -l)" -eq 2 ]] || exit 1
git commit -m "xiaomi(os4): recover verified LKG Gen $GEN / $BUILD"
bash scripts/xiaomi-os4/check-upstream-isolation.sh "$BASE_SHA" --committed
git push origin "$BRANCH"
HEAD_SHA="$(git rev-parse HEAD)"
URL="$(gh pr create --base dev --head "$BRANCH" \
  --title "xiaomi(os4): recover SHA-verified Gen $GEN / $BUILD" \
  --body "Recover completed $TAG evidence from original failed promotion Run $ORIGINAL_PROMOTION_RUN (dev advanced only after independent rebuild and full SHA-verified Release). New recovery Run $GITHUB_RUN_ID revalidated original source-run Artifact byte-for-byte and independently rechecked normalized Image, config, ABI and Release SHA256. Does NOT claim new device testing.")"
NUM="$(basename "$URL")"
PR="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM")"
jq -e --arg h "$HEAD_SHA" --arg b "$BRANCH" \
 '.state=="open" and .draft==false and .base.ref=="dev" and .head.ref==$b and .head.sha==$h' <<<"$PR" >/dev/null
FILES="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM/files?per_page=100" --jq '.[].filename')"
[[ "$(wc -l <<<"$FILES")" -eq 2 ]] || exit 1
grep -Fxq "$CURRENT" <<<"$FILES"
grep -Fxq "$HISTORY" <<<"$FILES"
bash scripts/xiaomi-os4/await-pr-isolation.sh "$BRANCH" "$HEAD_SHA"
[[ "$(gh api "repos/$GITHUB_REPOSITORY/branches/dev" --jq .commit.sha)" == "$BASE_SHA" ]] || exit 1
for i in {1..12}; do
  MERGEABLE="$(gh api "repos/$GITHUB_REPOSITORY/pulls/$NUM" --jq .mergeable)"
  [[ "$MERGEABLE" != null ]] && break
  sleep 3
done
[[ "$MERGEABLE" == true ]] || exit 1
gh api -X PUT "repos/$GITHUB_REPOSITORY/pulls/$NUM/merge" \
  -f merge_method=squash -f sha="$HEAD_SHA" \
  -f commit_title="xiaomi(os4): restore verified Gen $GEN / $BUILD" \
  | jq -e '.merged==true and (.sha|length)==40' >/dev/null
gh api -X DELETE "repos/$GITHUB_REPOSITORY/git/refs/heads/$BRANCH" >/dev/null || true
LIVE="$(gh api "repos/$GITHUB_REPOSITORY/contents/.github/config/ota-lkg-current.json?ref=dev" --jq .content | base64 -d)"
cmp -s <(printf '%s\n' "$LIVE") "$POINTER" || {
  echo "::error::merged LKG record changed; do not publish the draft"; exit 1;
}
gh release edit "$TAG" --draft=false --latest=false
[[ "$(gh release view "$TAG" --json isDraft --jq .isDraft)" == false ]] || exit 1
echo "LKG_VERIFIED_DRAFT_RECOVERY=PASS source=$SOURCE_RUN_ID original_promotion=$ORIGINAL_PROMOTION_RUN recovery_run=$GITHUB_RUN_ID generation=$GEN"
echo "Existing $TAG draft revalidated, Gen $GEN pointer merged; no redundant kernel rebuild. $URL" >> "$GITHUB_STEP_SUMMARY"
