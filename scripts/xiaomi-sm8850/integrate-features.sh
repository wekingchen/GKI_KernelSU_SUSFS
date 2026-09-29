#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KERNEL_ROOT="${1:?usage: integrate-features.sh <kernel-root> <fragment> <workdir>}"
FRAGMENT="${2:?usage: integrate-features.sh <kernel-root> <fragment> <workdir>}"
WORKDIR="${3:?usage: integrate-features.sh <kernel-root> <fragment> <workdir>}"
COMMON="$KERNEL_ROOT/common"
DEPS="$KERNEL_ROOT/.xiaomi-feature-deps"
PROVENANCE="$WORKDIR/feature-provenance.env"

[[ -d "$COMMON" ]] || die "common kernel tree not found"
[[ -f "$FRAGMENT" ]] || die "config fragment not found: $FRAGMENT"
mkdir -p "$DEPS"

USE_ZRAM="${XIAOMI_USE_ZRAM:-false}"
USE_BBG="${XIAOMI_USE_BBG:-false}"
USE_KPM="${XIAOMI_USE_KPM:-disabled}"
USE_REKERNEL="${XIAOMI_USE_REKERNEL:-false}"
USE_NOMOUNT="${XIAOMI_USE_NOMOUNT:-false}"
USE_NETWORKING="${XIAOMI_USE_NETWORKING:-false}"
USE_CVE="${XIAOMI_CVE_2026_43499_PATCH:-false}"
DROIDSPACES="${XIAOMI_DROIDSPACES:-off}"
DROIDSPACES_NTSYNC="${XIAOMI_DROIDSPACES_NTSYNC:-false}"

truthy() {
  case "${1,,}" in
    true|1|yes|on|enabled|"enabled (开启)") return 0 ;;
    *) return 1 ;;
  esac
}

config_defined() {
  local cfg="${1#CONFIG_}"
  grep -RqsE --include='Kconfig*' "^[[:space:]]*(menuconfig|config)[[:space:]]+${cfg}([[:space:]]|$)" "$COMMON"
}

enable_if_defined() {
  local cfg="$1"
  if config_defined "$cfg"; then
    append_config "$FRAGMENT" "$cfg=y"
  else
    note "feature config not defined by this kernel, skipping: $cfg"
  fi
}

apply_patch_strict() {
  local patch_file="$1"
  [[ -f "$patch_file" ]] || die "patch not found: $patch_file"
  (cd "$COMMON" && patch --batch --forward --dry-run -p1 < "$patch_file") ||
    die "patch dry-run failed: $patch_file"
  (cd "$COMMON" && patch --batch --forward --no-backup-if-mismatch -p1 < "$patch_file") ||
    die "patch apply failed: $patch_file"
}

checkout_feature_ref() {
  local repo="$1" ref="$2" dest="$3"
  [[ ! -e "$dest" ]] || die "feature checkout already exists: $dest"
  mkdir -p "$dest"
  git -C "$dest" init -q
  git -C "$dest" remote add origin "$repo"
  git -C "$dest" fetch --depth=1 --no-tags origin "$ref"
  git -C "$dest" checkout -q --detach FETCH_HEAD
}

zram_patch_ref="N/A"
zram_patch_commit="N/A"
nomount_ref="N/A"
nomount_commit="N/A"
droidspaces_ref="N/A"
droidspaces_commit="N/A"
ntsync_patch_ref="N/A"
ntsync_patch_commit="N/A"
bbg_ref="N/A"
bbg_commit="N/A"
rekernel_ref="N/A"
rekernel_commit="N/A"

if [[ "$USE_KPM" == patched* ]]; then
  die "KPM patched mode is intentionally unsupported on the Xiaomi SM8850 lane"
fi
if truthy "$USE_KPM"; then
  grep -RqsE '^[[:space:]]*config[[:space:]]+KPM([[:space:]]|$)'     "$KERNEL_ROOT/ReSukiSU/kernel" 2>/dev/null ||
    die "KPM requested but current ReSukiSU does not declare CONFIG_KPM"
  append_config "$FRAGMENT" "CONFIG_KPM=y"
  note "KPM enabled"
fi

if truthy "$USE_NOMOUNT"; then
  nomount_ref="${XIAOMI_NOMOUNT_REF:-$NOMOUNT_DEFAULT_REF}"
  note "integrating NoMount ref=$nomount_ref"
  checkout_feature_ref "$NOMOUNT_REPO" "$nomount_ref" "$COMMON/NoMount"
  nomount_commit="$(git -C "$COMMON/NoMount" rev-parse HEAD)"
  (
    cd "$COMMON"
    sh "$COMMON/NoMount/kernel/setup.sh" "$nomount_commit"
  )
  [[ "$(git -C "$COMMON/NoMount" rev-parse HEAD)" == "$nomount_commit" ]] ||
    die "NoMount checkout moved during setup"
  [[ -L "$COMMON/fs/nomount" ]] || die "NoMount integration did not create fs/nomount symlink"
  append_config "$FRAGMENT" "CONFIG_NOMOUNT=y"
  note "NoMount integrated ref=$nomount_ref commit=$nomount_commit"
fi

if [[ "$DROIDSPACES" != "off" ]]; then
  [[ "$DROIDSPACES" == "on" ]] || die "Xiaomi 6.12 supports DroidSpaces values: off/on"
  droidspaces_ref="${XIAOMI_DROIDSPACES_REF:-$DROIDSPACES_DEFAULT_REF}"
  note "integrating DroidSpaces 6.12 support ref=$droidspaces_ref"
  checkout_feature_ref "$DROIDSPACES_REPO" "$droidspaces_ref" "$DEPS/Droidspaces-OSS"
  droidspaces_commit="$(git -C "$DEPS/Droidspaces-OSS" rev-parse HEAD)"
  patch_file="$DEPS/Droidspaces-OSS/Documentation/resources/kernel-patches/GKI/kernel-6.12/001.GKI-6.12-or-above-fix_sysvipc_kabi.patch"
  apply_patch_strict "$patch_file"

  if [[ -f "$COMMON/ipc/msgutil.c" ]] && ! grep -qF 'EXPORT_SYMBOL(init_ipc_ns);' "$COMMON/ipc/msgutil.c"; then
    sed -i '/^struct msg_msgseg {/i EXPORT_SYMBOL(init_ipc_ns);' "$COMMON/ipc/msgutil.c"
  fi
  if [[ -f "$COMMON/ipc/namespace.c" ]] && ! grep -qF 'EXPORT_SYMBOL(put_ipc_ns);' "$COMMON/ipc/namespace.c"; then
    sed -i '/^static struct ns_common \*ipcns_get(/i EXPORT_SYMBOL(put_ipc_ns);' "$COMMON/ipc/namespace.c"
  fi
  grep -qF 'EXPORT_SYMBOL(init_ipc_ns);' "$COMMON/ipc/msgutil.c" ||
    die "DroidSpaces init_ipc_ns export is missing after integration"
  grep -qF 'EXPORT_SYMBOL(put_ipc_ns);' "$COMMON/ipc/namespace.c" ||
    die "DroidSpaces put_ipc_ns export is missing after integration"

  for cfg in CONFIG_SYSVIPC CONFIG_POSIX_MQUEUE CONFIG_IPC_NS CONFIG_PID_NS CONFIG_DEVTMPFS CONFIG_USER_NS; do
    append_config "$FRAGMENT" "$cfg=y"
  done
  for cfg in CONFIG_NETFILTER_XT_MATCH_ADDRTYPE CONFIG_NETFILTER_XT_TARGET_LOG     CONFIG_NETFILTER_XT_MATCH_RECENT CONFIG_IP_SET CONFIG_IP_SET_HASH_IP     CONFIG_IP_SET_HASH_NET CONFIG_NETFILTER_XT_SET CONFIG_NETFILTER_XT_TARGET_REJECT     CONFIG_IP_NF_TARGET_REJECT; do
    enable_if_defined "$cfg"
  done
  note "DroidSpaces integrated commit=$droidspaces_commit"
fi

if truthy "$DROIDSPACES_NTSYNC"; then
  [[ "$DROIDSPACES" == "on" ]] || die "NTSync requires DroidSpaces=on"
  ntsync_patch_ref="${XIAOMI_NTSYNC_PATCH_REF:-$NTSYNC_PATCH_DEFAULT_REF}"
  note "integrating DroidSpaces NTSync for android16-6.12 ref=$ntsync_patch_ref"

  ntsync_dir="$DEPS/Droidspaces_Kernel_patch"
  checkout_feature_ref "$NTSYNC_PATCH_REPO" "$ntsync_patch_ref" "$ntsync_dir"
  ntsync_patch_commit="$(git -C "$ntsync_dir" rev-parse HEAD)"
  base_patch="$ntsync_dir/NTsync/ntsync_base.patch"
  compat_patch="$ntsync_dir/NTsync/ntsync_compat_android16-6.12.patch"
  [[ -f "$base_patch" && -f "$compat_patch" ]] ||
    die "NTSync patch files are missing at commit $ntsync_patch_commit"

  if [[ -f "$COMMON/drivers/misc/ntsync.c" && -f "$COMMON/include/uapi/linux/ntsync.h" ]]; then
    note "NTSync base driver already present in 6.12; skipping ntsync_base.patch"
  else
    apply_patch_strict "$base_patch"
  fi

  if grep -A8 -E '^[[:space:]]*config[[:space:]]+NTSYNC$' "$COMMON/drivers/misc/Kconfig" | grep -q 'depends on BROKEN'; then
    apply_patch_strict "$compat_patch"
  else
    note "NTSync Kconfig is already enabled/compatible; skipping compat patch"
  fi

  append_config "$FRAGMENT" "CONFIG_NTSYNC=y"
  note "NTSync integration complete ref=$ntsync_patch_ref commit=$ntsync_patch_commit"
fi

if truthy "$USE_ZRAM"; then
  note "integrating Gold-family Android 16 / 6.12 LZ4K/LZ4KD ZRAM backend"

  zram_patch_ref="${XIAOMI_ZRAM_FEATURE_REF:-$ZRAM_FEATURE_DEFAULT_REF}"
  CCTV_FEATURE_DIR="$DEPS/cctv18-sm8850"

  checkout_feature_ref "$ZRAM_FEATURE_REPO" "$zram_patch_ref" "$CCTV_FEATURE_DIR"
  zram_patch_commit="$(git -C "$CCTV_FEATURE_DIR" rev-parse HEAD)"
  zram_patch="$CCTV_FEATURE_DIR/other_patch/lz4kd.patch"
  [[ -f "$zram_patch" ]] || die "Gold-family 6.12 LZ4KD patch missing: $zram_patch"

  # The generic SukiSU patch repository currently stops at 6.6. For 6.12,
  # use the dedicated patch maintained by the same cctv18 SM8850 build family
  # as our proven Gold baseline. Apply strictly so drift cannot be hidden.
  apply_patch_strict "$zram_patch"

  for line in     "CONFIG_ZSMALLOC=y"     "CONFIG_ZRAM=y"     "CONFIG_CRYPTO_LZ4HC=y"     "CONFIG_CRYPTO_LZ4K=y"     "CONFIG_CRYPTO_LZ4KD=y"     "CONFIG_CRYPTO_842=y"     "CONFIG_ZRAM_BACKEND_LZ4HC=y"     "CONFIG_ZRAM_BACKEND_LZ4K=y"     "CONFIG_ZRAM_BACKEND_LZ4KD=y"     "CONFIG_ZRAM_BACKEND_842=y"; do
    append_config "$FRAGMENT" "$line"
  done

  note "Gold-family 6.12 ZRAM stack integrated commit=$zram_patch_commit"
fi

if truthy "$USE_BBG"; then
  bbg_ref="${XIAOMI_BBG_REF:-$BBG_DEFAULT_REF}"
  note "integrating Baseband Guard ref=$bbg_ref"
  checkout_feature_ref "$BBG_REPO" "$bbg_ref" "$KERNEL_ROOT/Baseband-guard"
  bbg_commit="$(git -C "$KERNEL_ROOT/Baseband-guard" rev-parse HEAD)"
  (
    cd "$KERNEL_ROOT"
    sh "$KERNEL_ROOT/Baseband-guard/setup.sh" "$bbg_commit"
  )
  [[ "$(git -C "$KERNEL_ROOT/Baseband-guard" rev-parse HEAD)" == "$bbg_commit" ]] ||
    die "Baseband Guard checkout moved during setup"
  grep -RqsE '^[[:space:]]*config[[:space:]]+BBG([[:space:]]|$)' "$COMMON" ||
    die "BBG setup completed but CONFIG_BBG is not declared"
  append_config "$FRAGMENT" "CONFIG_BBG=y"
  sed -i '/^config LSM$/,/^help$/{ /^[[:space:]]*default/ { /baseband_guard/! s/selinux/selinux,baseband_guard/ } }' "$COMMON/security/Kconfig"
  note "Baseband Guard integrated ref=$bbg_ref commit=$bbg_commit"
fi

if truthy "$USE_NETWORKING"; then
  note "enabling Android 16 / 6.12 networking feature set (BBR baseline, IPSet, Qdisc, CIFS)"
  for cfg in CONFIG_IP_SET CONFIG_IP_SET_BITMAP_IP CONFIG_IP_SET_BITMAP_IPMAC     CONFIG_IP_SET_BITMAP_PORT CONFIG_IP_SET_HASH_IP CONFIG_IP_SET_HASH_IPMARK     CONFIG_IP_SET_HASH_IPPORT CONFIG_IP_SET_HASH_IPPORTIP CONFIG_IP_SET_HASH_IPPORTNET     CONFIG_IP_SET_HASH_IPMAC CONFIG_IP_SET_HASH_MAC CONFIG_IP_SET_HASH_NETPORTNET     CONFIG_IP_SET_HASH_NET CONFIG_IP_SET_HASH_NETNET CONFIG_IP_SET_HASH_NETPORT     CONFIG_IP_SET_HASH_NETIFACE CONFIG_IP_SET_LIST_SET CONFIG_NETFILTER_XT_MATCH_ADDRTYPE     CONFIG_NETFILTER_XT_SET CONFIG_NETFILTER_XT_TARGET_LOG CONFIG_NETFILTER_XT_MATCH_RECENT     CONFIG_IP6_NF_NAT CONFIG_IP6_NF_TARGET_MASQUERADE CONFIG_TCP_CONG_ADVANCED     CONFIG_TCP_CONG_BBR CONFIG_TCP_CONG_CUBIC CONFIG_TCP_CONG_BIC CONFIG_TCP_CONG_WESTWOOD     CONFIG_TCP_CONG_HTCP CONFIG_NET_SCH_FQ CONFIG_NET_SCH_FQ_CODEL CONFIG_NET_SCH_CAKE     CONFIG_NET_ACT_CONNMARK CONFIG_IP_NF_TARGET_TTL CONFIG_IP6_NF_TARGET_HL     CONFIG_IP6_NF_MATCH_HL CONFIG_WIREGUARD CONFIG_CIFS CONFIG_NETWORK_FILESYSTEMS     CONFIG_KEYS CONFIG_CIFS_XATTR CONFIG_CIFS_POSIX CONFIG_NETFS_SUPPORT; do
    enable_if_defined "$cfg"
  done
  if config_defined CONFIG_IP_SET_MAX; then append_config "$FRAGMENT" "CONFIG_IP_SET_MAX=65534"; fi
  if config_defined CONFIG_DEFAULT_BBR; then append_config "$FRAGMENT" "CONFIG_DEFAULT_BBR=y"; fi
  if config_defined CONFIG_DEFAULT_TCP_CONG; then append_config "$FRAGMENT" 'CONFIG_DEFAULT_TCP_CONG="bbr"'; fi
fi

if truthy "$USE_REKERNEL"; then
  rekernel_ref="${XIAOMI_REKERNEL_REF:-$REKERNEL_DEFAULT_REF}"
  note "integrating Re-Kernel as built-in driver ref=$rekernel_ref"
  checkout_feature_ref "$REKERNEL_REPO" "$rekernel_ref" "$DEPS/Re-Kernel"
  rekernel_commit="$(git -C "$DEPS/Re-Kernel" rev-parse HEAD)"
  rm -rf "$COMMON/drivers/rekernel"
  mkdir -p "$COMMON/drivers/rekernel"
  cp -a "$DEPS/Re-Kernel/LKM-Source/." "$COMMON/drivers/rekernel/"

  sed -i 's/^obj-m := rekernel\.o$/obj-$(CONFIG_REKERNEL) += rekernel.o/' "$COMMON/drivers/rekernel/Makefile"
  grep -qF 'ccflags-$(CONFIG_REKERNEL_LEGACY_NETLINK) += -DLEGACY_NETLINK' "$COMMON/drivers/rekernel/Makefile" ||
    echo 'ccflags-$(CONFIG_REKERNEL_LEGACY_NETLINK) += -DLEGACY_NETLINK' >> "$COMMON/drivers/rekernel/Makefile"
  sed -i '/^[[:space:]]*depends on MODULES[[:space:]]*$/d' "$COMMON/drivers/rekernel/Kconfig"

  if ! grep -qF 'source "drivers/rekernel/Kconfig"' "$COMMON/drivers/Kconfig"; then
    python3 - "$COMMON/drivers/Kconfig" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(); i=s.rfind("\nendmenu")
if i < 0: raise SystemExit("drivers/Kconfig final endmenu not found")
p.write_text(s[:i]+'\nsource "drivers/rekernel/Kconfig"\n'+s[i:])
PY
  fi
  grep -qF 'obj-$(CONFIG_REKERNEL) += rekernel/' "$COMMON/drivers/Makefile" ||
    echo 'obj-$(CONFIG_REKERNEL) += rekernel/' >> "$COMMON/drivers/Makefile"
  sed -i 's|#include <../android/binder_internal.h>|#include "../android/binder_internal.h"|g' "$COMMON/drivers/rekernel/rekernel_binder.c"
  grep -qF '#include <linux/seq_file.h>' "$COMMON/drivers/rekernel/rekernel_binder.c" ||
    sed -i '/#include <linux\/kprobes.h>/a #include <linux/seq_file.h>' "$COMMON/drivers/rekernel/rekernel_binder.c"
  append_config "$FRAGMENT" "CONFIG_REKERNEL=y"
  append_config "$FRAGMENT" "CONFIG_REKERNEL_NETWORK=y"
  note "Re-Kernel integrated ref=$rekernel_ref commit=$rekernel_commit"
fi

if truthy "$USE_CVE"; then
  sublevel="$(awk -F= '/^SUBLEVEL[[:space:]]*=/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "$COMMON/Makefile")"
  [[ "$sublevel" =~ ^[0-9]+$ ]] || die "unable to resolve kernel SUBLEVEL for CVE patch"
  note "applying repository CVE-2026-43499/CVE-2026-53163 chain to 6.12.$sublevel"
  (cd "$COMMON" && bash "$XIAOMI_REPO_ROOT/security_patch/apply_cve_2026_43499.sh"     "6.12" "$sublevel" "$XIAOMI_REPO_ROOT/security_patch")
fi

cat > "$PROVENANCE" <<EOF
feature_use_zram=$USE_ZRAM
feature_zram_patch_ref=$zram_patch_ref
feature_zram_patch_commit=$zram_patch_commit
feature_use_bbg=$USE_BBG
feature_bbg_ref=$bbg_ref
feature_bbg_commit=$bbg_commit
feature_use_kpm=$USE_KPM
feature_use_rekernel=$USE_REKERNEL
feature_rekernel_ref=$rekernel_ref
feature_rekernel_commit=$rekernel_commit
feature_use_nomount=$USE_NOMOUNT
feature_nomount_ref=$nomount_ref
feature_nomount_commit=$nomount_commit
feature_use_networking=$USE_NETWORKING
feature_cve_2026_43499_patch=$USE_CVE
feature_droidspaces=$DROIDSPACES
feature_droidspaces_ref=$droidspaces_ref
feature_droidspaces_commit=$droidspaces_commit
feature_droidspaces_ntsync=$DROIDSPACES_NTSYNC
feature_ntsync_patch_ref=$ntsync_patch_ref
feature_ntsync_patch_commit=$ntsync_patch_commit
EOF

note "optional feature integration complete"
