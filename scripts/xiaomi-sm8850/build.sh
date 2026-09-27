#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

DEVICE="${1:?usage: build.sh <device> <variant> <workdir>}"
VARIANT="${2:?usage: build.sh <device> <variant> <workdir>}"
WORKDIR="${3:?usage: build.sh <device> <variant> <workdir>}"

validate_device "$DEVICE"
validate_variant "$VARIANT"

OUT="$WORKDIR/output/$DEVICE/$VARIANT"
mkdir -p "$OUT"

"$XIAOMI_SCRIPT_DIR/prepare-source.sh" "$WORKDIR"
KERNEL_ROOT="$WORKDIR/kernel"
FRAGMENT="$KERNEL_ROOT/common/arch/arm64/configs/xiaomi_sm8850.fragment"
: > "$FRAGMENT"

case "$VARIANT" in
  base)
    note "Variant A: stock-compatible public ACK base; no root integration"
    ;;
  resukisu)
    note "Variant B: ACK base + ReSukiSU built-in (tracepoint)"
    "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" tracepoint "$FRAGMENT"
    ;;
  resukisu-susfs)
    note "Variant C: ACK base + ReSukiSU built-in + SUSFS"
    "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" susfs "$FRAGMENT"
    "$XIAOMI_SCRIPT_DIR/integrate-susfs.sh" "$KERNEL_ROOT" "$FRAGMENT"
    ;;
esac

cd "$KERNEL_ROOT"

clang_bin="$KERNEL_ROOT/prebuilts/clang/host/linux-x86/clang-$CLANG_VERSION/bin/clang"
[[ -x "$clang_bin" ]] || die "pinned clang not found: $clang_bin"
clang_line="$("$clang_bin" --version | head -n1)"
note "toolchain: $clang_line"

# Recheck that this lane did not inherit the generic workflow's ABI bypasses.
python3 - common/BUILD.bazel <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
i=s.find('name = "kernel_aarch64"')
if i < 0:
    raise SystemExit("kernel_aarch64 target missing")
chunk=s[i:i+7000]
for required in ("kmi_enforced = True", "kmi_symbol_list_strict_mode = True", "trim_nonlisted_kmi = True"):
    if required not in chunk:
        raise SystemExit(f"KMI guardrail disabled: {required}")
PY

frag_flag=()
if [[ -s "$FRAGMENT" ]]; then
  note "defconfig fragment:"
  cat "$FRAGMENT"
  frag_flag=("--defconfig_fragment=//common:arch/arm64/configs/xiaomi_sm8850.fragment")
fi

note "building //common:kernel_aarch64_dist with standard thin LTO and KMI checks intact"
tools/bazel build   --config=fast   --lto=thin   "${frag_flag[@]}"   //common:kernel_aarch64_dist

IMAGE="$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image"
[[ -s "$IMAGE" ]] || die "built Image not found: $IMAGE"
cp -f "$IMAGE" "$OUT/Image"
if [[ -s "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" ]]; then
  cp -f "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" "$OUT/Image.lz4"
fi

# Validate the configuration embedded in the actual Image, not just the input
# fragment. GKI enables IKCONFIG, so inability to extract it is a build failure.
"$KERNEL_ROOT/common/scripts/extract-ikconfig" "$OUT/Image" > "$OUT/final.config"
[[ -s "$OUT/final.config" ]] || die "failed to extract final config from Image"

kernel_string="$(strings -a "$OUT/Image" | grep -m1 '^Linux version ' || true)"
[[ -n "$kernel_string" ]] || die "Linux version string not found in Image"

resukisu_actual="N/A"
susfs_actual="N/A"
[[ -d "$KERNEL_ROOT/ReSukiSU/.git" ]] && resukisu_actual="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-parse HEAD)"
[[ -d "$KERNEL_ROOT/SUSFS/.git" ]] && susfs_actual="$(git -C "$KERNEL_ROOT/SUSFS" rev-parse HEAD)"

cat > "$OUT/build-metadata.txt" <<EOF
device=$DEVICE
device_name=$(device_marketing_name "$DEVICE")
variant=$VARIANT
android_version=$ANDROID_VERSION
kernel_expected=$KERNEL_VERSION
stock_reference=$EXPECTED_STOCK_RELEASE
ack_manifest_commit=$(git -C "$KERNEL_ROOT/.repo/manifests" rev-parse HEAD)
ack_common_ref=$ACK_COMMON_REF
ack_common_commit=$(git -C "$KERNEL_ROOT/common" rev-parse HEAD)
kmi_generation=$KMI_GENERATION
clang_revision=$CLANG_VERSION
clang_version=$clang_line
resukisu_commit=$resukisu_actual
susfs_commit=$susfs_actual
kernel_string=$kernel_string
build_target=//common:kernel_aarch64_dist
lto=thin
kmi_enforced=true
kmi_symbol_list_strict_mode=true
EOF

"$XIAOMI_SCRIPT_DIR/validate.sh" "$DEVICE" "$VARIANT" "$WORKDIR"
"$XIAOMI_SCRIPT_DIR/package-anykernel3.sh" "$DEVICE" "$VARIANT" "$WORKDIR"

sha256sum "$OUT/Image" "$OUT"/*.zip > "$OUT/SHA256SUMS"
note "build complete: $OUT"
