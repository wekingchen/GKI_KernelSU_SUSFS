#!/usr/bin/env bash
set -euo pipefail

# Xiaomi 17 Pro OS4 R62 selectable builder. Custom combinations remain fastboot-boot test only until validated.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"
STAGE="$RUNNER_TEMP/xiaomi-os4-integrated"
SRC="$STAGE/common"
OUT="$STAGE/out"
RESULT="$STAGE/results"
CACHE_ROOT="$HOME/.cache/xiaomi-os4"
GIT_CACHE="$CACHE_ROOT/common-r62.git"
TOOL_CACHE="$CACHE_ROOT/toolchain-r536225"
mkdir -p "$STAGE" "$RESULT" "$CACHE_ROOT"

CUSTOM_SELECTABLE="${XIAOMI_OS4_SELECTABLE_BUILD:-0}"
ROOT_MODE="${XIAOMI_OS4_ROOT_MODE:-bakasu-susfs}"
SUSFS_EXTRA_FEATURES="${XIAOMI_OS4_SUSFS_EXTRA_FEATURES:-1}"
USE_NOMOUNT="${XIAOMI_OS4_USE_NOMOUNT:-1}"
DROIDSPACES_ENABLED="${XIAOMI_OS4_DROIDSPACES:-1}"
USE_NTSYNC="${XIAOMI_OS4_USE_NTSYNC:-1}"
USE_BBG="${XIAOMI_OS4_USE_BBG:-1}"
USE_REKERNEL="${XIAOMI_OS4_USE_REKERNEL:-1}"
USE_NETWORKING="${XIAOMI_OS4_USE_NETWORKING:-1}"
USE_CVE="${XIAOMI_OS4_USE_CVE:-1}"

# Legacy low-level controls remain supported so the immutable LKG workflow can
# reproduce the already-verified image byte-for-byte.
DROIDSPACES_PIDS="${XIAOMI_OS4_ENABLE_CGROUP_PIDS:-0}"
DROIDSPACES_PIDS_REUSE_NET_PRIO="${XIAOMI_OS4_PIDS_REUSE_NET_PRIO_SLOT:-0}"
DROIDSPACES_PIDS_REPURPOSE_NET_PRIO="${XIAOMI_OS4_PIDS_REPURPOSE_NET_PRIO:-0}"
DROIDSPACES_CORE_NAMESPACES="${XIAOMI_OS4_DROIDSPACES_CORE_NAMESPACES:-0}"
DROIDSPACES_MACVLAN="${XIAOMI_OS4_DROIDSPACES_MACVLAN:-0}"
DROIDSPACES_FULL_EXTRAS="${XIAOMI_OS4_DROIDSPACES_FULL_EXTRAS:-0}"
OS3_PARITY_EXTRAS="${XIAOMI_OS4_OS3_PARITY_EXTRAS:-0}"
SELECTED_EXTRAS=0
EXACT_LKG_SELECTION=0

check_bool() {
  local name="$1" value="$2"
  [[ "$value" == "0" || "$value" == "1" ]] || {
    echo "::error::$name must be 0 or 1 (actual: $value)"
    exit 1
  }
}

check_bool XIAOMI_OS4_SELECTABLE_BUILD "$CUSTOM_SELECTABLE"

if [[ "$CUSTOM_SELECTABLE" == "1" ]]; then
  case "$ROOT_MODE" in
    bakasu-susfs)
      USE_BAKASU=1
      USE_SUSFS=1
      ;;
    bakasu)
      USE_BAKASU=1
      USE_SUSFS=0
      ;;
    none)
      USE_BAKASU=0
      USE_SUSFS=0
      ;;
    *)
      echo "::error::XIAOMI_OS4_ROOT_MODE must be bakasu-susfs, bakasu or none"
      exit 1
      ;;
  esac

  for pair in     "XIAOMI_OS4_SUSFS_EXTRA_FEATURES:$SUSFS_EXTRA_FEATURES"     "XIAOMI_OS4_USE_NOMOUNT:$USE_NOMOUNT"     "XIAOMI_OS4_DROIDSPACES:$DROIDSPACES_ENABLED"     "XIAOMI_OS4_USE_NTSYNC:$USE_NTSYNC"     "XIAOMI_OS4_USE_BBG:$USE_BBG"     "XIAOMI_OS4_USE_REKERNEL:$USE_REKERNEL"     "XIAOMI_OS4_USE_NETWORKING:$USE_NETWORKING"     "XIAOMI_OS4_USE_CVE:$USE_CVE"; do
    check_bool "${pair%%:*}" "${pair#*:}"
  done

  if [[ "$USE_SUSFS" != "1" && "$SUSFS_EXTRA_FEATURES" == "1" ]]; then
    echo "::warning::SUSFS 扩展已选择，但 Root 模式未启用 SUSFS；自动忽略。"
    SUSFS_EXTRA_FEATURES=0
  fi
  DROIDSPACES_PIDS=0
  DROIDSPACES_PIDS_REUSE_NET_PRIO=0
  DROIDSPACES_PIDS_REPURPOSE_NET_PRIO=0
  DROIDSPACES_CORE_NAMESPACES=0
  DROIDSPACES_MACVLAN=0
  DROIDSPACES_FULL_EXTRAS=0
  if [[ "$DROIDSPACES_ENABLED" == "1" ]]; then
    DROIDSPACES_PIDS_REPURPOSE_NET_PRIO=1
    DROIDSPACES_CORE_NAMESPACES=1
    DROIDSPACES_MACVLAN=1
    DROIDSPACES_FULL_EXTRAS=1
  fi

  # Reuse the already-proven parity integration verbatim when the complete
  # parity set is selected; partial combinations use the componentized helper.
  if [[ "$DROIDSPACES_ENABLED" == "1" && "$USE_NTSYNC" == "1" && "$USE_BBG" == "1" &&
        "$USE_REKERNEL" == "1" && "$USE_NETWORKING" == "1" && "$USE_CVE" == "1" ]]; then
    OS3_PARITY_EXTRAS=1
  else
    OS3_PARITY_EXTRAS=0
    if [[ "$USE_NTSYNC" == "1" || "$USE_BBG" == "1" || "$USE_REKERNEL" == "1" ||
          "$USE_NETWORKING" == "1" || "$USE_CVE" == "1" ]]; then
      SELECTED_EXTRAS=1
    fi
  fi

  if [[ "$ROOT_MODE" == "bakasu-susfs" && "$SUSFS_EXTRA_FEATURES" == "1" &&
        "$USE_NOMOUNT" == "1" && "$DROIDSPACES_ENABLED" == "1" &&
        "$USE_NTSYNC" == "1" && "$USE_BBG" == "1" && "$USE_REKERNEL" == "1" &&
        "$USE_NETWORKING" == "1" && "$USE_CVE" == "1" ]]; then
    EXACT_LKG_SELECTION=1
  fi
else
  # Historical/LKG behavior: these three sources were always integrated.
  USE_BAKASU=1
  USE_SUSFS=1
  USE_NOMOUNT=1
  SUSFS_EXTRA_FEATURES=1
  DROIDSPACES_ENABLED="$DROIDSPACES_FULL_EXTRAS"
  USE_NTSYNC="$OS3_PARITY_EXTRAS"
  USE_BBG="$OS3_PARITY_EXTRAS"
  USE_REKERNEL="$OS3_PARITY_EXTRAS"
  USE_NETWORKING="$OS3_PARITY_EXTRAS"
  USE_CVE="$OS3_PARITY_EXTRAS"
  if [[ "$OS3_PARITY_EXTRAS" == "1" && "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
    EXACT_LKG_SELECTION=1
  fi
fi

for pair in   "XIAOMI_OS4_ENABLE_CGROUP_PIDS:$DROIDSPACES_PIDS"   "XIAOMI_OS4_PIDS_REUSE_NET_PRIO_SLOT:$DROIDSPACES_PIDS_REUSE_NET_PRIO"   "XIAOMI_OS4_PIDS_REPURPOSE_NET_PRIO:$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO"   "XIAOMI_OS4_DROIDSPACES_CORE_NAMESPACES:$DROIDSPACES_CORE_NAMESPACES"   "XIAOMI_OS4_DROIDSPACES_MACVLAN:$DROIDSPACES_MACVLAN"   "XIAOMI_OS4_DROIDSPACES_FULL_EXTRAS:$DROIDSPACES_FULL_EXTRAS"   "XIAOMI_OS4_OS3_PARITY_EXTRAS:$OS3_PARITY_EXTRAS"; do
  check_bool "${pair%%:*}" "${pair#*:}"
done

if [[ "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
  [[ "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]] || {
    echo "::error::Full DroidSpaces extras require validated CoreNS + PIDs repurpose baseline"; exit 1;
  }
  DROIDSPACES_MACVLAN=1
fi
[[ "$DROIDSPACES_PIDS_REUSE_NET_PRIO" == "0" || "$DROIDSPACES_PIDS" == "1" ]] || {
  echo "::error::PIDs net_prio slot reuse requires XIAOMI_OS4_ENABLE_CGROUP_PIDS=1"; exit 1;
}
if [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && ( "$DROIDSPACES_PIDS" != "0" || "$DROIDSPACES_PIDS_REUSE_NET_PRIO" != "0" ) ]]; then
  echo "::error::PIDs net_prio repurpose mode keeps CONFIG_CGROUP_PIDS=n and cannot be combined with other PIDs modes"; exit 1
fi
if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
  [[ "$DROIDSPACES_FULL_EXTRAS" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]] || {
    echo "::error::Full parity integration requires the validated Full Extras/CoreNS/PIDs baseline"; exit 1;
  }
fi

echo "[OS4] selectable build: $CUSTOM_SELECTABLE"
echo "[OS4] Root mode: $ROOT_MODE (BakaSU=$USE_BAKASU SUSFS=$USE_SUSFS extras=$SUSFS_EXTRA_FEATURES)"
echo "[OS4] NoMount: $USE_NOMOUNT"
echo "[OS4] DroidSpaces: $DROIDSPACES_ENABLED"
echo "[OS4] NTSync: $USE_NTSYNC"
echo "[OS4] BBG: $USE_BBG"
echo "[OS4] Re-Kernel: $USE_REKERNEL"
echo "[OS4] Networking: $USE_NETWORKING"
echo "[OS4] CVE chain: $USE_CVE"
echo "[OS4] exact verified LKG selection: $EXACT_LKG_SELECTION"
echo "[OS4] DroidSpaces PIDs controller analysis: $DROIDSPACES_PIDS"
echo "[OS4] DroidSpaces PIDs reuse net_prio slot: $DROIDSPACES_PIDS_REUSE_NET_PRIO"
echo "[OS4] DroidSpaces PIDs repurpose net_prio KMI identity: $DROIDSPACES_PIDS_REPURPOSE_NET_PRIO"
echo "[OS4] DroidSpaces core PID/IPC namespaces with pinned 6.12 kABI patch: $DROIDSPACES_CORE_NAMESPACES"
echo "[OS4] DroidSpaces optional Macvlan support: $DROIDSPACES_MACVLAN"
echo "[OS4] DroidSpaces full remaining extras: $DROIDSPACES_FULL_EXTRAS"
echo "[OS4] legacy full parity helper: $OS3_PARITY_EXTRAS; partial extras helper: $SELECTED_EXTRAS"

# Export normalized/effective values so component helpers see the resolved
# feature selection rather than the original raw workflow inputs.
export XIAOMI_OS4_USE_NTSYNC="$USE_NTSYNC"
export XIAOMI_OS4_USE_BBG="$USE_BBG"
export XIAOMI_OS4_USE_REKERNEL="$USE_REKERNEL"
export XIAOMI_OS4_USE_NETWORKING="$USE_NETWORKING"
export XIAOMI_OS4_USE_CVE="$USE_CVE"

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

# The first feature build uses only commits that passed the source/Kconfig preflight.
# Stop if upstream history cannot supply the exact object; never substitute branch HEAD.
SUSFS_SHA="N/A"
BAKASU_SHA="N/A"
NOMOUNT_SHA="N/A"
DROIDSPACES_SHA="N/A"
[[ "$USE_SUSFS" != "1" ]] || SUSFS_SHA="${OS4_SUSFS_COMMIT:?missing OS4_SUSFS_COMMIT}"
[[ "$USE_BAKASU" != "1" ]] || BAKASU_SHA="${OS4_BAKASU_COMMIT:?missing OS4_BAKASU_COMMIT}"
[[ "$USE_NOMOUNT" != "1" ]] || NOMOUNT_SHA="${OS4_NOMOUNT_COMMIT:?missing OS4_NOMOUNT_COMMIT}"
[[ "$DROIDSPACES_CORE_NAMESPACES" != "1" ]] || DROIDSPACES_SHA="${OS4_DROIDSPACES_COMMIT:?missing OS4_DROIDSPACES_COMMIT}"
checkout_locked() {
  local url="$1" ref="$2" sha="$3" dir="$4"
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  if ! git -C "$dir" fetch -q --depth=1 origin "$sha"; then
    # Some servers refuse single-SHA shallow fetch. The pinned branch HEAD
    # is usable only if it still equals the audit-approved commit.
    git -C "$dir" fetch -q --depth=1 origin "refs/heads/$ref"
  fi
  git -C "$dir" checkout -q --detach FETCH_HEAD
  [[ "$(git -C "$dir" rev-parse HEAD)" == "$sha" ]] || {
    echo "::error::Upstream commit drift for $url; refuse unreviewed code"
    exit 1
  }
}
echo "[OS4] 固定已审核上游提交，不随上游 HEAD 漂移"
if [[ "$USE_SUSFS" == "1" ]]; then
  checkout_locked "$OS4_SUSFS_REPO" "$OS4_SUSFS_BRANCH" "$SUSFS_SHA" "$STAGE/susfs"
fi
if [[ "$USE_BAKASU" == "1" ]]; then
  checkout_locked "$OS4_BAKASU_REPO" "$OS4_BAKASU_REF" "$BAKASU_SHA" "$STAGE/bakasu"
fi
if [[ "$USE_NOMOUNT" == "1" ]]; then
  checkout_locked "$OS4_NOMOUNT_REPO" "$OS4_NOMOUNT_REF" "$NOMOUNT_SHA" "$SRC/NoMount"
fi
if [[ "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
  checkout_locked "$OS4_DROIDSPACES_REPO" "main" "$DROIDSPACES_SHA" "$STAGE/droidspaces"
fi

if [[ "$USE_SUSFS" == "1" ]]; then
# SUSFS's patch only edits existing kernel sources; its extra .c/.h files are
# shipped separately and MUST be installed before Image compilation.
# The old proven Gold integration copied both trees; the first OS4 feature
# run omitted them and kernel/kallsyms.c failed to find linux/susfs_def.h.
SUSFS_ASSETS="$STAGE/susfs/kernel_patches"
[[ -d "$SUSFS_ASSETS/fs" && -d "$SUSFS_ASSETS/include/linux" ]] || {
  echo "::error::Pinned SUSFS companion source directories are missing"; exit 1;
}
for required in \
  "$SUSFS_ASSETS/include/linux/susfs_def.h" \
  "$SUSFS_ASSETS/include/linux/susfs.h" \
  "$SUSFS_ASSETS/fs/susfs.c"; do
  [[ -s "$required" ]] || {
    echo "::error::Pinned SUSFS companion file missing: $required"; exit 1;
  }
done
shopt -s nullglob
for kind in fs include/linux; do
  files=( "$SUSFS_ASSETS/$kind/"* )
  (( ${#files[@]} > 0 )) || {
    echo "::error::No SUSFS companion files under $kind"; exit 1;
  }
  for file in "${files[@]}"; do
    [[ -f "$file" ]] || { echo "::error::Unexpected SUSFS asset type: $file"; exit 1; }
    target="$SRC/$kind/${file##*/}"
    if [[ -e "$target" ]] && ! cmp -s "$file" "$target"; then
      echo "::error::SUSFS companion would overwrite a different existing kernel file: $target"
      exit 1
    fi
    install -m 0644 "$file" "$target"
  done
done
shopt -u nullglob
[[ -s "$SRC/include/linux/susfs_def.h" && -s "$SRC/include/linux/susfs.h" && -s "$SRC/fs/susfs.c" ]] || {
  echo "::error::SUSFS source copy validation failed"; exit 1;
}
echo "[OS4] SUSFS .c/.h companion files installed from pinned upstream commit"

SUSFS_PATCH="$STAGE/susfs/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch"
[[ -s "$SUSFS_PATCH" ]] || { echo "::error::Pinned SUSFS patch missing"; exit 1; }
python3 "$ROOT/scripts/xiaomi-os4/susfs-task-mmu-compat.py" filter-patch "$SUSFS_PATCH" "$STAGE/susfs-filtered.patch"
patch --dry-run --batch --forward -d "$SRC" -p1 < "$STAGE/susfs-filtered.patch" > "$RESULT/patch-dryrun.log" 2>&1 || {
  tail -n 90 "$RESULT/patch-dryrun.log"; exit 1;
}
patch --batch --forward --no-backup-if-mismatch -d "$SRC" -p1 < "$STAGE/susfs-filtered.patch" > "$RESULT/patch-apply.log" 2>&1 || {
  tail -n 90 "$RESULT/patch-apply.log"; exit 1;
}
python3 "$ROOT/scripts/xiaomi-os4/susfs-task-mmu-compat.py" port-source "$SRC/fs/proc/task_mmu.c"
git -C "$SRC" diff --check -- fs/proc/task_mmu.c
if find "$SRC" -name '*.rej' -print -quit | grep -q .; then
  echo "::error::SUSFS patch produced reject files"; exit 1
fi

fi

if [[ "$USE_BAKASU" == "1" ]]; then
# The preflight verified the same BakaSU layout; make the link relative.
[[ -f "$STAGE/bakasu/kernel/Kconfig" && -f "$STAGE/bakasu/kernel/Makefile" ]] || exit 1
[[ ! -e "$SRC/drivers/kernelsu" ]] || { echo "::error::unexpected prior KernelSU integration"; exit 1; }
ln -s "$(realpath --relative-to="$SRC/drivers" "$STAGE/bakasu/kernel")" "$SRC/drivers/kernelsu"
grep -Fqx 'obj-$(CONFIG_KSU) += kernelsu/' "$SRC/drivers/Makefile" ||
  printf '\nobj-$(CONFIG_KSU) += kernelsu/\n' >> "$SRC/drivers/Makefile"
python3 - "$SRC/drivers/Kconfig" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
needle='\nendmenu'
pos=s.rfind(needle)
if pos<0 or 'source "drivers/kernelsu/Kconfig"' in s:
    raise SystemExit("Unexpected R62 drivers/Kconfig layout")
p.write_text(s[:pos]+'\nsource "drivers/kernelsu/Kconfig"\n'+s[pos:])
PY
[[ -L "$SRC/drivers/kernelsu" ]] || exit 1
grep -Fq 'source "drivers/kernelsu/Kconfig"' "$SRC/drivers/Kconfig"

fi

if [[ "$USE_NOMOUNT" == "1" ]]; then
# Reproduce the audited NoMount setup on the isolated checkout, without
# fetching mutable branch heads or allowing upstream setup.sh to change.
[[ -f "$SRC/NoMount/kernel/src/Kconfig" && -f "$SRC/NoMount/kernel/src/Makefile" ]] || exit 1
[[ ! -e "$SRC/fs/nomount" ]] || { echo "::error::unexpected prior NoMount integration"; exit 1; }
ln -s "$(realpath --relative-to="$SRC/fs" "$SRC/NoMount/kernel/src")" "$SRC/fs/nomount"
grep -Fq 'obj-$(CONFIG_NOMOUNT) += nomount/' "$SRC/fs/Makefile" ||
  printf '\nobj-$(CONFIG_NOMOUNT) += nomount/\n' >> "$SRC/fs/Makefile"
python3 - "$SRC/fs/Kconfig" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
needle='\nendmenu'
pos=s.rfind(needle)
if pos<0 or 'source "fs/nomount/Kconfig"' in s:
    raise SystemExit("Unexpected R62 fs/Kconfig layout")
p.write_text(s[:pos]+'\nsource "fs/nomount/Kconfig"\n'+s[pos:])
PY
git -C "$SRC" diff --check -- drivers/Kconfig drivers/Makefile fs/Kconfig fs/Makefile
[[ -L "$SRC/fs/nomount" ]] || exit 1
echo "[OS4] 已选择的 Root / SUSFS / NoMount 源码集成通过"

fi

if [[ "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
  echo "[OS4] Apply pinned DroidSpaces 6.12 SYSVIPC kABI patch before enabling PID/IPC namespaces"
  DROIDSPACES_KABI_PATCH="$STAGE/droidspaces/Documentation/resources/kernel-patches/GKI/kernel-6.12/001.GKI-6.12-or-above-fix_sysvipc_kabi.patch"
  [[ -s "$DROIDSPACES_KABI_PATCH" ]] || { echo "::error::Pinned DroidSpaces 6.12 kABI patch missing"; exit 1; }
  patch --dry-run --batch --forward -d "$SRC" -p1 < "$DROIDSPACES_KABI_PATCH" > "$RESULT/droidspaces-kabi-dryrun.log" 2>&1 || {
    cat "$RESULT/droidspaces-kabi-dryrun.log"; exit 1;
  }
  patch --batch --forward --no-backup-if-mismatch -d "$SRC" -p1 < "$DROIDSPACES_KABI_PATCH" > "$RESULT/droidspaces-kabi-apply.log" 2>&1 || {
    cat "$RESULT/droidspaces-kabi-apply.log"; exit 1;
  }
  grep -Fq 'char __kabi_ignored_0;' "$SRC/include/linux/sched.h"
  grep -Fq 'struct sysv_sem' "$SRC/include/linux/sched.h"
  grep -Fq 'char __kabi_ignored_1;' "$SRC/include/linux/sched.h"
  grep -Fq 'struct sysv_shm' "$SRC/include/linux/sched.h"

  # CONFIG_SYSVIPC changes task_struct-related C types. Keep the real C layout,
  # but hide only this newly enabled layout from bindgen so Xiaomi's stock
  # rust_binder.ko keeps the same Rust bindings/mangled symbol CRCs as stock.
  python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])

sched=root/"include/linux/sched.h"
s=sched.read_text()
needle="#ifdef CONFIG_SYSVIPC\n\tunion {\n\t\tchar __kabi_ignored_0;"
repl="#if defined(CONFIG_SYSVIPC) && !defined(__BINDGEN__)\n\t/* Preserve stock Rust KMI while retaining the real C SYSVIPC layout. */\n\tunion {\n\t\tchar __kabi_ignored_0;"
if s.count(needle) != 1:
    raise SystemExit("unexpected SYSVIPC kABI block in sched.h")
sched.write_text(s.replace(needle,repl,1))

sem=root/"include/linux/sem_types.h"
s=sem.read_text()
needle="#ifdef CONFIG_SYSVIPC\n\tstruct sem_undo_list *undo_list;"
repl="#if defined(CONFIG_SYSVIPC) && !defined(__BINDGEN__)\n\tstruct sem_undo_list *undo_list;"
if s.count(needle) != 1:
    raise SystemExit("unexpected SYSVIPC block in sem_types.h")
sem.write_text(s.replace(needle,repl,1))

shm=root/"include/linux/shm.h"
s=shm.read_text()
needle="#ifdef CONFIG_SYSVIPC\nstruct sysv_shm {"
repl="#if defined(CONFIG_SYSVIPC) && !defined(__BINDGEN__)\nstruct sysv_shm {"
if s.count(needle) != 1:
    raise SystemExit("unexpected SYSVIPC block in shm.h")
shm.write_text(s.replace(needle,repl,1))

# Rust Binder is a GKI module. With IPC_NS enabled its binderfs code consumes
# these two real kernel symbols. Export them; do not fake CRCs or disable
# MODVERSIONS. The ABI gate below must prove all pre-existing CRCs unchanged.
msg=root/"ipc/msgutil.c"
s=msg.read_text()
needle="#endif\n};\n\nstruct msg_msgseg {"
repl="#endif\n};\nEXPORT_SYMBOL(init_ipc_ns);\n\nstruct msg_msgseg {"
if s.count(needle) != 1:
    raise SystemExit("init_ipc_ns export insertion point not found")
msg.write_text(s.replace(needle,repl,1))

ns=root/"ipc/namespace.c"
s=ns.read_text()
needle="\t}\n}\n\nstatic inline struct ipc_namespace *to_ipc_ns"
repl="\t}\n}\nEXPORT_SYMBOL(put_ipc_ns);\n\nstatic inline struct ipc_namespace *to_ipc_ns"
if s.count(needle) != 1:
    raise SystemExit("put_ipc_ns export insertion point not found")
ns.write_text(s.replace(needle,repl,1))
PY

  grep -Fq '#if defined(CONFIG_SYSVIPC) && !defined(__BINDGEN__)' "$SRC/include/linux/sched.h"
  grep -Fq 'EXPORT_SYMBOL(init_ipc_ns);' "$SRC/ipc/msgutil.c"
  grep -Fq 'EXPORT_SYMBOL(put_ipc_ns);' "$SRC/ipc/namespace.c"
  git -C "$SRC" diff --check -- include/linux/sched.h include/linux/sem_types.h include/linux/shm.h ipc/msgutil.c ipc/namespace.c
fi

if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os3-parity-extras.sh" source
elif [[ "$SELECTED_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os4-selected-extras.sh" source
fi

if [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]]; then
  echo "[OS4] ABI-only: repurpose net_prio cgroup KMI identity as runtime pids controller"
  python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])

pids=root/"kernel/cgroup/pids.c"
t=pids.read_text()
if "pids_cgrp_id" not in t or "struct cgroup_subsys pids_cgrp_subsys" not in t:
    raise SystemExit("unexpected pids.c layout")
t=t.replace("pids_cgrp_id", "net_prio_cgrp_id")
t=t.replace("pids_cgrp_subsys", "net_prio_cgrp_subsys")
pids.write_text(t)

mk=root/"kernel/cgroup/Makefile"
t=mk.read_text()
needle="obj-$(CONFIG_CGROUP_PIDS) += pids.o"
if needle not in t:
    raise SystemExit("kernel/cgroup/Makefile pids rule not found")
t=t.replace(needle, "obj-$(CONFIG_CGROUP_NET_PRIO) += pids.o", 1)
mk.write_text(t)

nmk=root/"net/core/Makefile"
t=nmk.read_text()
needle="obj-$(CONFIG_CGROUP_NET_PRIO) += netprio_cgroup.o"
if needle not in t:
    raise SystemExit("net/core/Makefile netprio rule not found")
t=t.replace(needle, "# net_prio KMI slot repurposed by OS4 DroidSpaces ABI experiment", 1)
nmk.write_text(t)

cg=root/"kernel/cgroup/cgroup.c"
t=cg.read_text()
needle="\tRCU_INIT_POINTER(init_task.cgroups, &init_css_set);\n\n\tfor_each_subsys(ss, i) {"
repl="\tRCU_INIT_POINTER(init_task.cgroups, &init_css_set);\n\n\t/* KMI-preserving DroidSpaces experiment: expose net_prio slot as pids. */\n\tcgroup_subsys_name[net_prio_cgrp_id] = \"pids\";\n\n\tfor_each_subsys(ss, i) {"
if needle not in t:
    raise SystemExit("cgroup_init_early insertion point not found")
t=t.replace(needle,repl,1)
cg.write_text(t)
PY
  grep -qF 'obj-$(CONFIG_CGROUP_NET_PRIO) += pids.o' "$SRC/kernel/cgroup/Makefile"
  ! grep -qF 'obj-$(CONFIG_CGROUP_NET_PRIO) += netprio_cgroup.o' "$SRC/net/core/Makefile"
  grep -qF 'struct cgroup_subsys net_prio_cgrp_subsys' "$SRC/kernel/cgroup/pids.c"
  ! grep -qF 'pids_cgrp_id' "$SRC/kernel/cgroup/pids.c"
  grep -qF 'cgroup_subsys_name[net_prio_cgrp_id] = "pids";' "$SRC/kernel/cgroup/cgroup.c"
  git -C "$SRC" diff --check -- kernel/cgroup/pids.c kernel/cgroup/Makefile net/core/Makefile kernel/cgroup/cgroup.c
fi

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
if [[ "$CUSTOM_SELECTABLE" == "1" ]]; then
  if [[ "$EXACT_LKG_SELECTION" == "1" ]]; then
    FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-dscore-full-parity-kmi-4k"
  else
    FEATURE_LOCALVERSION="-android16-6-os4r62-custom-4k"
  fi
else
if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-dscore-full-parity-kmi-4k"
elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-dscore-full-kmi-4k"
elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_MACVLAN" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-dscore-macvlan-kmi-4k"
elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-dscore-kmi-4k"
elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-kmi-4k"
elif [[ "$DROIDSPACES_PIDS_REUSE_NET_PRIO" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-slot-4k"
elif [[ "$DROIDSPACES_PIDS" == "1" ]]; then
  FEATURE_LOCALVERSION="-android16-6-os4r62-dspids-4k"
else
  FEATURE_LOCALVERSION="-android16-6-os4r62-features-4k"
fi
fi
"$SRC/scripts/config" --file "$OUT/.config" --set-str LOCALVERSION "$FEATURE_LOCALVERSION"
"$SRC/scripts/config" --file "$OUT/.config" --disable LOCALVERSION_AUTO
if [[ "$CUSTOM_SELECTABLE" == "0" ]]; then
  "$SRC/scripts/config" --file "$OUT/.config" \
    --enable KSU --enable KSU_SUSFS --enable KSU_SUSFS_SUS_MAP \
    --disable KSU_TRACEPOINT_HOOK --enable NOMOUNT
else
  if [[ "$USE_BAKASU" == "1" ]]; then
    "$SRC/scripts/config" --file "$OUT/.config" --enable KSU
    if [[ "$USE_SUSFS" == "1" ]]; then
      "$SRC/scripts/config" --file "$OUT/.config" \
        --enable KSU_SUSFS --disable KSU_TRACEPOINT_HOOK \
        --enable KSU_SUSFS_SUS_PATH --enable KSU_SUSFS_SUS_MOUNT \
        --enable KSU_SUSFS_SUS_KSTAT --enable KSU_SUSFS_ENABLE_LOG
      if [[ "$SUSFS_EXTRA_FEATURES" == "1" ]]; then
        "$SRC/scripts/config" --file "$OUT/.config" \
          --enable KSU_SUSFS_SPOOF_UNAME \
          --enable KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS \
          --enable KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG \
          --enable KSU_SUSFS_OPEN_REDIRECT \
          --enable KSU_SUSFS_SUS_MAP
      else
        "$SRC/scripts/config" --file "$OUT/.config" \
          --disable KSU_SUSFS_SPOOF_UNAME \
          --disable KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS \
          --disable KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG \
          --disable KSU_SUSFS_OPEN_REDIRECT \
          --disable KSU_SUSFS_SUS_MAP
      fi
    else
      "$SRC/scripts/config" --file "$OUT/.config" \
        --disable KSU_SUSFS --enable KSU_TRACEPOINT_HOOK
    fi
  fi
  if [[ "$USE_NOMOUNT" == "1" ]]; then
    "$SRC/scripts/config" --file "$OUT/.config" --enable NOMOUNT
  fi
fi
if [[ "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
  "$SRC/scripts/config" --file "$OUT/.config" \
    --enable SYSVIPC --enable POSIX_MQUEUE --enable IPC_NS --enable PID_NS
fi
if [[ "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
  "$SRC/scripts/config" --file "$OUT/.config" \
    --enable DEVTMPFS \
    --enable MACVLAN \
    --enable IP6_NF_NAT \
    --enable IP6_NF_TARGET_MASQUERADE \
    --enable USER_NS
elif [[ "$DROIDSPACES_MACVLAN" == "1" ]]; then
  "$SRC/scripts/config" --file "$OUT/.config" --enable MACVLAN
fi
if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os3-parity-extras.sh" config
elif [[ "$SELECTED_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os4-selected-extras.sh" config
fi
if [[ "$DROIDSPACES_PIDS" == "1" ]]; then
  "$SRC/scripts/config" --file "$OUT/.config" --enable CGROUP_PIDS
  if [[ "$DROIDSPACES_PIDS_REUSE_NET_PRIO" == "1" ]]; then
    "$SRC/scripts/config" --file "$OUT/.config" --disable CGROUP_NET_PRIO
  fi
else
  "$SRC/scripts/config" --file "$OUT/.config" --disable CGROUP_PIDS
  if [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]]; then
    "$SRC/scripts/config" --file "$OUT/.config" --enable CGROUP_NET_PRIO
  fi
fi
make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 -j"$BUILD_JOBS" olddefconfig >> "$RESULT/config-build.log" 2>&1 || {
  tail -n 100 "$RESULT/config-build.log"; exit 1;
}
if [[ "$CUSTOM_SELECTABLE" == "0" ]]; then
  for cfg in CONFIG_KSU CONFIG_KSU_SUSFS CONFIG_KSU_SUSFS_SUS_MAP CONFIG_NOMOUNT; do
    grep -qx "$cfg=y" "$OUT/.config" || { echo "::error::Required feature $cfg was not resolved to y"; exit 1; }
  done
  grep -qx '# CONFIG_KSU_TRACEPOINT_HOOK is not set' "$OUT/.config" || {
    echo "::error::SUSFS Inline Hook requires tracepoint hook disabled"; exit 1;
  }
else
  if [[ "$USE_BAKASU" == "1" ]]; then
    grep -qx 'CONFIG_KSU=y' "$OUT/.config" || { echo "::error::BakaSU CONFIG_KSU did not resolve"; exit 1; }
    if [[ "$USE_SUSFS" == "1" ]]; then
      for cfg in CONFIG_KSU_SUSFS CONFIG_KSU_SUSFS_SUS_PATH CONFIG_KSU_SUSFS_SUS_MOUNT CONFIG_KSU_SUSFS_SUS_KSTAT CONFIG_KSU_SUSFS_ENABLE_LOG; do
        grep -qx "$cfg=y" "$OUT/.config" || { echo "::error::SUSFS core feature did not resolve: $cfg"; exit 1; }
      done
      grep -qx '# CONFIG_KSU_TRACEPOINT_HOOK is not set' "$OUT/.config" || { echo "::error::SUSFS mode requires tracepoint hook disabled"; exit 1; }
      for cfg in CONFIG_KSU_SUSFS_SPOOF_UNAME CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG CONFIG_KSU_SUSFS_OPEN_REDIRECT CONFIG_KSU_SUSFS_SUS_MAP; do
        if [[ "$SUSFS_EXTRA_FEATURES" == "1" ]]; then
          grep -qx "$cfg=y" "$OUT/.config" || { echo "::error::SUSFS extra feature did not resolve: $cfg"; exit 1; }
        else
          ! grep -qx "$cfg=y" "$OUT/.config" || { echo "::error::SUSFS extra feature unexpectedly enabled: $cfg"; exit 1; }
        fi
      done
    else
      grep -qx 'CONFIG_KSU_TRACEPOINT_HOOK=y' "$OUT/.config" || { echo "::error::BakaSU-only mode requires tracepoint hook"; exit 1; }
      ! grep -qx 'CONFIG_KSU_SUSFS=y' "$OUT/.config" || { echo "::error::SUSFS unexpectedly enabled in BakaSU-only mode"; exit 1; }
    fi
  else
    ! grep -qx 'CONFIG_KSU=y' "$OUT/.config" || { echo "::error::Root mode none unexpectedly enabled CONFIG_KSU"; exit 1; }
  fi
  if [[ "$USE_NOMOUNT" == "1" ]]; then
    grep -qx 'CONFIG_NOMOUNT=y' "$OUT/.config" || { echo "::error::NoMount did not resolve"; exit 1; }
  else
    ! grep -qx 'CONFIG_NOMOUNT=y' "$OUT/.config" || { echo "::error::NoMount unexpectedly enabled"; exit 1; }
  fi
fi
if [[ "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
  for cfg in CONFIG_SYSVIPC CONFIG_POSIX_MQUEUE CONFIG_IPC_NS CONFIG_PID_NS; do
    grep -qx "$cfg=y" "$OUT/.config" || {
      echo "::error::DroidSpaces core namespace config did not resolve: $cfg"; exit 1;
    }
  done
fi
if [[ "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
  echo "[OS4] Full Extras resolved Kconfig:"
  grep -E '^(CONFIG_DEVTMPFS|CONFIG_MACVLAN|CONFIG_IP6_NF_NAT|CONFIG_IP6_NF_TARGET_MASQUERADE|CONFIG_USER_NS)=' "$OUT/.config" || true
  for cfg in CONFIG_DEVTMPFS CONFIG_MACVLAN CONFIG_IP6_NF_NAT CONFIG_IP6_NF_TARGET_MASQUERADE CONFIG_USER_NS; do
    grep -qx "$cfg=y" "$OUT/.config" || {
      actual="$(grep -E "^$cfg=|^# $cfg is not set" "$OUT/.config" || echo '<absent>')"
      echo "::error::DroidSpaces full-extra config did not resolve: $cfg (actual: $actual)"; exit 1;
    }
  done
elif [[ "$DROIDSPACES_MACVLAN" == "1" ]]; then
  grep -qx 'CONFIG_MACVLAN=y' "$OUT/.config" || {
    echo "::error::DroidSpaces Macvlan config did not resolve to y"; exit 1;
  }
fi
if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os3-parity-extras.sh" validate
elif [[ "$SELECTED_EXTRAS" == "1" ]]; then
  bash "$ROOT/scripts/xiaomi-os4/apply-os4-selected-extras.sh" validate
fi
cp "$OUT/.config" "$RESULT/final.config"
grep -qx 'CONFIG_MODVERSIONS=y' "$OUT/.config" || { echo "::error::baseline requires MODVERSIONS"; exit 1; }
if [[ "$DROIDSPACES_PIDS" == "1" ]]; then
  grep -qx 'CONFIG_CGROUP_PIDS=y' "$OUT/.config" || {
    echo "::error::DroidSpaces PIDs analysis requested but CONFIG_CGROUP_PIDS did not resolve to y"; exit 1;
  }
  if [[ "$DROIDSPACES_PIDS_REUSE_NET_PRIO" == "1" ]]; then
    grep -qx '# CONFIG_CGROUP_NET_PRIO is not set' "$OUT/.config" || {
      echo "::error::PIDs slot-reuse experiment requested but CONFIG_CGROUP_NET_PRIO is still enabled"; exit 1;
    }
    grep -qx 'CONFIG_CGROUP_NET_CLASSID=y' "$OUT/.config" || {
      echo "::error::CONFIG_CGROUP_NET_CLASSID must remain enabled so SOCK_CGROUP_DATA stays present"; exit 1;
    }
    grep -qx 'CONFIG_SOCK_CGROUP_DATA=y' "$OUT/.config" || {
      echo "::error::SOCK_CGROUP_DATA disappeared while reusing net_prio slot"; exit 1;
    }
  fi
else
  grep -qx '# CONFIG_CGROUP_PIDS is not set' "$OUT/.config" || {
    echo "::error::unexpected PIDs feature in baseline"; exit 1;
  }
  if [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]]; then
    grep -qx 'CONFIG_CGROUP_NET_PRIO=y' "$OUT/.config" || { echo "::error::repurpose experiment requires CONFIG_CGROUP_NET_PRIO=y"; exit 1; }
    grep -qx 'CONFIG_CGROUP_NET_CLASSID=y' "$OUT/.config" || { echo "::error::CONFIG_CGROUP_NET_CLASSID must stay enabled"; exit 1; }
    grep -qx 'CONFIG_SOCK_CGROUP_DATA=y' "$OUT/.config" || { echo "::error::CONFIG_SOCK_CGROUP_DATA must stay enabled"; exit 1; }
  fi
fi
echo "[OS4] Building R62 Image with selected feature set (custom combinations are fastboot-boot test only)"
start="$(date +%s)"
if ! make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 \
  CC="$CLANG_CC" HOSTCC="$CLANG_CC" -j"$BUILD_JOBS" Image > "$RESULT/kernel-build.log" 2>&1; then
  echo "::error::R62 feature Image failed"
  # Parallel make can keep printing successful CC lines after the first compiler
  # error, pushing the real diagnostic out of a simple tail. Extract concise
  # error contexts from the complete local log without uploading that huge log.
  python3 - "$RESULT/kernel-build.log" "$RESULT/kernel-error-context.txt" <<'PY'
from pathlib import Path
import re, sys
src=Path(sys.argv[1]).read_text(errors="replace").splitlines()
pat=re.compile(r"(fatal error:|(^|\s)error:|undefined reference|ld\.lld: error|No rule to make target|No such file or directory)", re.I)
hits=[i for i,line in enumerate(src) if pat.search(line)]
out=[]
seen=set()
for i in hits[:30]:
    a=max(0,i-4); b=min(len(src),i+6)
    key=(a,b)
    if key in seen: continue
    seen.add(key)
    out.append(f"--- error context around line {i+1} ---")
    out.extend(src[a:b])
if not hits:
    out.append("No compiler diagnostic matched; final 180 lines follow.")
    out.extend(src[-180:])
Path(sys.argv[2]).write_text("\n".join(out)+"\n")
PY
  cat "$RESULT/kernel-error-context.txt"
  echo "::group::最后 80 行（仅辅助判断 make 退出路径）"
  tail -n 80 "$RESULT/kernel-build.log"
  echo "::endgroup::"
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
  if [[ "$CUSTOM_SELECTABLE" == "1" ]]; then
    if [[ "$EXACT_LKG_SELECTION" == "1" ]]; then
      echo "BUILD_KIND=R62_OS4_SELECTABLE_FULL_PARITY_LKG"
    else
      echo "BUILD_KIND=R62_OS4_SELECTABLE_CUSTOM"
    fi
  elif [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_FULL_OS3_PARITY_PIDS_NETPRIO_KMI_REPURPOSE_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_FULL_EXTRAS" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_FULL_PIDS_NETPRIO_KMI_REPURPOSE_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" && "$DROIDSPACES_MACVLAN" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_CORE_MACVLAN_PIDS_NETPRIO_KMI_REPURPOSE_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" && "$DROIDSPACES_CORE_NAMESPACES" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_CORE_PIDS_NETPRIO_KMI_REPURPOSE_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_PIDS_NETPRIO_KMI_REPURPOSE_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS_REUSE_NET_PRIO" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_PIDS_NETPRIO_SLOT_ANALYSIS"
  elif [[ "$DROIDSPACES_PIDS" == "1" ]]; then
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_DROIDSPACES_PIDS_ANALYSIS"
  else
    echo "BUILD_KIND=R62_BAKASU_SUSFS_NOMOUNT_ANALYSIS"
  fi
  echo "DROIDSPACES_CGROUP_PIDS=$DROIDSPACES_PIDS"
  echo "DROIDSPACES_PIDS_REUSE_NET_PRIO_SLOT=$DROIDSPACES_PIDS_REUSE_NET_PRIO"
  echo "DROIDSPACES_PIDS_REPURPOSE_NET_PRIO=$DROIDSPACES_PIDS_REPURPOSE_NET_PRIO"
  echo "DROIDSPACES_CORE_NAMESPACES=$DROIDSPACES_CORE_NAMESPACES"
  echo "DROIDSPACES_MACVLAN=$DROIDSPACES_MACVLAN"
  echo "DROIDSPACES_FULL_EXTRAS=$DROIDSPACES_FULL_EXTRAS"
  echo "OS3_PARITY_EXTRAS=$OS3_PARITY_EXTRAS"
  echo "SELECTABLE_BUILD=$CUSTOM_SELECTABLE"
  echo "ROOT_MODE=$ROOT_MODE"
  echo "SUSFS_EXTRA_FEATURES=$SUSFS_EXTRA_FEATURES"
  echo "USE_NOMOUNT=$USE_NOMOUNT"
  echo "DROIDSPACES_ENABLED=$DROIDSPACES_ENABLED"
  echo "USE_NTSYNC=$USE_NTSYNC"
  echo "USE_BBG=$USE_BBG"
  echo "USE_REKERNEL=$USE_REKERNEL"
  echo "USE_NETWORKING=$USE_NETWORKING"
  echo "USE_CVE=$USE_CVE"
  echo "EXACT_LKG_SELECTION=$EXACT_LKG_SELECTION"
  if [[ "$OS3_PARITY_EXTRAS" == "1" ]]; then
    cat "$RESULT/os3-parity-source.env"
  elif [[ "$SELECTED_EXTRAS" == "1" ]]; then
    cat "$RESULT/os4-selected-source.env"
  fi
  echo "FLASHABLE=NO"
  echo "SUSFS_COMMIT=$SUSFS_SHA"
  echo "BAKASU_COMMIT=$BAKASU_SHA"
  echo "NOMOUNT_COMMIT=$NOMOUNT_SHA"
  echo "DROIDSPACES_COMMIT=$DROIDSPACES_SHA"
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
echo "[OS4] R62 feature Image/Symvers built; NOT flashable, no AnyKernel3."
