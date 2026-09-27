#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

WORKDIR="${1:?usage: prepare-source.sh <workdir>}"
KERNEL_ROOT="$WORKDIR/kernel"

require_cmd repo
require_cmd git
require_cmd python3

rm -rf "$KERNEL_ROOT"
mkdir -p "$KERNEL_ROOT"
cd "$KERNEL_ROOT"

note "initializing pinned ACK manifest tooling snapshot"
repo init --depth=1   -u "$ACK_MANIFEST_URL"   -b "$ACK_MANIFEST_BRANCH"   --repo-rev="$ACK_MANIFEST_COMMIT"

actual_manifest="$(git -C .repo/manifests rev-parse HEAD)"
[[ "$actual_manifest" == "$ACK_MANIFEST_COMMIT" ]] ||
  die "manifest commit mismatch: expected $ACK_MANIFEST_COMMIT got $actual_manifest"

note "syncing ACK build tree"
repo sync -c --force-sync --no-clone-bundle --no-tags -j4

note "pinning common to $ACK_COMMON_REF / $ACK_COMMON_COMMIT"
git -C common fetch --depth=1 "$ACK_COMMON_REPO" "$ACK_COMMON_REF"
fetched_common="$(git -C common rev-parse FETCH_HEAD)"
[[ "$fetched_common" == "$ACK_COMMON_COMMIT" ]] ||
  die "ACK tag resolved to unexpected commit: $fetched_common"
git -C common checkout --detach "$ACK_COMMON_COMMIT"
actual_common="$(git -C common rev-parse HEAD)"
[[ "$actual_common" == "$ACK_COMMON_COMMIT" ]] ||
  die "common commit mismatch: expected $ACK_COMMON_COMMIT got $actual_common"

make_version="$(awk '
  /^VERSION = /{v=$3}
  /^PATCHLEVEL = /{p=$3}
  /^SUBLEVEL = /{s=$3}
  END{print v "." p "." s}
' common/Makefile)"
[[ "$make_version" == "$KERNEL_VERSION" ]] ||
  die "kernel Makefile version mismatch: expected $KERNEL_VERSION got $make_version"

# shellcheck disable=SC1091
source common/build.config.constants
[[ "$BRANCH" == "android16-6.12" ]] || die "unexpected ACK BRANCH=$BRANCH"
[[ "$KMI_GENERATION" == "$KMI_GENERATION" ]] || true
[[ "${CLANG_VERSION:-}" == "$CLANG_VERSION" ]] || true

# The sourced names collide with our config names. Read authoritative values
# again without relying on shell variable shadowing.
ack_kmi="$(sed -n 's/^KMI_GENERATION=//p' common/build.config.constants)"
ack_clang="$(sed -n 's/^CLANG_VERSION=//p' common/build.config.constants)"
[[ "$ack_kmi" == "5" ]] || die "unexpected KMI generation: $ack_kmi"
[[ "$ack_clang" == "r536225" ]] || die "unexpected clang revision: $ack_clang"

xiaomi_symbols="common/gki/aarch64/symbols/xiaomi"
[[ -f "$xiaomi_symbols" ]] || die "Xiaomi GKI symbol list is missing"
grep -q '__tracepoint_android_vh_health_report' "$xiaomi_symbols" ||
  die "ACK snapshot lacks Xiaomi health_report KMI symbol"
grep -q 'task_work_add' "$xiaomi_symbols" ||
  die "ACK snapshot lacks later Xiaomi task_work_add KMI symbol"

python3 - "$KERNEL_ROOT/common/BUILD.bazel" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
needle = 'name = "kernel_aarch64"'
i = s.find(needle)
if i < 0:
    raise SystemExit("kernel_aarch64 target not found")
chunk = s[i:i+7000]
for required in (
    "kmi_enforced = True",
    "kmi_symbol_list_strict_mode = True",
    "trim_nonlisted_kmi = True",
):
    if required not in chunk:
        raise SystemExit(f"kernel_aarch64 lost required KMI guardrail: {required}")
PY

cat > "$WORKDIR/source-provenance.env" <<EOF
ACK_MANIFEST_COMMIT=$actual_manifest
ACK_COMMON_COMMIT=$actual_common
ACK_COMMON_REF=$ACK_COMMON_REF
ACK_BRANCH=android16-6.12
KERNEL_VERSION=$make_version
KMI_GENERATION=$ack_kmi
CLANG_VERSION=$ack_clang
EOF

note "source ready: common=$actual_common manifest=$actual_manifest"
