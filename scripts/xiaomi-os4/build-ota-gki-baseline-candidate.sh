#!/usr/bin/env bash
# Build an exploratory, NON-FLASHABLE pure GKI candidate for a new pandora OTA.
set -euo pipefail
[[ -n "$OTA_CANDIDATE_ENV" && -n "$RUNNER_TEMP" ]] || exit 2
source "$OTA_CANDIDATE_ENV"
[[ "$OTA_BUILD" =~ ^OS[0-9]+\.[0-9.]+[A-Z0-9]+$ ]] || exit 2
[[ "$OTA_KERNEL_VERSION" =~ ^6\.12\.[0-9]+$ && "$OTA_KMI" == "android16-6" ]] || exit 2
[[ "$OTA_GKI_TAG" =~ ^android16-6\.12-[0-9]{4}-[0-9]{2}_r[1-9][0-9]*$ ]] || exit 2
[[ "$OTA_GKI_COMMIT" =~ ^[0-9a-f]{40}$ && "$OTA_INPUT_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ "$OTA_SELECTION_REASON" == "EXACT_OFFICIAL_GKI_BUILD_ID" || "$OTA_SELECTION_REASON" == "SAME_PATCH_LATEST_OFFICIAL_GKI_CANDIDATE" ]] || exit 2
STAGE="$RUNNER_TEMP/ota-candidate"
SRC="$STAGE/common"
OUT="$STAGE/out"
RESULT="$STAGE/results"
TOOL_CACHE="$HOME/.cache/xiaomi-os4/toolchain-r536225"
GIT_CACHE="$HOME/.cache/xiaomi-os4/ota-$OTA_GKI_COMMIT.git"
mkdir -p "$STAGE" "$RESULT" "$(dirname "$GIT_CACHE")"
cp "$OTA_CANDIDATE_ENV" "$RESULT/locked-candidate.env"
printf 'OTA_GKI_CANDIDATE=UNVERIFIED\nFLASHABLE=NO\nDEVICE=pandora\nBUILD=%s\n' "$OTA_BUILD" > "$RESULT/STATUS.txt"
echo "::notice::No boot, no AnyKernel3, no OEM ABI compatibility claim and no LKG promotion."
if [[ ! -d "$GIT_CACHE" ]] || ! git --git-dir="$GIT_CACHE" cat-file -e "$OTA_GKI_COMMIT^{commit}" 2>/dev/null; then
  rm -rf "$GIT_CACHE"
  git init -q --bare "$GIT_CACHE"
  git --git-dir="$GIT_CACHE" remote add origin "https://android.googlesource.com/kernel/common"
  git --git-dir="$GIT_CACHE" fetch -q --depth=1 --no-tags origin "refs/tags/$OTA_GKI_TAG"
  actual="$(git --git-dir="$GIT_CACHE" rev-parse 'FETCH_HEAD^{commit}')"
  [[ "$actual" == "$OTA_GKI_COMMIT" ]] || { echo "::error::GKI catalog commit does not match downloaded tag"; exit 1; }
  git --git-dir="$GIT_CACHE" update-ref refs/heads/ota "$actual"
fi
git clone -q --no-checkout "$GIT_CACHE" "$SRC"
git -C "$SRC" checkout -q --detach "$OTA_GKI_COMMIT"
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$OTA_GKI_COMMIT" ]] || exit 1
make_ver="$(awk '/^VERSION = /{v=$3} /^PATCHLEVEL = /{p=$3} /^SUBLEVEL = /{s=$3} END {print v"."p"."s}' "$SRC/Makefile")"
[[ "$make_ver" == "$OTA_KERNEL_VERSION" ]] || { echo "::error::GKI patch version drift: $make_ver"; exit 1; }
[[ "$(sed -n 's/^KMI_GENERATION=//p' "$SRC/build.config.constants")" == 6 ]] || {
  echo "::error::New KMI generation requires review"; exit 1;
}
required_clang="$(sed -n 's/^CLANG_VERSION=//p' "$SRC/build.config.constants")"
[[ "$required_clang" == "r536225" ]] || {
  echo "::error::GKI requires $required_clang, current validated toolchain is r536225; halt"; exit 1;
}
TOOL_BASE="https://github.com/cctv18/oneplus_sm8650_toolchain/releases/download/LLVM-Clang19-r536225"
if [[ ! -x "$TOOL_CACHE/clang19/bin/clang" || ! -x "$TOOL_CACHE/rust/bin/rustc" ||
      ! -x "$TOOL_CACHE/build-tools/bin/pahole" || ! -f "$TOOL_CACHE/.verified" ]]; then
  rm -rf "$TOOL_CACHE"
  mkdir -p "$TOOL_CACHE/clang19" "$TOOL_CACHE/rust"
  for f in clang-r536225.zip rust.zip build-tools.zip; do
    curl -fLsS --retry 3 "$TOOL_BASE/$f" -o "$TOOL_CACHE/$f"
  done
  (
    cd "$TOOL_CACHE"
    echo '574ef505fa9222c24bb75a9c6592fd62ca546bd86267f73b5533ec38a239f0ea  clang-r536225.zip' | sha256sum -c -
    echo '4adf5f226cd4ac4840f454955b52b07e99a198a859efe635194e89e7c35c3f41  rust.zip' | sha256sum -c -
    echo '821babb745321981222d0cb42af5c1214e4efc908b159ae82dbd8113d978c7dd  build-tools.zip' | sha256sum -c -
    unzip -q clang-r536225.zip -d clang19
    unzip -q rust.zip -d rust
    unzip -q build-tools.zip
    rm clang-r536225.zip rust.zip build-tools.zip
    printf 'r536225\n' > .verified
  )
fi
[[ "$(cat "$TOOL_CACHE/.verified")" == r536225 ]] || exit 1
export PATH="$TOOL_CACHE/clang19/bin:$TOOL_CACHE/build-tools/bin:$TOOL_CACHE/rust/bin:$PATH"
export RUSTC=rustc BINDGEN=bindgen LIBCLANG_PATH="$TOOL_CACHE/clang19/lib"
export ARCH=arm64 SUBARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang HOSTCC=clang LD=ld.lld HOSTLD=ld.lld
export CROSS_COMPILE=aarch64-linux-gnu- KBUILD_GENDWARFKSYMS_STABLE=1 LOCALVERSION=""
export AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy STRIP=llvm-strip
export KBUILD_BUILD_USER=android-build KBUILD_BUILD_HOST=ota-candidate-ci KBUILD_BUILD_VERSION=1
export SOURCE_DATE_EPOCH="$(git -C "$SRC" show -s --format=%ct "$OTA_GKI_COMMIT")"
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %d %T UTC %Y')"
unset KCFLAGS
[[ "$(clang --version | head -n1)" == *"clang version 19.0.1"* ]] || exit 1
BUILD_JOBS="$XIAOMI_OS4_JOBS"
[[ "$BUILD_JOBS" =~ ^[1-8]$ ]] || exit 2
mkdir -p "$OUT"
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" gki_defconfig > "$RESULT/config-build.log" 2>&1; then
  tail -n 60 "$RESULT/config-build.log"; exit 1
fi
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION "-android16-6-ota-candidate-4k"
"$SRC/scripts/config" --file "$OUT/.config" --disable LOCALVERSION_AUTO
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" olddefconfig >> "$RESULT/config-build.log" 2>&1; then
  tail -n 60 "$RESULT/config-build.log"; exit 1
fi
cp "$OUT/.config" "$RESULT/final.config"
grep -qx 'CONFIG_MODVERSIONS=y' "$OUT/.config" || exit 1
echo "::notice::Only building unmodified official GKI candidate Image and Module.symvers."
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" Image modules > "$RESULT/kernel-build.log" 2>&1; then
  echo "::error::Candidate build failed; showing last 100 lines only"
  tail -n 100 "$RESULT/kernel-build.log"; exit 1
fi
[[ -s "$OUT/arch/arm64/boot/Image" && -s "$OUT/Module.symvers" ]] || exit 1
cp "$OUT/arch/arm64/boot/Image" "$RESULT/Image"
cp "$OUT/Module.symvers" "$RESULT/Module.symvers"
{
  echo "BASELINE_KIND=UNMODIFIED_GKI_CANDIDATE_ONLY"
  echo "FLASHABLE=NO"
  echo "VENDOR_KMI_ABI_EQUIVALENCE=NOT_PROVEN"
  echo "STOCK_BUILD=$OTA_BUILD"
  echo "STOCK_KERNEL_VERSION=$OTA_KERNEL_VERSION"
  echo "STOCK_KMI=$OTA_KMI"
  echo "SOURCE_GKI_TAG=$OTA_GKI_TAG"
  echo "SOURCE_GKI_COMMIT=$OTA_GKI_COMMIT"
  echo "SOURCE_SELECTION=$OTA_SELECTION_REASON"
  echo "STOCK_INPUT_SHA256=$OTA_INPUT_SHA256"
  echo "KERNEL_RELEASE=$(make --no-print-directory -s -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 kernelrelease)"
  echo "IMAGE_SHA256=$(sha256sum "$RESULT/Image" | awk '{print $1}')"
  echo "SYMVERS_SHA256=$(sha256sum "$RESULT/Module.symvers" | awk '{print $1}')"
  echo "FASTBOOT_BOOT=NOT_BUILT"
  echo "ANYKERNEL3=NOT_BUILT"
  echo "LKG_PROMOTION=FORBIDDEN"
} > "$RESULT/build-metadata.txt"
(cd "$RESULT" && sha256sum Image Module.symvers final.config > SHA256SUMS.txt)
cat "$RESULT/build-metadata.txt"
echo "OTA_BASELINE_GKI_CANDIDATE=PASS_UNVERIFIED_NOT_FLASHABLE"
