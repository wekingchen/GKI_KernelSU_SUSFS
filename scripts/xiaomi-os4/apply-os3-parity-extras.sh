#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?usage: apply-os3-parity-extras.sh <source|config|validate>}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"

STAGE="${RUNNER_TEMP:?RUNNER_TEMP is required}/xiaomi-os4-integrated"
SRC="$STAGE/common"
OUT="$STAGE/out"
RESULT="$STAGE/results"

mkdir -p "$RESULT"

checkout_locked() {
  local url="$1" ref="$2" sha="$3" dir="$4"
  [[ ! -e "$dir" ]] || {
    echo "::error::Parity dependency path already exists: $dir"
    exit 1
  }
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  if ! git -C "$dir" fetch -q --depth=1 origin "$sha"; then
    git -C "$dir" fetch -q --depth=1 origin "refs/heads/$ref"
  fi
  git -C "$dir" checkout -q --detach FETCH_HEAD
  [[ "$(git -C "$dir" rev-parse HEAD)" == "$sha" ]] || {
    echo "::error::Parity dependency drift: $url"
    exit 1
  }
}

config_defined() {
  local cfg="$1"
  grep -RqsE --include='Kconfig*' "^[[:space:]]*(menuconfig|config)[[:space:]]+${cfg}([[:space:]]|$)" "$SRC"
}

case "$MODE" in
  source)
    NTSYNC_SHA="${OS4_NTSYNC_PATCH_COMMIT:?missing OS4_NTSYNC_PATCH_COMMIT}"
    BBG_SHA="${OS4_BBG_COMMIT:?missing OS4_BBG_COMMIT}"
    REKERNEL_SHA="${OS4_REKERNEL_COMMIT:?missing OS4_REKERNEL_COMMIT}"

    echo "[OS4 parity] checkout pinned NTSync/BBG/Re-Kernel sources"
    checkout_locked "$OS4_NTSYNC_PATCH_REPO" "$OS4_NTSYNC_PATCH_REF" "$NTSYNC_SHA" "$STAGE/ntsync-patch"
    checkout_locked "$OS4_BBG_REPO" "$OS4_BBG_REF" "$BBG_SHA" "$SRC/Baseband-guard"
    checkout_locked "$OS4_REKERNEL_REPO" "$OS4_REKERNEL_REF" "$REKERNEL_SHA" "$STAGE/rekernel"

    # Android 16 / 6.12 already carries the NTSync driver. The pinned patch is
    # only allowed to remove the BROKEN gate. Never replace the R62 driver with
    # an older ntsync_base.patch.
    NTSYNC_COMPAT="$STAGE/ntsync-patch/NTsync/ntsync_compat_android16-6.12.patch"
    [[ -s "$NTSYNC_COMPAT" && -s "$SRC/drivers/misc/ntsync.c" && -s "$SRC/include/uapi/linux/ntsync.h" ]] || {
      echo "::error::R62 NTSync source or pinned compatibility patch missing"
      exit 1
    }
    if grep -A8 -E '^[[:space:]]*config[[:space:]]+NTSYNC$' "$SRC/drivers/misc/Kconfig" | grep -q 'depends on BROKEN'; then
      patch --dry-run --batch --forward -d "$SRC" -p1 < "$NTSYNC_COMPAT" > "$RESULT/ntsync-dryrun.log" 2>&1 || {
        cat "$RESULT/ntsync-dryrun.log"
        exit 1
      }
      patch --batch --forward --no-backup-if-mismatch -d "$SRC" -p1 < "$NTSYNC_COMPAT" > "$RESULT/ntsync-apply.log" 2>&1 || {
        cat "$RESULT/ntsync-apply.log"
        exit 1
      }
      NTSYNC_STATUS="PINNED_COMPAT_PATCH_APPLIED"
    else
      NTSYNC_STATUS="R62_ALREADY_ENABLED_COMPAT_NOT_NEEDED"
    fi

    # Baseband Guard: reproduce only its modern GKI integration. We deliberately
    # do not run upstream setup.sh because setup.sh can perform mutable fetches.
    [[ -s "$SRC/Baseband-guard/Kconfig" && -s "$SRC/Baseband-guard/Makefile" ]] || {
      echo "::error::Pinned Baseband Guard source incomplete"
      exit 1
    }
    [[ ! -e "$SRC/security/baseband-guard" ]] || {
      echo "::error::Baseband Guard was already integrated unexpectedly"
      exit 1
    }
    ln -s "$(realpath --relative-to="$SRC/security" "$SRC/Baseband-guard")" "$SRC/security/baseband-guard"
    grep -Fq 'obj-$(CONFIG_BBG) += baseband-guard/' "$SRC/security/Makefile" ||
      printf '\nobj-$(CONFIG_BBG) += baseband-guard/\n' >> "$SRC/security/Makefile"
    python3 - "$SRC/security/Kconfig" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
line='source "security/baseband-guard/Kconfig"'
if line in s:
    raise SystemExit("unexpected prior Baseband Guard Kconfig source")
pos=s.rfind("\nendmenu")
if pos < 0:
    raise SystemExit("security/Kconfig final endmenu not found")
p.write_text(s[:pos]+"\n"+line+s[pos:])
PY

    # Re-Kernel: same built-in conversion as the OS3 proven path, pinned to the
    # current audited commit and using Generic Netlink rather than legacy raw netlink.
    [[ -d "$STAGE/rekernel/LKM-Source" ]] || {
      echo "::error::Pinned Re-Kernel LKM-Source missing"
      exit 1
    }
    rm -rf "$SRC/drivers/rekernel"
    mkdir -p "$SRC/drivers/rekernel"
    cp -a "$STAGE/rekernel/LKM-Source/." "$SRC/drivers/rekernel/"
    sed -i 's/^obj-m := rekernel\.o$/obj-$(CONFIG_REKERNEL) += rekernel.o/' "$SRC/drivers/rekernel/Makefile"
    grep -Fq 'obj-$(CONFIG_REKERNEL) += rekernel.o' "$SRC/drivers/rekernel/Makefile" || {
      echo "::error::Re-Kernel Makefile built-in conversion failed"
      exit 1
    }
    grep -Fq 'ccflags-$(CONFIG_REKERNEL_LEGACY_NETLINK) += -DLEGACY_NETLINK' "$SRC/drivers/rekernel/Makefile" ||
      echo 'ccflags-$(CONFIG_REKERNEL_LEGACY_NETLINK) += -DLEGACY_NETLINK' >> "$SRC/drivers/rekernel/Makefile"
    sed -i '/^[[:space:]]*depends on MODULES[[:space:]]*$/d' "$SRC/drivers/rekernel/Kconfig"
    python3 - "$SRC/drivers/Kconfig" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
line='source "drivers/rekernel/Kconfig"'
if line in s:
    raise SystemExit("unexpected prior Re-Kernel Kconfig source")
pos=s.rfind("\nendmenu")
if pos < 0:
    raise SystemExit("drivers/Kconfig final endmenu not found")
p.write_text(s[:pos]+"\n"+line+s[pos:])
PY
    grep -Fq 'obj-$(CONFIG_REKERNEL) += rekernel/' "$SRC/drivers/Makefile" ||
      printf '\nobj-$(CONFIG_REKERNEL) += rekernel/\n' >> "$SRC/drivers/Makefile"
    sed -i 's|#include <../android/binder_internal.h>|#include "../android/binder_internal.h"|g' "$SRC/drivers/rekernel/rekernel_binder.c"
    grep -Fq '#include <linux/seq_file.h>' "$SRC/drivers/rekernel/rekernel_binder.c" ||
      sed -i '/#include <linux\/kprobes.h>/a #include <linux/seq_file.h>' "$SRC/drivers/rekernel/rekernel_binder.c"

    # Audit/apply the repository's idempotent CVE-2026-43499 + CVE-2026-53163
    # chain. 6.12.69 is below the generic 6.12.95 threshold, but Android R62
    # may have cherry-picked it; the helper detects that from source semantics.
    CVE_PATHS=(
      kernel/locking/rtmutex.c
      kernel/locking/rtmutex_api.c
      kernel/locking/Makefile
      include/linux/cleanup.h
      include/linux/compiler_attributes.h
      include/linux/compiler-clang.h
      include/linux/spinlock.h
    )
    before_cve="$(git -C "$SRC" diff -- "${CVE_PATHS[@]}" | sha256sum | awk '{print $1}')"
    (
      cd "$SRC"
      bash "$ROOT/security_patch/apply_cve_2026_43499.sh" "6.12" "69" "$ROOT/security_patch"
    ) | tee "$RESULT/cve-chain-audit.log"
    after_cve="$(git -C "$SRC" diff -- "${CVE_PATHS[@]}" | sha256sum | awk '{print $1}')"
    if [[ "$before_cve" == "$after_cve" ]]; then
      CVE_STATUS="UPSTREAM_OR_ALREADY_PRESENT"
    else
      CVE_STATUS="BACKPORTED_BY_REPOSITORY_CHAIN"
    fi

    cat > "$RESULT/os3-parity-source.env" <<EOF
OS3_PARITY_NTSYNC_COMMIT=$NTSYNC_SHA
OS3_PARITY_NTSYNC_STATUS=$NTSYNC_STATUS
OS3_PARITY_BBG_COMMIT=$BBG_SHA
OS3_PARITY_REKERNEL_COMMIT=$REKERNEL_SHA
CVE_2026_43499_53163_STATUS=$CVE_STATUS
EOF

    git -C "$SRC" diff --check --       drivers/misc/Kconfig       security/Kconfig security/Makefile       drivers/Kconfig drivers/Makefile drivers/rekernel       kernel/locking include/linux

    cat "$RESULT/os3-parity-source.env"
    ;;

  config)
    [[ -s "$OUT/.config" ]] || {
      echo "::error::Kernel .config missing before parity configuration"
      exit 1
    }
    [[ -s "$RESULT/os3-parity-source.env" ]] || {
      echo "::error::Parity source integration metadata missing"
      exit 1
    }

    ENABLED="$RESULT/os3-parity-config-enabled.txt"
    SKIPPED="$RESULT/os3-parity-config-skipped.txt"
    : > "$ENABLED"
    : > "$SKIPPED"

    enable_if_defined() {
      local cfg="$1"
      if config_defined "$cfg"; then
        "$SRC/scripts/config" --file "$OUT/.config" --enable "$cfg"
        echo "CONFIG_$cfg" >> "$ENABLED"
      else
        echo "CONFIG_$cfg" >> "$SKIPPED"
      fi
    }

    # Networking Full parity from the mature OS3 lane.
    for cfg in       IP_SET IP_SET_BITMAP_IP IP_SET_BITMAP_IPMAC IP_SET_BITMAP_PORT       IP_SET_HASH_IP IP_SET_HASH_IPMARK IP_SET_HASH_IPPORT IP_SET_HASH_IPPORTIP       IP_SET_HASH_IPPORTNET IP_SET_HASH_IPMAC IP_SET_HASH_MAC       IP_SET_HASH_NETPORTNET IP_SET_HASH_NET IP_SET_HASH_NETNET       IP_SET_HASH_NETPORT IP_SET_HASH_NETIFACE IP_SET_LIST_SET       NETFILTER_XT_MATCH_ADDRTYPE NETFILTER_XT_SET NETFILTER_XT_TARGET_LOG       NETFILTER_XT_MATCH_RECENT IP6_NF_NAT IP6_NF_TARGET_MASQUERADE       TCP_CONG_ADVANCED TCP_CONG_BBR TCP_CONG_CUBIC TCP_CONG_BIC       TCP_CONG_WESTWOOD TCP_CONG_HTCP NET_SCH_FQ NET_SCH_FQ_CODEL NET_SCH_CAKE       NET_ACT_CONNMARK IP_NF_TARGET_TTL IP6_NF_TARGET_HL IP6_NF_MATCH_HL       WIREGUARD CIFS NETWORK_FILESYSTEMS KEYS CIFS_XATTR CIFS_POSIX NETFS_SUPPORT; do
      enable_if_defined "$cfg"
    done

    if config_defined IP_SET_MAX; then
      "$SRC/scripts/config" --file "$OUT/.config" --set-val IP_SET_MAX 65534
    fi
    if config_defined DEFAULT_BBR; then
      "$SRC/scripts/config" --file "$OUT/.config" --enable DEFAULT_BBR
    fi
    if config_defined DEFAULT_TCP_CONG; then
      "$SRC/scripts/config" --file "$OUT/.config" --set-str DEFAULT_TCP_CONG bbr
    fi

    "$SRC/scripts/config" --file "$OUT/.config"       --enable NTSYNC       --enable BBG       --disable BBG_BLOCK_BOOT       --disable BBG_BLOCK_RECOVERY       --enable REKERNEL       --enable REKERNEL_NETWORK       --disable REKERNEL_LEGACY_NETLINK

    current_lsm="$(sed -n 's/^CONFIG_LSM="\(.*\)"/\1/p' "$OUT/.config")"
    [[ -n "$current_lsm" ]] || {
      echo "::error::CONFIG_LSM missing before Baseband Guard config"
      exit 1
    }
    case ",$current_lsm," in
      *,baseband_guard,*) ;;
      *) "$SRC/scripts/config" --file "$OUT/.config" --set-str LSM "$current_lsm,baseband_guard" ;;
    esac
    ;;

  validate)
    [[ -s "$OUT/.config" ]] || {
      echo "::error::Kernel .config missing for parity validation"
      exit 1
    }
    for cfg in       CONFIG_NTSYNC       CONFIG_BBG       CONFIG_REKERNEL       CONFIG_REKERNEL_NETWORK       CONFIG_IP_SET       CONFIG_TCP_CONG_ADVANCED       CONFIG_TCP_CONG_BBR       CONFIG_NET_SCH_FQ       CONFIG_NET_SCH_FQ_CODEL       CONFIG_NET_SCH_CAKE       CONFIG_WIREGUARD       CONFIG_CIFS; do
      grep -qx "$cfg=y" "$OUT/.config" || {
        actual="$(grep -E "^$cfg=|^# $cfg is not set" "$OUT/.config" || echo '<absent>')"
        echo "::error::OS3 parity config did not resolve: $cfg (actual: $actual)"
        exit 1
      }
    done

    grep -qx '# CONFIG_REKERNEL_LEGACY_NETLINK is not set' "$OUT/.config" || {
      echo "::error::Re-Kernel must stay on Generic Netlink"
      exit 1
    }
    grep -qx '# CONFIG_BBG_BLOCK_BOOT is not set' "$OUT/.config" || {
      echo "::error::Baseband Guard boot blocking must stay disabled"
      exit 1
    }
    grep -qx '# CONFIG_BBG_BLOCK_RECOVERY is not set' "$OUT/.config" || {
      echo "::error::Baseband Guard recovery blocking must stay disabled"
      exit 1
    }

    lsm="$(sed -n 's/^CONFIG_LSM="\(.*\)"/\1/p' "$OUT/.config")"
    echo "$lsm" | tr ',' '\n' | grep -qx baseband_guard || {
      echo "::error::baseband_guard missing from CONFIG_LSM: $lsm"
      exit 1
    }

    if config_defined DEFAULT_BBR; then
      grep -qx 'CONFIG_DEFAULT_BBR=y' "$OUT/.config" || {
        echo "::error::CONFIG_DEFAULT_BBR did not resolve"
        exit 1
      }
    fi
    if config_defined DEFAULT_TCP_CONG; then
      grep -qx 'CONFIG_DEFAULT_TCP_CONG="bbr"' "$OUT/.config" || {
        echo "::error::DEFAULT_TCP_CONG is not bbr"
        exit 1
      }
    fi

    {
      echo "OS3_PARITY_CONFIG=PASS"
      grep -E '^(CONFIG_NTSYNC|CONFIG_BBG|CONFIG_REKERNEL|CONFIG_REKERNEL_NETWORK|CONFIG_IP_SET|CONFIG_TCP_CONG_BBR|CONFIG_DEFAULT_BBR|CONFIG_DEFAULT_TCP_CONG|CONFIG_NET_SCH_FQ|CONFIG_NET_SCH_FQ_CODEL|CONFIG_NET_SCH_CAKE|CONFIG_WIREGUARD|CONFIG_CIFS|CONFIG_LSM)=' "$OUT/.config" || true
    } | tee "$RESULT/os3-parity-config-result.txt"
    ;;

  *)
    echo "::error::Unknown mode: $MODE"
    exit 2
    ;;
esac
