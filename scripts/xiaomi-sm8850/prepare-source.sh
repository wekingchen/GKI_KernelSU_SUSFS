#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

WORKDIR="${1:?usage: prepare-source.sh <workdir> [source-profile]}"
SOURCE_PROFILE="${2:-$DEFAULT_SOURCE_PROFILE}"
KERNEL_ROOT="$WORKDIR/kernel"

validate_source_profile "$SOURCE_PROFILE"
require_cmd repo
require_cmd git
require_cmd python3

rm -rf "$KERNEL_ROOT"
mkdir -p "$KERNEL_ROOT"
cd "$KERNEL_ROOT"

note "initializing pinned ACK build manifest"
repo init --depth=1 -u "$ACK_MANIFEST_URL" -b "$ACK_MANIFEST_BRANCH" --repo-rev=stable

actual_manifest="$(git -C .repo/manifests rev-parse HEAD)"
[[ "$actual_manifest" == "$ACK_MANIFEST_COMMIT" ]] ||
  die "manifest branch drifted: expected $ACK_MANIFEST_COMMIT got $actual_manifest"

note "rewriting common project to deprecated ACK namespace for reproducible build tooling"
python3 - "$KERNEL_ROOT/.repo/manifests" "$ACK_COMMON_SYNC_REF" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

manifest_dir = pathlib.Path(sys.argv[1])
sync_ref = sys.argv[2]
expected = "android16-6.12-2025-06"

matches = []
for path in sorted(manifest_dir.rglob("*.xml")):
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        continue
    root = tree.getroot()
    for project in root.iter("project"):
        name = project.get("name")
        proj_path = project.get("path")
        if name == "common" or proj_path == "common":
            matches.append((path, tree, project))

if len(matches) != 1:
    details = ", ".join(str(m[0]) for m in matches)
    raise SystemExit(
        f"expected exactly one common project, found {len(matches)}"
        + (f": {details}" if details else "")
    )

path, tree, project = matches[0]
old = project.get("revision")
if old not in (expected, sync_ref):
    raise SystemExit(f"unexpected common manifest revision in {path}: {old!r}")

project.set("revision", sync_ref)
tree.write(path, encoding="utf-8", xml_declaration=True)
print(f"common project file: {path}")
print(f"common manifest revision: {old} -> {sync_ref}")
PY

note "syncing pinned ACK build tree"
repo sync -c --force-sync --no-clone-bundle --no-tags -j4

actual_manifest_after="$(git -C .repo/manifests rev-parse HEAD)"
[[ "$actual_manifest_after" == "$ACK_MANIFEST_COMMIT" ]] ||
  die "manifest changed during sync: expected $ACK_MANIFEST_COMMIT got $actual_manifest_after"

case "$SOURCE_PROFILE" in
  ack-r51)
    note "source profile ack-r51: pinning official ACK common"
    git -C common fetch --depth=1 "$ACK_COMMON_REPO" "$ACK_COMMON_REF"
    fetched_common="$(git -C common rev-parse 'FETCH_HEAD^{}')"
    [[ "$fetched_common" == "$ACK_COMMON_COMMIT" ]] ||
      die "ACK tag peeled to unexpected commit: $fetched_common"
    git -C common checkout --detach "$ACK_COMMON_COMMIT"
    SOURCE_COMMON_REPO="$ACK_COMMON_REPO"
    SOURCE_COMMON_REF="$ACK_COMMON_REF"
    SOURCE_COMMON_COMMIT="$ACK_COMMON_COMMIT"
    ;;

  gold-cctv)
    note "source profile gold-cctv: replacing common/ with pinned cctv18 public GKI source"
    rm -rf common
    git clone --filter=blob:none --no-checkout --branch "$GOLD_COMMON_BRANCH" "$GOLD_COMMON_REPO" common
    git -C common fetch --depth=1 origin "$GOLD_COMMON_COMMIT"
    git -C common checkout --detach "$GOLD_COMMON_COMMIT"
    actual_gold="$(git -C common rev-parse HEAD)"
    [[ "$actual_gold" == "$GOLD_COMMON_COMMIT" ]] ||
      die "Gold-compatible common commit mismatch: expected $GOLD_COMMON_COMMIT got $actual_gold"
    SOURCE_COMMON_REPO="$GOLD_COMMON_REPO"
    SOURCE_COMMON_REF="refs/heads/$GOLD_COMMON_BRANCH"
    SOURCE_COMMON_COMMIT="$GOLD_COMMON_COMMIT"
    ;;
esac

actual_common="$(git -C common rev-parse HEAD)"
[[ "$actual_common" == "$SOURCE_COMMON_COMMIT" ]] ||
  die "common commit mismatch: expected $SOURCE_COMMON_COMMIT got $actual_common"

make_version="$(awk '
  /^VERSION = /{v=$3}
  /^PATCHLEVEL = /{p=$3}
  /^SUBLEVEL = /{s=$3}
  END{print v "." p "." s}
' common/Makefile)"
[[ "$make_version" == "$KERNEL_VERSION" ]] ||
  die "kernel Makefile version mismatch: expected $KERNEL_VERSION got $make_version"

ack_branch="$(sed -n 's/^BRANCH=//p' common/build.config.constants)"
ack_kmi="$(sed -n 's/^KMI_GENERATION=//p' common/build.config.constants)"
ack_clang="$(sed -n 's/^CLANG_VERSION=//p' common/build.config.constants)"
[[ "$ack_branch" == "android16-6.12" ]] || die "unexpected ACK branch: $ack_branch"
[[ "$ack_kmi" == "$KMI_GENERATION" ]] || die "unexpected KMI generation: $ack_kmi"
[[ "$ack_clang" == "$CLANG_VERSION" ]] || die "unexpected clang revision: $ack_clang"

xiaomi_symbols="common/gki/aarch64/symbols/xiaomi"
[[ -f "$xiaomi_symbols" ]] || die "Xiaomi GKI symbol list is missing"

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
SOURCE_PROFILE=$SOURCE_PROFILE
ACK_MANIFEST_COMMIT=$actual_manifest
SOURCE_COMMON_REPO=$SOURCE_COMMON_REPO
SOURCE_COMMON_REF=$SOURCE_COMMON_REF
SOURCE_COMMON_COMMIT=$SOURCE_COMMON_COMMIT
ACK_BRANCH=$ack_branch
KERNEL_VERSION=$make_version
KMI_GENERATION=$ack_kmi
CLANG_VERSION=$ack_clang
EOF

note "source ready: profile=$SOURCE_PROFILE common=$actual_common manifest=$actual_manifest"
