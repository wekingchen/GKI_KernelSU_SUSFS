#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KERNEL_ROOT="${1:?usage: build-gold-make.sh <kernel-root> <fragment> <out-dir>}"
FRAGMENT="${2:?usage: build-gold-make.sh <kernel-root> <fragment> <out-dir>}"
OUT="${3:?usage: build-gold-make.sh <kernel-root> <fragment> <out-dir>}"

COMMON="$KERNEL_ROOT/common"
TOOLROOT="$KERNEL_ROOT/gold-toolchain"
CLANG_BIN="$TOOLROOT/clang19/bin"
RUST_BIN="$TOOLROOT/rust/bin"
BUILD_TOOLS_BIN="$TOOLROOT/build-tools/bin"
KOUT="$COMMON/out"

[[ -x "$CLANG_BIN/clang" ]] || die "Gold clang not found"
[[ -x "$RUST_BIN/rustc" ]] || die "Gold rustc not found"
[[ -x "$RUST_BIN/bindgen" ]] || die "Gold bindgen not found"
[[ -x "$COMMON/scripts/config" ]] || die "kernel scripts/config missing"

export PATH="$CLANG_BIN:$BUILD_TOOLS_BIN:$RUST_BIN:$PATH"
export RUSTC=rustc
export BINDGEN=bindgen
export CC=clang
export HOSTCC=clang
export LD=ld.lld
export HOSTLD=ld.lld
export LLVM=1
export LLVM_IAS=1
export ARCH=arm64
export SUBARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
export AR=llvm-ar
export NM=llvm-nm
export AS=clang
export READELF=llvm-readelf
export OBJCOPY=llvm-objcopy
export OBJDUMP=llvm-objdump
export OBJSIZE=llvm-size
export STRIP=llvm-strip
export LIBCLANG_PATH="$TOOLROOT/clang19/lib"
export KBUILD_GENDWARFKSYMS_STABLE=1

cd "$COMMON"

# Match the compatibility-sensitive flags used by the public cctv18 6.12.23
# make/Image workflow. In particular, remap absolute paths because 6.12 uses
# gendwarfksyms for symbol-version generation.
COMMON_REAL_PATH="$(pwd -P)"
ROOT_REAL_PATH="$(dirname "$COMMON_REAL_PATH")"
KCFLAGS=" -fdebug-prefix-map=$ROOT_REAL_PATH=."
KCFLAGS+=" -fmacro-prefix-map=$ROOT_REAL_PATH=."
KCFLAGS+=" -ffile-prefix-map=$ROOT_REAL_PATH=."
KCFLAGS+=" -no-canonical-prefixes"
KCFLAGS+=" -O2"
KCFLAGS+=" -pipe"
KCFLAGS+=" -Wno-error"
KCFLAGS+=" -fno-stack-protector"
KCFLAGS+=" -D__ANDROID_COMMON_KERNEL__"
export KCFLAGS

note "Gold make path toolchain:"
clang --version | head -n1
ld.lld --version | head -n1
rustc -V
bindgen --version

rm -rf "$KOUT"

make -j"$(nproc)" \
  LLVM=1 ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CC=clang LD=ld.lld OBJCOPY=llvm-objcopy \
  O=out gki_defconfig

# cctv18 packages use a deterministic custom kernel suffix. Do the same rather
# than allowing the runner checkout state ("dirty", branch movement, etc.) to
# leak into uname -r.
"$COMMON/scripts/config" --file "$KOUT/.config" \
  --set-str LOCALVERSION "$GOLD_KERNEL_LOCALVERSION"
"$COMMON/scripts/config" --file "$KOUT/.config" --disable LOCALVERSION_AUTO

# Apply only the diagnostic ReSukiSU/SUSFS fragment after gki_defconfig.
# The Xiaomi lane currently emits bool/tristate y and explicit "not set" lines.
if [[ -s "$FRAGMENT" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ "$line" =~ ^CONFIG_([A-Z0-9_]+)=y$ ]]; then
      "$COMMON/scripts/config" --file "$KOUT/.config" --enable "${BASH_REMATCH[1]}"
    elif [[ "$line" =~ ^#\ CONFIG_([A-Z0-9_]+)\ is\ not\ set$ ]]; then
      "$COMMON/scripts/config" --file "$KOUT/.config" --disable "${BASH_REMATCH[1]}"
    else
      die "unsupported Gold config fragment line: $line"
    fi
  done < "$FRAGMENT"
fi

make -j"$(nproc)" \
  LLVM=1 ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CC=clang LD=ld.lld OBJCOPY=llvm-objcopy \
  O=out olddefconfig

note "Gold make path: building Image only (no Kleaf dist/module-output enforcement)"
make -j"$(nproc)" \
  LLVM=1 ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  CC=clang LD=ld.lld OBJCOPY=llvm-objcopy \
  O=out Image

IMAGE="$KOUT/arch/arm64/boot/Image"
[[ -s "$IMAGE" ]] || die "Gold make Image not found: $IMAGE"
cp -f "$IMAGE" "$OUT/Image"
cp -f "$KOUT/.config" "$OUT/final.config"

note "Gold make Image ready: $OUT/Image"
