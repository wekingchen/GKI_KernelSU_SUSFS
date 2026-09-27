#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KERNEL_ROOT="${1:?usage: integrate-resukisu.sh <kernel-root> <tracepoint|susfs> <fragment>}"
HOOK_MODE="${2:?usage: integrate-resukisu.sh <kernel-root> <tracepoint|susfs> <fragment>}"
FRAGMENT="${3:?usage: integrate-resukisu.sh <kernel-root> <tracepoint|susfs> <fragment>}"

case "$HOOK_MODE" in tracepoint|susfs) ;; *) die "invalid ReSukiSU hook mode: $HOOK_MODE";; esac
[[ -d "$KERNEL_ROOT/common/drivers" ]] || die "common/drivers not found"
[[ -f "$FRAGMENT" ]] || die "config fragment not found: $FRAGMENT"

cd "$KERNEL_ROOT"
[[ ! -e ReSukiSU ]] || die "ReSukiSU checkout already exists"
[[ ! -e common/drivers/kernelsu ]] || die "drivers/kernelsu already exists"

note "cloning ReSukiSU at immutable commit $RESUKISU_COMMIT"
git clone --filter=blob:none --no-checkout "$RESUKISU_REPO" ReSukiSU
git -C ReSukiSU fetch --depth=1 origin "$RESUKISU_COMMIT"
git -C ReSukiSU checkout --detach "$RESUKISU_COMMIT"
actual="$(git -C ReSukiSU rev-parse HEAD)"
[[ "$actual" == "$RESUKISU_COMMIT" ]] ||
  die "ReSukiSU commit mismatch: expected $RESUKISU_COMMIT got $actual"
[[ -f ReSukiSU/kernel/Kconfig && -f ReSukiSU/kernel/Makefile ]] ||
  die "ReSukiSU kernel integration files missing"

ln -s "$(realpath --relative-to=common/drivers ReSukiSU/kernel)" common/drivers/kernelsu
grep -qF 'obj-$(CONFIG_KSU) += kernelsu/' common/drivers/Makefile ||
  printf '\nobj-$(CONFIG_KSU) += kernelsu/\n' >> common/drivers/Makefile

if ! grep -qF 'source "drivers/kernelsu/Kconfig"' common/drivers/Kconfig; then
  python3 - common/drivers/Kconfig <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
idx=s.rfind("\nendmenu")
if idx < 0:
    raise SystemExit("unable to find final endmenu in drivers/Kconfig")
s=s[:idx]+'\nsource "drivers/kernelsu/Kconfig"\n'+s[idx:]
p.write_text(s)
PY
fi

append_config "$FRAGMENT" 'CONFIG_KSU=y'
append_config "$FRAGMENT" '# CONFIG_KSU_MULTI_MANAGER_SUPPORT is not set'
append_config "$FRAGMENT" '# CONFIG_KSU_TOOLKIT_SUPPORT is not set'

if [[ "$HOOK_MODE" == "tracepoint" ]]; then
  append_config "$FRAGMENT" 'CONFIG_KSU_TRACEPOINT_HOOK=y'
  append_config "$FRAGMENT" '# CONFIG_KSU_SUSFS is not set'
else
  append_config "$FRAGMENT" 'CONFIG_KSU_SUSFS=y'
  append_config "$FRAGMENT" '# CONFIG_KSU_TRACEPOINT_HOOK is not set'
fi

note "ReSukiSU integrated built-in: CONFIG_KSU=y mode=$HOOK_MODE commit=$actual"
