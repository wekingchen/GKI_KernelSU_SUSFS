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

sukisu_patch_commit="N/A"
nomount_commit="N/A"
droidspaces_commit="N/A"
rekernel_commit="N/A"

if [[ "$USE_KPM" == patched* ]]; then
  die "KPM patched mode is intentionally unsupported on the Xiaomi Gold lane"
fi
if truthy "$USE_KPM"; then
  grep -RqsE '^[[:space:]]*config[[:space:]]+KPM([[:space:]]|$)'     "$KERNEL_ROOT/ReSukiSU/kernel" 2>/dev/null ||
    die "KPM requested but current ReSukiSU does not declare CONFIG_KPM"
  append_config "$FRAGMENT" "CONFIG_KPM=y"
  note "KPM enabled"
fi

if truthy "$USE_NOMOUNT"; then
  note "integrating latest NoMount dev"
  (
    cd "$COMMON"
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors       https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh | bash -s dev
  )
  [[ -L "$COMMON/fs/nomount" ]] || die "NoMount integration did not create fs/nomount symlink"
  [[ -d "$COMMON/NoMount/.git" ]] && nomount_commit="$(git -C "$COMMON/NoMount" rev-parse HEAD)"
  append_config "$FRAGMENT" "CONFIG_NOMOUNT=y"
  note "NoMount integrated commit=$nomount_commit"
fi

if [[ "$DROIDSPACES" != "off" ]]; then
  [[ "$DROIDSPACES" == "on" ]] || die "Xiaomi 6.12 supports DroidSpaces values: off/on"
  note "integrating DroidSpaces 6.12 support"
  git clone --depth 1 https://github.com/ravindu644/Droidspaces-OSS.git "$DEPS/Droidspaces-OSS"
  droidspaces_commit="$(git -C "$DEPS/Droidspaces-OSS" rev-parse HEAD)"
  patch_file="$DEPS/Droidspaces-OSS/Documentation/resources/kernel-patches/GKI/kernel-6.12/001.GKI-6.12-or-above-fix_sysvipc_kabi.patch"
  apply_patch_strict "$patch_file"

  if [[ -f "$COMMON/ipc/msgutil.c" ]] && ! grep -qF 'EXPORT_SYMBOL(init_ipc_ns);' "$COMMON/ipc/msgutil.c"; then
    sed -i '/^struct msg_msgseg {/i EXPORT_SYMBOL(init_ipc_ns);' "$COMMON/ipc/msgutil.c"
  fi
  if [[ -f "$COMMON/ipc/namespace.c" ]] && ! grep -qF 'EXPORT_SYMBOL(put_ipc_ns);' "$COMMON/ipc/namespace.c"; then
    sed -i '/^static struct ns_common \*ipcns_get(/i EXPORT_SYMBOL(put_ipc_ns);' "$COMMON/ipc/namespace.c"
  fi

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
  note "integrating DroidSpaces NTSync for android16-6.12"
  base_patch="$DEPS/ntsync_base.patch"
  compat_patch="$DEPS/ntsync_compat_android16-6.12.patch"
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors     https://raw.githubusercontent.com/Goldzxcbug/Droidspaces_Kernel_patch/refs/heads/main/NTsync/ntsync_base.patch     -o "$base_patch"
  curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors     https://raw.githubusercontent.com/Goldzxcbug/Droidspaces_Kernel_patch/refs/heads/main/NTsync/ntsync_compat_android16-6.12.patch     -o "$compat_patch"
  apply_patch_strict "$base_patch"
  apply_patch_strict "$compat_patch"
  append_config "$FRAGMENT" "CONFIG_NTSYNC=y"
fi

if truthy "$USE_ZRAM"; then
  note "integrating upstream custom-workflow ZRAM/LZ4 stack"
  git clone --depth 1 https://github.com/ShirkNeko/SukiSU_patch.git "$DEPS/SukiSU_patch"
  sukisu_patch_commit="$(git -C "$DEPS/SukiSU_patch" rev-parse HEAD)"

  rm -f "$COMMON"/lib/lz4/lz4_compress.c "$COMMON"/lib/lz4/lz4_decompress.c     "$COMMON"/lib/lz4/lz4defs.h "$COMMON"/lib/lz4/lz4hc_compress.c
  cp -r "$XIAOMI_REPO_ROOT"/zram/lz4/* "$COMMON/lib/lz4/"
  cp -r "$XIAOMI_REPO_ROOT"/zram/include/linux/* "$COMMON/include/linux/"
  (cd "$COMMON" && bash "$XIAOMI_REPO_ROOT/zram/apply_lz4_neon.sh")

  if [[ -f "$COMMON/fs/f2fs/Makefile" ]] &&
     ! grep -qF 'f2fs-$(CONFIG_F2FS_IOSTAT) += iostat.o' "$COMMON/fs/f2fs/Makefile"; then
    echo 'f2fs-$(CONFIG_F2FS_IOSTAT) += iostat.o' >> "$COMMON/fs/f2fs/Makefile"
  fi

  cp -r "$DEPS/SukiSU_patch"/other/zram/lz4k/include/linux/* "$COMMON/include/linux/"
  cp -r "$DEPS/SukiSU_patch"/other/zram/lz4k/lib/* "$COMMON/lib/"
  cp -r "$DEPS/SukiSU_patch"/other/zram/lz4k/crypto/* "$COMMON/crypto/"
  cp -r "$DEPS/SukiSU_patch"/other/zram/lz4k_oplus "$COMMON/lib/"

  for p in lz4kd.patch lz4k_oplus.patch; do
    patch_file="$DEPS/SukiSU_patch/other/zram/zram_patch/6.12/$p"
    [[ -f "$patch_file" ]] || die "ZRAM patch missing: $patch_file"
    (cd "$COMMON" && patch --batch --forward --dry-run -F 3 -p1 < "$patch_file") ||
      die "ZRAM patch dry-run failed: $p"
    (cd "$COMMON" && patch --batch --forward --no-backup-if-mismatch -F 3 -p1 < "$patch_file") ||
      die "ZRAM patch apply failed: $p"
  done

  append_config "$FRAGMENT" "CONFIG_ZSMALLOC=y"
  append_config "$FRAGMENT" "CONFIG_ZRAM=y"
  while IFS= read -r line; do
    [[ "$line" == CONFIG_* ]] && append_config "$FRAGMENT" "$line"
  done < "$XIAOMI_REPO_ROOT/config/zram.config"
  note "ZRAM stack integrated SukiSU_patch commit=$sukisu_patch_commit"
fi

if truthy "$USE_BBG"; then
  note "integrating latest Baseband Guard"
  (cd "$KERNEL_ROOT" && curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors     https://github.com/vc-teahouse/Baseband-guard/raw/main/setup.sh | bash)
  grep -RqsE '^[[:space:]]*config[[:space:]]+BBG([[:space:]]|$)' "$COMMON" ||
    die "BBG setup completed but CONFIG_BBG is not declared"
  append_config "$FRAGMENT" "CONFIG_BBG=y"
  sed -i '/^config LSM$/,/^help$/{ /^[[:space:]]*default/ { /baseband_guard/! s/selinux/selinux,baseband_guard/ } }'     "$COMMON/security/Kconfig"
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
  note "integrating latest Re-Kernel as built-in driver"
  git clone --depth 1 https://github.com/Sakion-Team/Re-Kernel.git "$DEPS/Re-Kernel"
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
  sed -i 's|#include <../android/binder_internal.h>|#include "../android/binder_internal.h"|g'     "$COMMON/drivers/rekernel/rekernel_binder.c"
  grep -qF '#include <linux/seq_file.h>' "$COMMON/drivers/rekernel/rekernel_binder.c" ||
    sed -i '/#include <linux\/kprobes.h>/a #include <linux/seq_file.h>' "$COMMON/drivers/rekernel/rekernel_binder.c"
  append_config "$FRAGMENT" "CONFIG_REKERNEL=y"
  append_config "$FRAGMENT" "CONFIG_REKERNEL_NETWORK=y"
  note "Re-Kernel integrated commit=$rekernel_commit"
fi

if truthy "$USE_CVE"; then
  sublevel="$(awk -F= '/^SUBLEVEL[[:space:]]*=/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "$COMMON/Makefile")"
  [[ "$sublevel" =~ ^[0-9]+$ ]] || die "unable to resolve kernel SUBLEVEL for CVE patch"
  note "applying repository CVE-2026-43499/CVE-2026-53163 chain to 6.12.$sublevel"
  (cd "$COMMON" && bash "$XIAOMI_REPO_ROOT/security_patch/apply_cve_2026_43499.sh"     "6.12" "$sublevel" "$XIAOMI_REPO_ROOT/security_patch")
fi

cat > "$PROVENANCE" <<EOF
feature_use_zram=$USE_ZRAM
feature_zram_patch_commit=$sukisu_patch_commit
feature_use_bbg=$USE_BBG
feature_use_kpm=$USE_KPM
feature_use_rekernel=$USE_REKERNEL
feature_rekernel_commit=$rekernel_commit
feature_use_nomount=$USE_NOMOUNT
feature_nomount_commit=$nomount_commit
feature_use_networking=$USE_NETWORKING
feature_cve_2026_43499_patch=$USE_CVE
feature_droidspaces=$DROIDSPACES
feature_droidspaces_commit=$droidspaces_commit
feature_droidspaces_ntsync=$DROIDSPACES_NTSYNC
EOF

note "optional feature integration complete"
