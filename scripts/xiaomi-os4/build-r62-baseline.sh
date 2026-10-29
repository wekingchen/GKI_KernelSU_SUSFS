#!/usr/bin/env bash
set -euo pipefail

# Official GKI R62 kernel-only baseline. Never package for flashing.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"
STAGE="$RUNNER_TEMP/xiaomi-os4-build"
SRC="$STAGE/common"
OUT="$STAGE/out"
RESULT="$STAGE/results"
CACHE_ROOT="$HOME/.cache/xiaomi-os4"
GIT_CACHE="$CACHE_ROOT/common-r62.git"
TOOL_CACHE="$CACHE_ROOT/toolchain-r536225"
mkdir -p "$STAGE" "$RESULT" "$CACHE_ROOT"

echo "[OS4] 仅用于兼容性分析，严禁刷机。目标为 $OS4_KERNEL_VERSION / $OS4_STOCK_KMI"
[[ "$OS4_DEVICE" == pandora && "$OS4_KERNEL_VERSION" == 6.12.69 ]] || exit 1

if [[ ! -d "$GIT_CACHE" ]] || ! git --git-dir="$GIT_CACHE" cat-file -e "$OS4_GKI_COMMON_COMMIT^{commit}" 2>/dev/null; then
  rm -rf "$GIT_CACHE"
  git init -q --bare "$GIT_CACHE"
  git --git-dir="$GIT_CACHE" remote add origin "$OS4_GKI_COMMON_URL"
  git --git-dir="$GIT_CACHE" fetch --depth=1 --no-tags origin "refs/tags/$OS4_GKI_TAG"
  actual="$(git --git-dir="$GIT_CACHE" rev-parse 'FETCH_HEAD^{commit}')"
  [[ "$actual" == "$OS4_GKI_COMMON_COMMIT" ]] || { echo "::error::R62 GKI commit drift: $actual"; exit 1; }
  git --git-dir="$GIT_CACHE" update-ref refs/heads/pinned "$actual"
fi
if [[ ! -d "$SRC/.git" ]]; then
  git clone -q --no-checkout "$GIT_CACHE" "$SRC"
fi
git -C "$SRC" checkout -q --detach "$OS4_GKI_COMMON_COMMIT"
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$OS4_GKI_COMMON_COMMIT" ]] || exit 1
make_ver="$(awk '/^VERSION = /{v=$3} /^PATCHLEVEL = /{p=$3} /^SUBLEVEL = /{s=$3} END {print v"."p"."s}' "$SRC/Makefile")"
[[ "$make_ver" == "$OS4_KERNEL_VERSION" ]] || { echo "::error::unexpected Makefile version $make_ver"; exit 1; }
[[ "$(sed -n 's/^KMI_GENERATION=//p' "$SRC/build.config.constants")" == "$OS4_KMI_GENERATION" ]] || exit 1
[[ "$(sed -n 's/^CLANG_VERSION=//p' "$SRC/build.config.constants")" == "$OS4_GKI_EXPECTED_CLANG" ]] || exit 1

TOOL_BASE="https://github.com/cctv18/oneplus_sm8650_toolchain/releases/download/LLVM-Clang19-r536225"
if [[ ! -x "$TOOL_CACHE/clang19/bin/clang" || ! -x "$TOOL_CACHE/rust/bin/rustc" || ! -x "$TOOL_CACHE/build-tools/bin/pahole" || ! -f "$TOOL_CACHE/.verified" ]]; then
  rm -rf "$TOOL_CACHE"
  mkdir -p "$TOOL_CACHE/clang19" "$TOOL_CACHE/rust"
  curl -fL --retry 5 --retry-all-errors --connect-timeout 30 "$TOOL_BASE/clang-r536225.zip" -o "$TOOL_CACHE/clang.zip"
  curl -fL --retry 5 --retry-all-errors --connect-timeout 30 "$TOOL_BASE/rust.zip" -o "$TOOL_CACHE/rust.zip"
  curl -fL --retry 5 --retry-all-errors --connect-timeout 30 "$TOOL_BASE/build-tools.zip" -o "$TOOL_CACHE/build-tools.zip"
  (
    cd "$TOOL_CACHE"
    printf '%s  %s\n' '574ef505fa9222c24bb75a9c6592fd62ca546bd86267f73b5533ec38a239f0ea' clang.zip | sha256sum -c -
    printf '%s  %s\n' '4adf5f226cd4ac4840f454955b52b07e99a198a859efe635194e89e7c35c3f41' rust.zip | sha256sum -c -
    printf '%s  %s\n' '821babb745321981222d0cb42af5c1214e4efc908b159ae82dbd8113d978c7dd' build-tools.zip | sha256sum -c -
    unzip -q clang.zip -d clang19
    unzip -q rust.zip -d rust
    unzip -q build-tools.zip
    rm clang.zip rust.zip build-tools.zip
    printf 'r536225\n' > .verified
  )
fi
export PATH="$TOOL_CACHE/clang19/bin:$TOOL_CACHE/build-tools/bin:$TOOL_CACHE/rust/bin:$PATH"
export RUSTC=rustc BINDGEN=bindgen LIBCLANG_PATH="$TOOL_CACHE/clang19/lib"
# Preserve compiler output across experimental CI runs; Rust expects CC as one executable.
CLANG_CC=clang
if command -v ccache >/dev/null 2>&1; then
  export CCACHE_DIR="$HOME/.cache/xiaomi-os4/ccache-r62"
  export CCACHE_COMPILERCHECK="string:android-r536225"
  export CCACHE_BASEDIR="$STAGE"
  mkdir -p "$CCACHE_DIR" "$STAGE/.compiler"
  ccache --max-size=3G >/dev/null
  cat > "$STAGE/.compiler/clang" <<'CC_WRAPPER'
#!/usr/bin/env bash
exec ccache clang "$@"
CC_WRAPPER
  chmod +x "$STAGE/.compiler/clang"
  CLANG_CC="$STAGE/.compiler/clang"
  ccache --show-stats || true
fi
export CC="$CLANG_CC" HOSTCC="$CLANG_CC" LD=ld.lld HOSTLD=ld.lld
export LLVM=1 LLVM_IAS=1 ARCH=arm64 SUBARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_GENDWARFKSYMS_STABLE=1
export LOCALVERSION=""
# Make repeated builds from the same pinned source/config byte-reproducible.
# GitHub runner hostnames and wall-clock time otherwise change UTS_VERSION and
# therefore the final Image hash even when KMI and Module.symvers are identical.
SOURCE_DATE_EPOCH="$(git -C "$SRC" show -s --format=%ct "$OS4_GKI_COMMON_COMMIT")"
export SOURCE_DATE_EPOCH
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %d %T UTC %Y')"
export KBUILD_BUILD_USER="android-build"
export KBUILD_BUILD_HOST="pandora-r62-ci"
export KBUILD_BUILD_VERSION=1
export AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy STRIP=llvm-strip
# Build official R62 with upstream flags: Gold's 6.12.23 KCFLAGS (notably
# -fmacro-prefix-map) fail when R62 compiles Rust kernel objects with -Werror.
# Baseline must reflect official GKI Kconfig/compiler semantics, not Gold hacks.
unset KCFLAGS
echo "[OS4] 工具链: $(clang --version | head -n1) / $(rustc --version)"
[[ "$(clang --version | head -n1)" == *"clang version 19.0.1"* ]] || { echo "::error::incorrect Clang"; exit 1; }

BUILD_JOBS="${XIAOMI_OS4_JOBS:-$(nproc)}"
(( BUILD_JOBS >= 1 && BUILD_JOBS <= 8 )) || { echo "::error::Invalid build jobs: $BUILD_JOBS"; exit 1; }
echo "[OS4] 编译线程 $BUILD_JOBS，ccache 编译器 $CLANG_CC"
mkdir -p "$OUT"
make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" gki_defconfig > "$RESULT/config-build.log" 2>&1 || {
  tail -n 100 "$RESULT/config-build.log"; exit 1;
}
# Experimental kernel identity must never masquerade as the Xiaomi OEM release.
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION "-android16-6-os4r62-analysis-4k"
"$SRC/scripts/config" --file "$OUT/.config" --disable LOCALVERSION_AUTO
make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" olddefconfig >> "$RESULT/config-build.log" 2>&1 || {
  tail -n 100 "$RESULT/config-build.log"; exit 1;
}
cp "$OUT/.config" "$RESULT/final.config"
grep -qx 'CONFIG_MODVERSIONS=y' "$OUT/.config" || { echo "::error::baseline requires MODVERSIONS"; exit 1; }
grep -qx '# CONFIG_CGROUP_PIDS is not set' "$OUT/.config" || {
  echo "::error::unexpected PIDs feature in baseline"; exit 1;
}
echo "[OS4] Starting official GKI R62 baseline Image (no BakaSU/SUSFS/NoMount)"
start="$(date +%s)"
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 \
  CC="$CLANG_CC" HOSTCC="$CLANG_CC" -j"$BUILD_JOBS" Image > "$RESULT/kernel-build.log" 2>&1; then
  echo "::error::R62 baseline Image failed; last 120 lines:"
  tail -n 120 "$RESULT/kernel-build.log"
  exit 1
fi
image_elapsed="$(( $(date +%s) - start ))"
[[ -s "$OUT/arch/arm64/boot/Image" ]] || { echo "::error::Image missing"; exit 1; }
[[ -s "$OUT/vmlinux" ]] || { echo "::error::vmlinux missing"; exit 1; }
[[ -s "$OUT/vmlinux.symvers" ]] || { echo "::error::vmlinux.symvers missing"; exit 1; }
# Image completes before Module.symvers is created. Keep verified outputs
# even if the subsequent module build fails, but do not label them flashable.
cp "$OUT/arch/arm64/boot/Image" "$RESULT/Image"
cp "$OUT/vmlinux.symvers" "$RESULT/vmlinux.symvers"
echo "[OS4] Image 完成（$image_elapsed 秒），开始内核模块构建以生成真正 Module.symvers"
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 \
  CC="$CLANG_CC" HOSTCC="$CLANG_CC" -j"$BUILD_JOBS" modules > "$RESULT/modules-build.log" 2>&1; then
  echo "::error::R62 modules build failed; last 120 lines:"
  tail -n 120 "$RESULT/modules-build.log"
  exit 1
fi
elapsed="$(( $(date +%s) - start ))"
[[ -s "$OUT/Module.symvers" ]] || { echo "::error::Module.symvers still missing after modules build"; exit 1; }
cp "$OUT/Module.symvers" "$RESULT/Module.symvers"
RUST_BINDER="$OUT/drivers/android/binder/rust_binder.ko"
[[ -s "$RUST_BINDER" ]] || { echo "::error::R62 rust_binder.ko missing after modules build"; exit 1; }
cp "$RUST_BINDER" "$RESULT/rust_binder-R62.ko"
{
  echo "sha256=$(sha256sum "$RUST_BINDER" | cut -d ' ' -f1)"
  echo "module=$(basename "$RUST_BINDER")"
  echo "kernelrelease=$(make --no-print-directory -s -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 kernelrelease)"
  echo "undefined-symbols=$(llvm-nm -u "$RUST_BINDER" | wc -l)"
  echo "version-ext-names=$(llvm-readelf -S "$RUST_BINDER" | grep -c '__version_ext_names' || true)"
  echo "version-ext-crcs=$(llvm-readelf -S "$RUST_BINDER" | grep -c '__version_ext_crcs' || true)"
} > "$RESULT/rust-binder-R62-metadata.txt"
zstd -T2 -q -6 -f "$OUT/vmlinux" -o "$RESULT/vmlinux.zst"
{
  echo "STOCK_RELEASE=$OS4_STOCK_KERNEL_RELEASE"
  echo "SOURCE_COMMIT=$OS4_GKI_COMMON_COMMIT"
  echo "KMI_GENERATION=$OS4_KMI_GENERATION"
  echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
  echo "KBUILD_BUILD_TIMESTAMP=$KBUILD_BUILD_TIMESTAMP"
  echo "KBUILD_BUILD_USER=$KBUILD_BUILD_USER"
  echo "KBUILD_BUILD_HOST=$KBUILD_BUILD_HOST"
  echo "KBUILD_BUILD_VERSION=$KBUILD_BUILD_VERSION"
  echo "BUILD_KIND=R62_UNMODIFIED_GKI_BASELINE"
  echo "FLASHABLE=NO"
  echo "IMAGE_BUILD_SECONDS=$image_elapsed"
  echo "IMAGE_AND_MODULES_BUILD_SECONDS=$elapsed"
  echo "SYMVERS_FROM=make_modules"
  echo "KERNEL_RELEASE=$(make --no-print-directory -s -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 kernelrelease)"
  echo "IMAGE_SHA256=$(sha256sum "$RESULT/Image" | cut -d ' ' -f1)"
  echo "SYMVERS_SHA256=$(sha256sum "$RESULT/Module.symvers" | cut -d ' ' -f1)"
  echo "SYMVERS_LINES=$(wc -l < "$RESULT/Module.symvers")"
  echo "VMLINUX_SYMVERS_LINES=$(wc -l < "$RESULT/vmlinux.symvers")"
} > "$RESULT/build-metadata.txt"
cat "$RESULT/build-metadata.txt"
echo "[OS4] R62 baseline Image/Symvers built; NOT flashable, no AnyKernel3."
