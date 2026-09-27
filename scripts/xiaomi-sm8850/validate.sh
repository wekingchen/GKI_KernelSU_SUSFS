#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

DEVICE="${1:?usage: validate.sh <device> <variant> <workdir>}"
VARIANT="${2:?usage: validate.sh <device> <variant> <workdir>}"
WORKDIR="${3:?usage: validate.sh <device> <variant> <workdir>}"

validate_device "$DEVICE"
validate_variant "$VARIANT"

KERNEL_ROOT="$WORKDIR/kernel"
OUT="$WORKDIR/output/$DEVICE/$VARIANT"
IMAGE="$OUT/Image"
FINAL="$OUT/final.config"
REPORT="$OUT/validation.txt"

[[ -s "$IMAGE" ]] || die "Image missing"
[[ -s "$FINAL" ]] || die "final.config missing"

kernel_string="$(strings -a "$IMAGE" | grep -m1 '^Linux version ' || true)"
[[ "$kernel_string" == *"Linux version $KERNEL_VERSION-android16-5"* ]] ||
  die "unexpected kernel release: $kernel_string"
[[ "$kernel_string" == *"-4k"* ]] ||
  die "kernel release does not advertise 4K page-size suffix: $kernel_string"

for key in CONFIG_ARM64 CONFIG_MODVERSIONS CONFIG_GENDWARFKSYMS CONFIG_MODULE_SCMVERSION CONFIG_CFI_CLANG; do
  config_is_y "$FINAL" "$key" || die "$key is not enabled in final Image"
done

if ! config_is_y "$FINAL" CONFIG_ARM64_4K_PAGES && ! config_is_y "$FINAL" CONFIG_PAGE_SIZE_4KB; then
  die "final Image is not configured for 4K pages"
fi

case "$VARIANT" in
  base)
    config_is_not_y "$FINAL" CONFIG_KSU || die "Variant A unexpectedly contains CONFIG_KSU=y"
    ;;
  resukisu)
    config_is_y "$FINAL" CONFIG_KSU || die "Variant B missing CONFIG_KSU=y"
    config_is_y "$FINAL" CONFIG_KSU_TRACEPOINT_HOOK || die "Variant B missing tracepoint hook"
    config_is_not_y "$FINAL" CONFIG_KSU_SUSFS || die "Variant B unexpectedly enables SUSFS"
    ;;
  resukisu-susfs)
    config_is_y "$FINAL" CONFIG_KSU || die "Variant C missing CONFIG_KSU=y"
    config_is_y "$FINAL" CONFIG_KSU_SUSFS || die "Variant C missing CONFIG_KSU_SUSFS=y"
    for key in       CONFIG_KSU_SUSFS_SUS_PATH       CONFIG_KSU_SUSFS_SUS_MOUNT       CONFIG_KSU_SUSFS_SUS_KSTAT       CONFIG_KSU_SUSFS_SPOOF_UNAME       CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS       CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG       CONFIG_KSU_SUSFS_OPEN_REDIRECT       CONFIG_KSU_SUSFS_SUS_MAP
    do
      config_is_y "$FINAL" "$key" || die "Variant C missing $key"
    done
    ;;
esac

actual_common="$(git -C "$KERNEL_ROOT/common" rev-parse HEAD)"
[[ "$actual_common" == "$ACK_COMMON_COMMIT" ]] ||
  die "kernel source commit drifted: $actual_common"

ack_kmi="$(sed -n 's/^KMI_GENERATION=//p' "$KERNEL_ROOT/common/build.config.constants")"
ack_clang="$(sed -n 's/^CLANG_VERSION=//p' "$KERNEL_ROOT/common/build.config.constants")"
[[ "$ack_kmi" == "$KMI_GENERATION" ]] || die "KMI generation mismatch: $ack_kmi"
[[ "$ack_clang" == "$CLANG_VERSION" ]] || die "clang revision mismatch: $ack_clang"

python3 - "$KERNEL_ROOT/common/BUILD.bazel" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
i=s.find('name = "kernel_aarch64"')
if i < 0:
    raise SystemExit("kernel_aarch64 target missing")
chunk=s[i:i+7000]
for required in ("kmi_enforced = True", "kmi_symbol_list_strict_mode = True", "trim_nonlisted_kmi = True"):
    if required not in chunk:
        raise SystemExit(f"KMI guardrail missing after integration: {required}")
PY

if find "$KERNEL_ROOT/common" -type f -name '*.rej' -print -quit | grep -q .; then
  find "$KERNEL_ROOT/common" -type f -name '*.rej' -print >&2
  die "patch reject files remain"
fi

{
  echo "PASS"
  echo "device=$DEVICE"
  echo "variant=$VARIANT"
  echo "arch=arm64"
  echo "android_branch=android16-6.12"
  echo "kernel_version=$KERNEL_VERSION"
  echo "kmi_generation=$KMI_GENERATION"
  echo "page_size=4K"
  echo "modversions=y"
  echo "gendwarfksyms=y"
  echo "module_scmversion=y"
  echo "kmi_enforced=true"
  echo "kmi_symbol_list_strict_mode=true"
  echo "kernel_string=$kernel_string"
  if [[ "$VARIANT" != base ]]; then
    echo "resukisu_builtin=y"
  fi
  if [[ "$VARIANT" == resukisu-susfs ]]; then
    echo "susfs=y"
  fi
} | tee "$REPORT"
