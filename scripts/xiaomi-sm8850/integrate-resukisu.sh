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

requested_ref="${XIAOMI_RESUKISU_REF:-$RESUKISU_DEFAULT_REF}"
note "cloning ReSukiSU ref=$requested_ref (default tracks upstream main)"

# Use a full clone on purpose. ReSukiSU derives KSU_VERSION from the complete
# git rev-list count, and the generic upstream custom workflow also follows
# main rather than pinning a shallow historical checkout.
git clone "$RESUKISU_REPO" ReSukiSU
if ! git -C ReSukiSU checkout "$requested_ref"; then
  note "ref $requested_ref is not available locally; fetching it explicitly"
  git -C ReSukiSU fetch origin "$requested_ref"
  git -C ReSukiSU checkout --detach FETCH_HEAD
fi

actual="$(git -C ReSukiSU rev-parse HEAD)"
if [[ "$requested_ref" == "main" ]]; then
  upstream_main="$(git -C ReSukiSU rev-parse refs/remotes/origin/main)"
  [[ "$actual" == "$upstream_main" ]] ||
    die "ReSukiSU main drifted during checkout: HEAD=$actual origin/main=$upstream_main"
fi

commit_count="$(git -C ReSukiSU rev-list --count HEAD)"
version_code="$((30000 + commit_count + 700))"
tag_name="$(git -C ReSukiSU describe --abbrev=0 --tags 2>/dev/null || echo v4.1.0)"
branch_name="$(git -C ReSukiSU branch --show-current 2>/dev/null || true)"
[[ -n "$branch_name" ]] || branch_name="detached"

[[ -f ReSukiSU/kernel/Kconfig && -f ReSukiSU/kernel/Makefile ]] ||
  die "ReSukiSU kernel integration files missing"

note "ReSukiSU resolved: ref=$requested_ref branch=$branch_name commit=$actual tag=$tag_name version_code=$version_code"

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

note "ReSukiSU integrated built-in: CONFIG_KSU=y mode=$HOOK_MODE ref=$requested_ref commit=$actual version_code=$version_code"
