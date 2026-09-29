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
PROVENANCE="$WORKDIR/source-provenance.env"

[[ -s "$IMAGE" ]] || die "Image missing"
[[ -s "$FINAL" ]] || die "final.config missing"
[[ -s "$PROVENANCE" ]] || die "source provenance missing"
# shellcheck disable=SC1090
source "$PROVENANCE"
validate_source_profile "$SOURCE_PROFILE"

kernel_string="$(strings -a "$IMAGE" | grep -m1 '^Linux version ' || true)"
kernel_release="$(awk '{print $3}' <<<"$kernel_string")"
[[ "$kernel_string" == *"Linux version $KERNEL_VERSION-android16-5"* ]] ||
  die "unexpected kernel release: $kernel_string"
[[ "$kernel_string" == *"-4k"* ]] ||
  die "kernel release does not advertise 4K suffix: $kernel_string"

for key in CONFIG_ARM64 CONFIG_MODVERSIONS CONFIG_GENDWARFKSYMS CONFIG_CFI_CLANG; do
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
    for key in CONFIG_KSU_SUSFS_SUS_PATH CONFIG_KSU_SUSFS_SUS_MOUNT CONFIG_KSU_SUSFS_SUS_KSTAT CONFIG_KSU_SUSFS_ENABLE_LOG; do
      config_is_y "$FINAL" "$key" || die "Variant C missing $key"
    done
    if [[ "${XIAOMI_SUSFS_EXTRA_FEATURES:-false}" == "true" ]]; then
      for key in CONFIG_KSU_SUSFS_SPOOF_UNAME CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG CONFIG_KSU_SUSFS_OPEN_REDIRECT CONFIG_KSU_SUSFS_SUS_MAP; do
        config_is_y "$FINAL" "$key" || die "SUSFS extra features requested but missing $key"
      done
    else
      for key in CONFIG_KSU_SUSFS_SPOOF_UNAME CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG CONFIG_KSU_SUSFS_OPEN_REDIRECT CONFIG_KSU_SUSFS_SUS_MAP; do
        config_is_not_y "$FINAL" "$key" || die "Variant C unexpectedly enables optional SUSFS feature $key"
      done
    fi
    ;;
esac

truthy_feature() {
  case "${1,,}" in
    true|1|yes|on|enabled|"enabled (开启)") return 0 ;;
    *) return 1 ;;
  esac
}

if truthy_feature "${XIAOMI_USE_KPM:-disabled}"; then
  config_is_y "$FINAL" CONFIG_KPM || die "KPM requested but final Image lacks CONFIG_KPM=y"
fi
if truthy_feature "${XIAOMI_USE_ZRAM:-false}"; then
  config_is_y "$FINAL" CONFIG_ZRAM || die "ZRAM requested but CONFIG_ZRAM=y is missing"
  config_is_y "$FINAL" CONFIG_ZSMALLOC || die "ZRAM requested but CONFIG_ZSMALLOC=y is missing"
fi
if truthy_feature "${XIAOMI_USE_BBG:-false}"; then
  config_is_y "$FINAL" CONFIG_BBG || die "BBG requested but CONFIG_BBG=y is missing"
fi
if truthy_feature "${XIAOMI_USE_REKERNEL:-false}"; then
  config_is_y "$FINAL" CONFIG_REKERNEL || die "Re-Kernel requested but CONFIG_REKERNEL=y is missing"
  config_is_y "$FINAL" CONFIG_REKERNEL_NETWORK || die "Re-Kernel networking requested but config is missing"
fi
if truthy_feature "${XIAOMI_USE_NOMOUNT:-false}"; then
  config_is_y "$FINAL" CONFIG_NOMOUNT || die "NoMount requested but CONFIG_NOMOUNT=y is missing"
fi
if [[ "${XIAOMI_DROIDSPACES:-off}" != "off" ]]; then
  for key in CONFIG_SYSVIPC CONFIG_POSIX_MQUEUE CONFIG_IPC_NS CONFIG_PID_NS CONFIG_DEVTMPFS CONFIG_USER_NS; do
    config_is_y "$FINAL" "$key" || die "DroidSpaces requested but final Image lacks $key"
  done
fi
if truthy_feature "${XIAOMI_DROIDSPACES_NTSYNC:-false}"; then
  config_is_y "$FINAL" CONFIG_NTSYNC || die "NTSync requested but CONFIG_NTSYNC=y is missing"
fi
if truthy_feature "${XIAOMI_USE_NETWORKING:-false}"; then
  config_is_y "$FINAL" CONFIG_TCP_CONG_BBR || die "networking requested but CONFIG_TCP_CONG_BBR=y is missing"
  config_is_y "$FINAL" CONFIG_IP_SET || die "networking requested but CONFIG_IP_SET=y is missing"
  config_is_y "$FINAL" CONFIG_CIFS || die "networking requested but CONFIG_CIFS=y is missing"
fi
if truthy_feature "${XIAOMI_CVE_2026_43499_PATCH:-false}"; then
  grep -q 'struct task_struct \*waiter_task = waiter->task;' "$KERNEL_ROOT/common/kernel/locking/rtmutex.c" ||
    die "CVE patch requested but rtmutex fix marker is missing"
fi

actual_common="$(git -C "$KERNEL_ROOT/common" rev-parse HEAD)"
[[ "$actual_common" == "$SOURCE_COMMON_COMMIT" ]] ||
  die "kernel source commit drifted: expected $SOURCE_COMMON_COMMIT got $actual_common"

ack_kmi="$(sed -n 's/^KMI_GENERATION=//p' "$KERNEL_ROOT/common/build.config.constants")"
ack_clang="$(sed -n 's/^CLANG_VERSION=//p' "$KERNEL_ROOT/common/build.config.constants")"
[[ "$ack_kmi" == "$KMI_GENERATION" ]] || die "KMI generation mismatch: $ack_kmi"
[[ "$ack_clang" == "$CLANG_VERSION" ]] || die "clang revision mismatch: $ack_clang"

case "$SOURCE_BUILD_MODE" in
  make-image)
    [[ "$SOURCE_PROFILE" == "gold-cctv" ]] ||
      die "make-image mode is only expected for gold-cctv"
    grep -qx "CONFIG_LOCALVERSION=\"$GOLD_KERNEL_LOCALVERSION\"" "$FINAL" ||
      die "Gold Image localversion is not deterministic"
    expected_gold_release="$KERNEL_VERSION$GOLD_KERNEL_LOCALVERSION"
    [[ "$kernel_release" == "$expected_gold_release" ]] ||
      die "Gold kernel release mismatch: expected $expected_gold_release got $kernel_release"
    config_is_not_y "$FINAL" CONFIG_LOCALVERSION_AUTO ||
      die "Gold make path unexpectedly enables CONFIG_LOCALVERSION_AUTO"
    config_is_not_y "$FINAL" CONFIG_MODULE_SCMVERSION ||
      die "Gold make path unexpectedly enables CONFIG_MODULE_SCMVERSION"
    [[ "$SOURCE_KMI_SOURCE_MODE" == "$GOLD_KMI_MODE" && "$SOURCE_KMI_MODE" == "$GOLD_KMI_MODE" ]] ||
      die "Gold KMI provenance mismatch: source=$SOURCE_KMI_SOURCE_MODE final=$SOURCE_KMI_MODE"
    kmi_guardrail_report="make-image: MODVERSIONS+GENDWARFKSYMS; deterministic localversion; MODULE_SCMVERSION intentionally off"
    ;;
  kleaf-dist)
    [[ "$SOURCE_PROFILE" == "ack-r51" ]] ||
      die "kleaf-dist mode is only expected for ack-r51"
    [[ "$kernel_release" != *"maybe-dirty"* ]] ||
      die "ACK release still contains Kleaf maybe-dirty placeholder: $kernel_release"
    [[ "$SOURCE_KMI_SOURCE_MODE" == "$ACK_SOURCE_KMI_MODE" ]] ||
      die "ACK source KMI provenance mismatch: $SOURCE_KMI_SOURCE_MODE"
    [[ "$SOURCE_KMI_MODE" == "$ACK_XIAOMI_KMI_MODE" ]] ||
      die "ACK final KMI provenance mismatch: $SOURCE_KMI_MODE"

    # Xiaomi ACK compatibility intentionally relaxes the source GKI KMI policy
    # to the real-device-validated trimming/protected-module behavior. Validate
    # both the Bazel target policy and the embedded final config so the policy
    # cannot silently drift.
    python3 - "$KERNEL_ROOT/common/BUILD.bazel" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
start=s.find('common_kernel(\n    name = "kernel_aarch64",')
if start < 0:
    raise SystemExit("kernel_aarch64 target missing")
end=s.find("\n)\n", start)
if end < 0:
    raise SystemExit("kernel_aarch64 target end missing")
chunk=s[start:end+3]

for required in (
    "kmi_enforced = False",
    "kmi_symbol_list_strict_mode = False",
    "trim_nonlisted_kmi = False",
):
    if required not in chunk:
        raise SystemExit(f"Xiaomi ACK compatibility policy missing: {required}")

for forbidden in (
    "kmi_enforced = True",
    "kmi_symbol_list_strict_mode = True",
    "trim_nonlisted_kmi = True",
    'kmi_symbol_list = "gki/aarch64/symbols/base"',
    'protected_module_names_list = ":gki_aarch64_protected_module_names"',
):
    if forbidden in chunk:
        raise SystemExit(f"Xiaomi ACK compatibility policy unexpectedly retains: {forbidden}")
PY

    config_is_not_y "$FINAL" CONFIG_TRIM_UNUSED_KSYMS ||
      die "ACK Xiaomi compatibility unexpectedly enables CONFIG_TRIM_UNUSED_KSYMS"
    config_is_not_y "$FINAL" CONFIG_MODULE_SIG_PROTECT ||
      die "ACK Xiaomi compatibility unexpectedly enables CONFIG_MODULE_SIG_PROTECT"
    grep -q '^CONFIG_UNUSED_KSYMS_WHITELIST=' "$FINAL" &&
      die "ACK Xiaomi compatibility unexpectedly retains CONFIG_UNUSED_KSYMS_WHITELIST"
    module_sig_protect_list="$(sed -n 's/^CONFIG_MODULE_SIG_PROTECT_LIST=//p' "$FINAL")"
    if [[ -n "$module_sig_protect_list" && "$module_sig_protect_list" != '""' ]]; then
      die "ACK Xiaomi compatibility unexpectedly retains a non-empty CONFIG_MODULE_SIG_PROTECT_LIST"
    fi

    # Keep SCMVERSION unchanged; Xiaomi compatibility only changes the
    # trimming/protected-module policy.
    config_is_y "$FINAL" CONFIG_MODULE_SCMVERSION ||
      die "ACK Xiaomi compatibility unexpectedly disables CONFIG_MODULE_SCMVERSION"

    kmi_guardrail_report="kleaf-xiaomi-compat: trimming/protected-module policy disabled; MODULE_SCMVERSION retained"
    ;;
  *)
    die "unknown source build mode: $SOURCE_BUILD_MODE"
    ;;
esac

if find "$KERNEL_ROOT/common" -type f -name '*.rej' -print -quit | grep -q .; then
  find "$KERNEL_ROOT/common" -type f -name '*.rej' -print >&2
  die "patch reject files remain"
fi

{
  echo "PASS"
  echo "device=$DEVICE"
  echo "variant=$VARIANT"
  echo "source_profile=$SOURCE_PROFILE"
  echo "source_build_mode=$SOURCE_BUILD_MODE"
  echo "source_kmi_source_mode=$SOURCE_KMI_SOURCE_MODE"
  echo "source_kmi_mode=$SOURCE_KMI_MODE"
  echo "source_common_repo=$SOURCE_COMMON_REPO"
  echo "source_common_ref=$SOURCE_COMMON_REF"
  echo "source_common_commit=$SOURCE_COMMON_COMMIT"
  echo "arch=arm64"
  echo "android_branch=android16-6.12"
  echo "kernel_version=$KERNEL_VERSION"
  echo "kmi_generation=$KMI_GENERATION"
  echo "page_size=4K"
  echo "modversions=y"
  echo "gendwarfksyms=y"
  if config_is_y "$FINAL" CONFIG_MODULE_SCMVERSION; then
    echo "module_scmversion=y"
  else
    echo "module_scmversion=n"
  fi
  echo "kmi_guardrails=$kmi_guardrail_report"
  echo "kernel_release=$kernel_release"
  echo "kernel_string=$kernel_string"
  if [[ "$VARIANT" != base ]]; then
    echo "resukisu_builtin=y"
  fi
  if [[ "$VARIANT" == resukisu-susfs ]]; then
    echo "susfs=y"
    echo "susfs_extra_features=${XIAOMI_SUSFS_EXTRA_FEATURES:-false}"
  fi
  echo "feature_use_zram=${XIAOMI_USE_ZRAM:-false}"
  echo "feature_use_bbg=${XIAOMI_USE_BBG:-false}"
  echo "feature_use_kpm=${XIAOMI_USE_KPM:-disabled}"
  echo "feature_use_rekernel=${XIAOMI_USE_REKERNEL:-false}"
  echo "feature_use_nomount=${XIAOMI_USE_NOMOUNT:-false}"
  echo "feature_use_networking=${XIAOMI_USE_NETWORKING:-false}"
  echo "feature_cve_2026_43499_patch=${XIAOMI_CVE_2026_43499_PATCH:-false}"
  echo "feature_droidspaces=${XIAOMI_DROIDSPACES:-off}"
  echo "feature_droidspaces_ntsync=${XIAOMI_DROIDSPACES_NTSYNC:-false}"
} | tee "$REPORT"
