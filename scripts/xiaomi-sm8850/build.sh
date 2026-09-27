#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

DEVICE="${1:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
VARIANT="${2:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
WORKDIR="${3:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
SOURCE_PROFILE="${4:-$DEFAULT_SOURCE_PROFILE}"

validate_device "$DEVICE"
validate_variant "$VARIANT"
validate_source_profile "$SOURCE_PROFILE"

OUT="$WORKDIR/output/$DEVICE/$VARIANT"
mkdir -p "$OUT"

bash "$XIAOMI_SCRIPT_DIR/prepare-source.sh" "$WORKDIR" "$SOURCE_PROFILE"
KERNEL_ROOT="$WORKDIR/kernel"
FRAGMENT="$KERNEL_ROOT/common/arch/arm64/configs/xiaomi_sm8850.fragment"
: > "$FRAGMENT"

case "$VARIANT" in
  base)
    note "Variant A: source=$SOURCE_PROFILE; no root integration"
    ;;
  resukisu)
    note "Variant B: source=$SOURCE_PROFILE + ReSukiSU built-in (tracepoint)"
    bash "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" tracepoint "$FRAGMENT"
    ;;
  resukisu-susfs)
    note "Variant C: source=$SOURCE_PROFILE + ReSukiSU built-in + SUSFS"
    bash "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" susfs "$FRAGMENT"
    bash "$XIAOMI_SCRIPT_DIR/integrate-susfs.sh" "$KERNEL_ROOT" "$FRAGMENT"
    ;;
esac

# shellcheck disable=SC1090
source "$WORKDIR/source-provenance.env"

case "$SOURCE_BUILD_MODE" in
  make-image)
    clang_bin="$KERNEL_ROOT/gold-toolchain/clang19/bin/clang"
    [[ -x "$clang_bin" ]] || die "pinned Gold clang not found: $clang_bin"
    clang_line="$("$clang_bin" --version | head -n1)"

    note "building Gold-compatible profile with standalone make/Image path"
    bash "$XIAOMI_SCRIPT_DIR/build-gold-make.sh" "$KERNEL_ROOT" "$FRAGMENT" "$OUT"

    build_target="make O=out gki_defconfig + Image"
    lto_mode="source-default (not forced by Kleaf)"
    kmi_enforced="not-applicable (Image-only make path)"
    kmi_strict="not-applicable (Image-only make path)"
    ;;

  kleaf-dist)
    cd "$KERNEL_ROOT"
    clang_bin="$KERNEL_ROOT/prebuilts/clang/host/linux-x86/clang-$CLANG_VERSION/bin/clang"
    [[ -x "$clang_bin" ]] || die "pinned ACK clang not found: $clang_bin"
    clang_line="$("$clang_bin" --version | head -n1)"
    note "toolchain: $clang_line"

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

      cat >> common/BUILD.bazel <<'EOF'
exports_files(
    ["arch/arm64/configs/xiaomi_sm8850.fragment"],
    visibility = ["//visibility:public"],
)
EOF
      frag_flag=("--defconfig_fragment=//common:arch/arm64/configs/xiaomi_sm8850.fragment")
    fi

    note "building ACK control with //common:kernel_aarch64_dist + ThinLTO + strict KMI"
    tools/bazel build \
      --config=fast \
      --lto=thin \
      "${frag_flag[@]}" \
      //common:kernel_aarch64_dist

    IMAGE="$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image"
    [[ -s "$IMAGE" ]] || die "built Image not found: $IMAGE"
    cp -f "$IMAGE" "$OUT/Image"
    if [[ -s "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" ]]; then
      cp -f "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" "$OUT/Image.lz4"
    fi

    build_target="//common:kernel_aarch64_dist"
    lto_mode="thin"
    kmi_enforced="true"
    kmi_strict="true"
    ;;

  *)
    die "unknown build mode from provenance: $SOURCE_BUILD_MODE"
    ;;
esac

IMAGE="$OUT/Image"
[[ -s "$IMAGE" ]] || die "Image missing after build"

"$KERNEL_ROOT/common/scripts/extract-ikconfig" "$IMAGE" > "$OUT/final.config.embedded"
[[ -s "$OUT/final.config.embedded" ]] ||
  die "failed to extract embedded config from final Image"
mv -f "$OUT/final.config.embedded" "$OUT/final.config"

kernel_string="$(strings -a "$IMAGE" | grep -m1 '^Linux version ' || true)"
[[ -n "$kernel_string" ]] || die "Linux version string not found in Image"

resukisu_ref="${XIAOMI_RESUKISU_REF:-$RESUKISU_DEFAULT_REF}"
resukisu_actual="N/A"
resukisu_tag="N/A"
resukisu_version_code="N/A"
susfs_actual="N/A"
if [[ -d "$KERNEL_ROOT/ReSukiSU/.git" ]]; then
  resukisu_actual="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-parse HEAD)"
  resukisu_tag="$(git -C "$KERNEL_ROOT/ReSukiSU" describe --abbrev=0 --tags 2>/dev/null || echo v4.1.0)"
  resukisu_commit_count="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-list --count HEAD)"
  resukisu_version_code="$((30000 + resukisu_commit_count + 700))"
fi
[[ -d "$KERNEL_ROOT/SUSFS/.git" ]] && susfs_actual="$(git -C "$KERNEL_ROOT/SUSFS" rev-parse HEAD)"

cat > "$OUT/build-metadata.txt" <<EOF
device=$DEVICE
device_name=$(device_marketing_name "$DEVICE")
variant=$VARIANT
source_profile=$SOURCE_PROFILE
source_build_mode=$SOURCE_BUILD_MODE
source_kmi_mode=$SOURCE_KMI_MODE
android_version=$ANDROID_VERSION
kernel_expected=$KERNEL_VERSION
stock_reference=$EXPECTED_STOCK_RELEASE
manifest_commit=$SOURCE_MANIFEST_COMMIT
source_common_repo=$SOURCE_COMMON_REPO
source_common_ref=$SOURCE_COMMON_REF
source_common_commit=$SOURCE_COMMON_COMMIT
kmi_generation=$KMI_GENERATION
clang_revision=$CLANG_VERSION
clang_version=$clang_line
resukisu_requested_ref=$resukisu_ref
resukisu_commit=$resukisu_actual
resukisu_tag=$resukisu_tag
resukisu_version_code=$resukisu_version_code
resukisu_last_known_good_commit=$RESUKISU_LAST_KNOWN_GOOD_COMMIT
susfs_commit=$susfs_actual
kernel_string=$kernel_string
build_target=$build_target
lto=$lto_mode
kmi_enforced=$kmi_enforced
kmi_symbol_list_strict_mode=$kmi_strict
EOF

bash "$XIAOMI_SCRIPT_DIR/validate.sh" "$DEVICE" "$VARIANT" "$WORKDIR"
bash "$XIAOMI_SCRIPT_DIR/package-anykernel3.sh" "$DEVICE" "$VARIANT" "$WORKDIR"

sha256sum "$OUT/Image" "$OUT"/*.zip > "$OUT/SHA256SUMS"
note "build complete: $OUT"
