#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KERNEL_ROOT="${1:?usage: integrate-bakasu.sh <kernel-root> <tracepoint|susfs> <fragment>}"
HOOK_MODE="${2:?usage: integrate-bakasu.sh <kernel-root> <tracepoint|susfs> <fragment>}"
FRAGMENT="${3:?usage: integrate-bakasu.sh <kernel-root> <tracepoint|susfs> <fragment>}"

case "$HOOK_MODE" in tracepoint|susfs) ;; *) die "invalid BakaSU hook mode: $HOOK_MODE";; esac
[[ -d "$KERNEL_ROOT/common/drivers" ]] || die "common/drivers not found"
[[ -f "$FRAGMENT" ]] || die "config fragment not found: $FRAGMENT"

cd "$KERNEL_ROOT"
[[ ! -e BakaSU ]] || die "BakaSU checkout already exists"
[[ ! -e common/drivers/kernelsu ]] || die "drivers/kernelsu already exists"

requested_ref="${XIAOMI_BAKASU_REF:-${XIAOMI_RESUKISU_REF:-$BAKASU_DEFAULT_REF}}"
note "cloning BakaSU ref=$requested_ref (default tracks upstream main)"

# Use a full clone on purpose. BakaSU derives KSU_VERSION from the complete
# git rev-list count, and the generic upstream custom workflow also follows
# main rather than pinning a shallow historical checkout.
git clone "$BAKASU_REPO" BakaSU
if ! git -C BakaSU checkout "$requested_ref"; then
  note "ref $requested_ref is not available locally; fetching it explicitly"
  git -C BakaSU fetch origin "$requested_ref"
  git -C BakaSU checkout --detach FETCH_HEAD
fi

actual="$(git -C BakaSU rev-parse HEAD)"
if [[ "$requested_ref" == "main" ]]; then
  upstream_main="$(git -C BakaSU rev-parse refs/remotes/origin/main)"
  [[ "$actual" == "$upstream_main" ]] ||
    die "BakaSU main drifted during checkout: HEAD=$actual origin/main=$upstream_main"
fi

commit_count="$(git -C BakaSU rev-list --count HEAD)"
version_code="$((30000 + commit_count + 700))"
tag_name="$(git -C BakaSU describe --abbrev=0 --tags 2>/dev/null || echo v4.1.0)"
branch_name="$(git -C BakaSU branch --show-current 2>/dev/null || true)"
[[ -n "$branch_name" ]] || branch_name="detached"

[[ -f BakaSU/kernel/Kconfig && -f BakaSU/kernel/Makefile ]] ||
  die "BakaSU kernel integration files missing"

note "BakaSU resolved: ref=$requested_ref branch=$branch_name commit=$actual tag=$tag_name version_code=$version_code"

ln -s "$(realpath --relative-to=common/drivers BakaSU/kernel)" common/drivers/kernelsu
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

note "BakaSU integrated built-in: CONFIG_KSU=y mode=$HOOK_MODE ref=$requested_ref commit=$actual version_code=$version_code"
