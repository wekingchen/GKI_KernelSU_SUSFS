#!/usr/bin/env bash
# Long-term, fail-closed archive of the USER-PROMOTED OS4 current LKG.
# No flash, no LKG promotion, no source change, no overwrite of Release assets.
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${REPRO_RUN_ID:?REPRO_RUN_ID is required}"
[[ "$GITHUB_REPOSITORY" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 2
[[ "$REPRO_RUN_ID" =~ ^[0-9]+$ ]] || { echo "::error::Invalid reproduction run ID"; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
source .github/config/pandora-os4-full-parity-lkg.env
[[ "$LKG_DEVICE" == "pandora" && "$LKG_SYSTEM_BUILD" == "OS4.0.5.0.XBLCNXM" ]] || exit 2
[[ "$LKG_PROMOTION_GENERATION" =~ ^[1-9][0-9]*$ && "$LKG_SOURCE_RUN_ID" =~ ^[0-9]+$ ]] || exit 2
for proof in LKG_FASTBOOT_BOOT_VALIDATION LKG_PERSISTENT_BOOT_VALIDATION LKG_REBUILD_REAL_DEVICE_VALIDATION; do
  [[ "${!proof:-}" == "PASS" ]] || { echo "::error::LKG missing actual device validation: $proof"; exit 1; }
done
[[ "$LKG_ROOT_MODE" == "bakasu-susfs" && "$LKG_FULL_PARITY" == "YES" ]] || {
  echo "::error::This archivist requires validated Full Parity BakaSU"; exit 1;
}
TAG="pandora-os4-lkg-gen${LKG_PROMOTION_GENERATION}"
export GH_REPO="$GITHUB_REPOSITORY"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC="$WORK/original"; REPRO="$WORK/reproduced"; MANAGER="$WORK/manager"; OUT="$WORK/release"
mkdir -p "$SRC" "$REPRO" "$MANAGER" "$OUT"

require_run() {
  local id="$1" workflow="$2" identity_sha="${3:-}"
  local info
  info="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$id")"
  jq -e --arg path "$workflow" --arg sha "$identity_sha" '
    .status == "completed" and .conclusion == "success"
    and .head_branch == "dev" and .path == $path
    and ($sha == "" or .head_sha == $sha)
  ' <<<"$info" >/dev/null || {
    echo "::error::Untrusted workflow run: $id ($workflow)"; exit 1;
  }
}
require_sha() {
  local path="$1" want="$2" got
  [[ -s "$path" && "$want" =~ ^[a-f0-9]{64}$ ]] || { echo "::error::Missing file/hash: $path"; exit 1; }
  got="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$got" == "$want" ]] || { echo "::error::SHA256 mismatch: $path"; exit 1; }
}
field() {
  local file="$1" key="$2"
  grep -m1 "^$key=" "$file" | cut -d= -f2-
}
require_line() {
  grep -Fxq -- "$2" "$1" || { echo "::error::Metadata mismatch: $1 : $2"; exit 1; }
}
safe_name() {
  [[ "$1" =~ ^[a-zA-Z0-9_.-]+$ && "$1" != .* && "$1" != *..* ]] || {
    echo "::error::Unsafe file name: $1"; exit 1;
  }
}

require_run "$LKG_SOURCE_RUN_ID" ".github/workflows/xiaomi-sm8850-os4-custom.yml" "$LKG_SOURCE_RUN_HEAD"
require_run "$REPRO_RUN_ID" ".github/workflows/xiaomi-sm8850-os4-lkg.yml"
gh run download "$LKG_SOURCE_RUN_ID" --name "pandora-OS4-R62-CUSTOM-run-$LKG_SOURCE_RUN_ID" --dir "$SRC"
gh run download "$LKG_SOURCE_RUN_ID" --name "BakaSU-Manager-pandora-OS4-run-$LKG_SOURCE_RUN_ID" --dir "$MANAGER"
gh run download "$REPRO_RUN_ID" --name "pandora-OS4.0.5.0-R62-CURRENT-LKG" --dir "$REPRO"

for file in "$SRC/selection-manifest.txt" "$SRC/SHA256SUMS.txt" "$SRC/build-metadata.txt"             "$REPRO/current-lkg.env" "$REPRO/SHA256SUMS.txt" "$REPRO/LKG-REPRODUCTION.txt"             "$MANAGER/manager-metadata.txt" "$MANAGER/MANAGER-SHA256SUMS.txt"; do
  [[ -s "$file" ]] || { echo "::error::Artifact missing $file"; exit 1; }
done
(cd "$SRC" && sha256sum -c SHA256SUMS.txt)
(cd "$REPRO" && sha256sum -c SHA256SUMS.txt)
(cd "$MANAGER" && sha256sum -c MANAGER-SHA256SUMS.txt)
cmp -s "$REPRO/current-lkg.env" .github/config/pandora-os4-full-parity-lkg.env || {
  echo "::error::Reproduction was not built for exact current LKG generation"; exit 1;
}

require_sha "$SRC/Image" "$LKG_IMAGE_SHA256"
require_sha "$SRC/Module.symvers" "$LKG_SYMVERS_SHA256"
require_sha "$SRC/final.config" "$LKG_FINAL_CONFIG_SHA256"
require_line "$SRC/selection-manifest.txt" "DEVICE=$LKG_DEVICE"
require_line "$SRC/selection-manifest.txt" "SYSTEM_BUILD=$LKG_SYSTEM_BUILD"
require_line "$SRC/selection-manifest.txt" "KERNEL_RELEASE=$LKG_KERNEL_RELEASE"
require_line "$SRC/selection-manifest.txt" "UPSTREAM_SET_SHA256=$LKG_UPSTREAM_SET_SHA256"
require_line "$SRC/selection-manifest.txt" "BAKASU_MAIN_COMMIT=$LKG_BAKASU_COMMIT"
require_line "$SRC/selection-manifest.txt" "LKG_NORMALIZED_EQUIVALENCE=PASS"
require_line "$SRC/build-metadata.txt" "BAKASU_COMMIT=$LKG_BAKASU_COMMIT"
require_line "$SRC/selection-manifest.txt" "ANYKERNEL3_SHA256=$LKG_PACKAGE_SHA256"
require_line "$REPRO/LKG-REPRODUCTION.txt" "PROMOTION_GENERATION=$LKG_PROMOTION_GENERATION"
require_line "$REPRO/LKG-REPRODUCTION.txt" "SOURCE_RUN_ID=$LKG_SOURCE_RUN_ID"
require_line "$REPRO/LKG-REPRODUCTION.txt" "KERNEL_RELEASE=$LKG_KERNEL_RELEASE"

SRC_BOOT="$(field "$SRC/selection-manifest.txt" FASTBOOT_BOOT)"
SRC_AK3="$(field "$SRC/selection-manifest.txt" ANYKERNEL3)"
safe_name "$SRC_BOOT"; safe_name "$SRC_AK3"
[[ "$SRC_AK3" == "$LKG_PACKAGE_NAME" ]] || exit 1
require_sha "$SRC/$SRC_BOOT" "$LKG_FASTBOOT_BOOT_SHA256"
require_sha "$SRC/$SRC_AK3" "$LKG_PACKAGE_SHA256"
unzip -tqq "$SRC/$SRC_AK3" || { echo "::error::Source AnyKernel3 ZIP damaged"; exit 1; }

require_sha "$REPRO/Module.symvers" "$LKG_SYMVERS_SHA256"
require_sha "$REPRO/final.config" "$LKG_FINAL_CONFIG_SHA256"
python3 scripts/xiaomi-os4/verify-lkg-image-equivalence.py "$REPRO/Image" \
  --expected-size "$LKG_IMAGE_SIZE" \
  --build-id-payload-offset "$LKG_IMAGE_BUILD_ID_PAYLOAD_OFFSET" \
  --cert-offset "$LKG_IMAGE_MODULE_CERT_OFFSET" \
  --cert-length "$LKG_IMAGE_MODULE_CERT_LENGTH" \
  --expected-normalized-sha256 "$LKG_IMAGE_NORMALIZED_SHA256"
REPRO_BOOT="pandora-OS4-R62-CURRENT-LKG-FASTBOOT-BOOT-ONLY.img"
REPRO_AK3="Xiaomi17Pro-pandora-OS4.0.5.0-R62-CURRENT-LKG-AnyKernel3.zip"
[[ -s "$REPRO/$REPRO_BOOT" && -s "$REPRO/$REPRO_AK3" ]] || exit 1
require_line "$REPRO/LKG-REPRODUCTION.txt" "REBUILT_IMAGE_SHA256=$(sha256sum "$REPRO/Image" | awk '{print $1}')"
require_line "$REPRO/LKG-REPRODUCTION.txt" "REBUILT_FASTBOOT_BOOT_SHA256=$(sha256sum "$REPRO/$REPRO_BOOT" | awk '{print $1}')"
unzip -tqq "$REPRO/$REPRO_AK3" || { echo "::error::Reproduction ZIP damaged"; exit 1; }

require_line "$MANAGER/manager-metadata.txt" "BAKASU_TARGET_COMMIT=$LKG_BAKASU_COMMIT"
require_line "$MANAGER/manager-metadata.txt" "MANAGER_HEAD_SHA=$LKG_BAKASU_COMMIT"
require_line "$MANAGER/manager-metadata.txt" "BAKASU_VALIDATED_REFERENCE=$LKG_BAKASU_COMMIT"
mapfile -t APKS < <(find "$MANAGER" -maxdepth 1 -type f -name '*-arm64-v8a-release.apk' -printf '%f\n' | sort)
(( ${#APKS[@]} > 0 )) || { echo "::error::No validated Manager APK"; exit 1; }

# Names explicitly distinguish the user-validated ORIGINAL from a CI-REBUILT equivalent.
PREFIX="Xiaomi17Pro-pandora-OS4-Gen${LKG_PROMOTION_GENERATION}"
cp "$SRC/$SRC_AK3" "$OUT/$PREFIX-ORIGINAL-USER-VERIFIED-AnyKernel3.zip"
cp "$SRC/$SRC_BOOT" "$OUT/$PREFIX-ORIGINAL-USER-VERIFIED-fastboot-boot.img"
cp "$REPRO/$REPRO_AK3" "$OUT/$PREFIX-REBUILT-CI-VERIFIED-AnyKernel3.zip"
cp "$REPRO/$REPRO_BOOT" "$OUT/$PREFIX-REBUILT-CI-VERIFIED-fastboot-boot.img"
for apk in "${APKS[@]}"; do cp "$MANAGER/$apk" "$OUT/$PREFIX-$apk"; done

# Complete evidence packages preserve all source metadata independent of expiring Artifacts.
tar -I 'zstd -T2 -6' -cf "$OUT/$PREFIX-ORIGINAL-evidence.tar.zst" -C "$SRC" .
tar -I 'zstd -T2 -6' -cf "$OUT/$PREFIX-REBUILT-evidence.tar.zst" -C "$REPRO" .
tar -I 'zstd -T2 -6' -cf "$OUT/$PREFIX-MANAGER-evidence.tar.zst" -C "$MANAGER" .
cp .github/config/pandora-os4-full-parity-lkg.env "$OUT/$PREFIX-locked-lkg.env"

cat > "$OUT/README-RECOVERY.md" <<EOF
# Xiaomi 17 Pro OS4 LKG generation $LKG_PROMOTION_GENERATION

Device: $LKG_DEVICE
HyperOS: $LKG_SYSTEM_BUILD
Kernel: $LKG_KERNEL_RELEASE
User-confirmed source run: $LKG_SOURCE_RUN_ID
CI-reproduced run: $REPRO_RUN_ID
BakaSU exact commit: $LKG_BAKASU_COMMIT
Full upstream set SHA256: $LKG_UPSTREAM_SET_SHA256

**ORIGINAL-USER-VERIFIED** files are byte-identical copies from the original
user-promoted run, whose original filename contained UNVERIFIED *before*
real-device confirmation and Gen $LKG_PROMOTION_GENERATION promotion.
**REBUILT-CI-VERIFIED** files were freshly rebuilt with exact locked inputs
and passed the repository's normalized Image / KMI / configuration checks.
They have **not** been separately flashed to a device.
Manager APKs originate from the same exact BakaSU commit as the source kernel.

Compare files against SHA256SUMS-$TAG.txt prior to use.
Original source Image: $LKG_IMAGE_SHA256
Original source fastboot boot: $LKG_FASTBOOT_BOOT_SHA256
Original source AnyKernel3: $LKG_PACKAGE_SHA256
Normalized kernel Image: $LKG_IMAGE_NORMALIZED_SHA256

Do not flash this on a different HyperOS/OTA/kernel/boot layout.
Keep your known-bootable stock/backup boot image for recovery.
EOF
(
  cd "$OUT"
  find . -maxdepth 1 -type f ! -name "SHA256SUMS-$TAG.txt" -printf '%f\0' \
    | LC_ALL=C sort -z | xargs -0 sha256sum > "SHA256SUMS-$TAG.txt"
  sha256sum -c "SHA256SUMS-$TAG.txt"
)
cat > "$WORK/release-notes.md" <<EOF
# Xiaomi 17 Pro / pandora / OS4 · LKG Gen $LKG_PROMOTION_GENERATION

**真机确认稳定的原始 Gen $LKG_PROMOTION_GENERATION**，以及对应的 **CI 严格复现版本**，作为不依赖 30 天 Actions Artifact 的长期归档。

- 系统：$LKG_SYSTEM_BUILD
- 内核：$LKG_KERNEL_RELEASE
- 真机已验证来源：[Run $LKG_SOURCE_RUN_ID](https://github.com/$GITHUB_REPOSITORY/actions/runs/$LKG_SOURCE_RUN_ID)
- 复现校验通过：[Run $REPRO_RUN_ID](https://github.com/$GITHUB_REPOSITORY/actions/runs/$REPRO_RUN_ID)
- Manager 与内核 BakaSU 提交一致：\`$LKG_BAKASU_COMMIT\`

优先使用 \`ORIGINAL-USER-VERIFIED\` 文件恢复已验证版本。
\`REBUILT-CI-VERIFIED\` 仅代表构建及归一化一致性校验通过，**不是再次真机刷入验证**。
其他文件包含独立 SHA256 校验单、已锁定的 LKG 配置、ABI/KMI 与构建元数据。
此 Release 不会随 Actions Artifact 30 天到期自动清理，但仍需防范仓库/Release 人工删除、GitHub 服务风险；建议额外离线备份。
EOF

# Never clobber an existing release asset. A partially uploaded DRAFT can be resumed.
if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" --title "Xiaomi 17 Pro OS4 · Gen $LKG_PROMOTION_GENERATION verified LKG" \
    --notes-file "$WORK/release-notes.md" --target "$(git rev-parse HEAD)" \
    --draft --latest=false
fi
for file in "$OUT"/*; do
  name="$(basename "$file")"
  if gh release view "$TAG" --json assets --jq '.assets[].name' | grep -Fxq "$name"; then
    echo "Existing asset: $name (will independently verify download)"
  else
    gh release upload "$TAG" "$file"
  fi
done
# Independently download all assets from the Release service; not local assumptions.
VERIFY="$WORK/verify"
mkdir -p "$VERIFY"
gh release download "$TAG" --dir "$VERIFY"
cmp -s "$OUT/SHA256SUMS-$TAG.txt" "$VERIFY/SHA256SUMS-$TAG.txt" || {
  echo "::error::Release checksum manifest mismatch"; exit 1;
}
(cd "$VERIFY" && sha256sum -c "SHA256SUMS-$TAG.txt")
gh release edit "$TAG" --draft=false --latest=false
[[ "$(gh release view "$TAG" --json isDraft --jq '.isDraft')" == "false" ]] || exit 1
echo "RELEASE_ARCHIVE=PASS"
echo "RELEASE_URL=https://github.com/$GITHUB_REPOSITORY/releases/tag/$TAG"
echo "ORIGINAL_SHA256=$LKG_PACKAGE_SHA256"
echo "REBUILT_RUN_ID=$REPRO_RUN_ID"
