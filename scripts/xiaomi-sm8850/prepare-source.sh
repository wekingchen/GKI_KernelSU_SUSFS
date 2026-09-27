#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

WORKDIR="${1:?usage: prepare-source.sh <workdir> [source-profile]}"
SOURCE_PROFILE="${2:-$DEFAULT_SOURCE_PROFILE}"
KERNEL_ROOT="$WORKDIR/kernel"

validate_source_profile "$SOURCE_PROFILE"
require_cmd git
require_cmd python3

rm -rf "$KERNEL_ROOT"
mkdir -p "$KERNEL_ROOT"
cd "$KERNEL_ROOT"

make_version_of() {
  awk '
    /^VERSION = /{v=$3}
    /^PATCHLEVEL = /{p=$3}
    /^SUBLEVEL = /{s=$3}
    END{print v "." p "." s}
  ' "$1/Makefile"
}

verify_common_constants() {
  local common="$1"
  local make_version ack_branch ack_kmi ack_clang

  make_version="$(make_version_of "$common")"
  [[ "$make_version" == "$KERNEL_VERSION" ]] ||
    die "kernel Makefile version mismatch: expected $KERNEL_VERSION got $make_version"

  ack_branch="$(sed -n 's/^BRANCH=//p' "$common/build.config.constants")"
  ack_kmi="$(sed -n 's/^KMI_GENERATION=//p' "$common/build.config.constants")"
  ack_clang="$(sed -n 's/^CLANG_VERSION=//p' "$common/build.config.constants")"
  [[ "$ack_branch" == "android16-6.12" ]] || die "unexpected ACK branch: $ack_branch"
  [[ "$ack_kmi" == "$KMI_GENERATION" ]] || die "unexpected KMI generation: $ack_kmi"
  [[ "$ack_clang" == "$CLANG_VERSION" ]] || die "unexpected clang revision: $ack_clang"

  [[ -f "$common/gki/aarch64/symbols/xiaomi" ]] ||
    die "Xiaomi GKI symbol list is missing"

  VERIFIED_KERNEL_VERSION="$make_version"
  VERIFIED_ACK_BRANCH="$ack_branch"
  VERIFIED_KMI_GENERATION="$ack_kmi"
  VERIFIED_CLANG_VERSION="$ack_clang"
}

case "$SOURCE_PROFILE" in
  gold-cctv)
    require_cmd curl
    require_cmd unzip

    common_cache="${XIAOMI_GOLD_COMMON_CACHE:-$HOME/.cache/xiaomi-sm8850/gold-common-$GOLD_COMMON_COMMIT.git}"

    common_cache_valid() {
      [[ -d "$common_cache" ]] || return 1
      local pinned
      pinned="$(git --git-dir="$common_cache" rev-parse refs/heads/pinned 2>/dev/null || true)"
      [[ "$pinned" == "$GOLD_COMMON_COMMIT" ]] &&
      git --git-dir="$common_cache" cat-file -e "$GOLD_COMMON_COMMIT^{commit}" 2>/dev/null
    }

    if common_cache_valid; then
      note "using cached Gold common object store: $common_cache"
    else
      note "Gold common cache miss; fetching pinned source commit once"
      rm -rf "$common_cache"
      mkdir -p "$(dirname "$common_cache")"
      git init --bare "$common_cache"
      git --git-dir="$common_cache" remote add origin "$GOLD_COMMON_REPO"
      git --git-dir="$common_cache" fetch --depth=1 --no-tags origin "$GOLD_COMMON_COMMIT"

      # FETCH_HEAD alone is not a persistent reachable ref. Without this,
      # cloning the bare cache treats it as an empty repository and drops the
      # fetched commit objects.
      git --git-dir="$common_cache" update-ref refs/heads/pinned "$GOLD_COMMON_COMMIT"

      common_cache_valid || die "Gold common cache does not contain pinned reachable commit"
    fi

    # Clone a fresh worktree from the immutable cached object store for every
    # build. This preserves the clean-source guarantee while avoiding the
    # multi-minute network fetch of the same pinned common commit.
    note "source profile gold-cctv: creating clean common worktree from cache"
    git clone --no-checkout "$common_cache" common
    git -C common remote set-url origin "$GOLD_COMMON_REPO"
    git -C common checkout --detach "$GOLD_COMMON_COMMIT"
    actual_common="$(git -C common rev-parse HEAD)"
    [[ "$actual_common" == "$GOLD_COMMON_COMMIT" ]] ||
      die "Gold-compatible common commit mismatch: expected $GOLD_COMMON_COMMIT got $actual_common"

    verify_common_constants "$KERNEL_ROOT/common"

    toolchain_cache="${XIAOMI_GOLD_TOOLCHAIN_CACHE:-$HOME/.cache/xiaomi-sm8850/gold-toolchain-$CLANG_VERSION}"

    toolchain_cache_valid() {
      [[ -x "$toolchain_cache/clang19/bin/clang" ]] &&
      [[ -x "$toolchain_cache/rust/bin/rustc" ]] &&
      [[ -x "$toolchain_cache/rust/bin/bindgen" ]] &&
      [[ -x "$toolchain_cache/build-tools/bin/pahole" ]]
    }

    if toolchain_cache_valid; then
      note "using cached Gold toolchain: $toolchain_cache"
    else
      note "Gold toolchain cache miss; downloading pinned r536225 bundle"
      rm -rf "$toolchain_cache"
      mkdir -p "$toolchain_cache/clang19" "$toolchain_cache/rust"

      download_asset() {
        local name="$1" out="$2"
        curl --fail --location --retry 5 --retry-all-errors \
          --connect-timeout 30 \
          "$GOLD_TOOLCHAIN_BASE/$name" \
          -o "$out"
      }

      download_asset "$GOLD_CLANG_ARCHIVE" "$toolchain_cache/clang.zip"
      download_asset "$GOLD_RUST_ARCHIVE" "$toolchain_cache/rust.zip"
      download_asset "$GOLD_BUILD_TOOLS_ARCHIVE" "$toolchain_cache/build-tools.zip"

      unzip -q "$toolchain_cache/clang.zip" -d "$toolchain_cache/clang19"
      unzip -q "$toolchain_cache/rust.zip" -d "$toolchain_cache/rust"
      # cctv18's build-tools.zip already contains a top-level build-tools/
      # directory. Extract it at TOOLROOT.
      unzip -q "$toolchain_cache/build-tools.zip" -d "$toolchain_cache"
      rm -f "$toolchain_cache/"*.zip

      toolchain_cache_valid || die "downloaded Gold toolchain cache is incomplete"
    fi

    ln -s "$toolchain_cache" "$KERNEL_ROOT/gold-toolchain"

    [[ -x "$KERNEL_ROOT/gold-toolchain/clang19/bin/clang" ]] ||
      die "Gold clang bundle missing clang"
    [[ -x "$KERNEL_ROOT/gold-toolchain/rust/bin/rustc" ]] ||
      die "Gold rust bundle missing rustc"
    [[ -x "$KERNEL_ROOT/gold-toolchain/rust/bin/bindgen" ]] ||
      die "Gold rust bundle missing bindgen"
    [[ -d "$KERNEL_ROOT/gold-toolchain/build-tools/bin" ]] ||
      die "Gold build-tools bundle extracted to unexpected layout"
    [[ -x "$KERNEL_ROOT/gold-toolchain/build-tools/bin/pahole" ]] ||
      die "Gold build-tools bundle missing pahole"

    clang_line="$("$KERNEL_ROOT/gold-toolchain/clang19/bin/clang" --version | head -n1)"
    [[ "$clang_line" == *"14043575"* && "$clang_line" == *"clang version 19.0.1"* ]] ||
      die "unexpected Gold clang bundle: $clang_line"

    SOURCE_COMMON_REPO="$GOLD_COMMON_REPO"
    SOURCE_COMMON_REF="refs/heads/$GOLD_COMMON_BRANCH"
    SOURCE_COMMON_COMMIT="$GOLD_COMMON_COMMIT"
    SOURCE_BUILD_MODE=make-image
    SOURCE_KMI_MODE=modversions-gendwarfksyms
    SOURCE_MANIFEST_COMMIT=not-used
    ;;

  ack-r51)
    require_cmd repo

    note "source profile ack-r51: initializing pinned ACK build manifest"
    repo init --depth=1 -u "$ACK_MANIFEST_URL" -b "$ACK_MANIFEST_BRANCH" --repo-rev=stable

    actual_manifest="$(git -C .repo/manifests rev-parse HEAD)"
    [[ "$actual_manifest" == "$ACK_MANIFEST_COMMIT" ]] ||
      die "manifest branch drifted: expected $ACK_MANIFEST_COMMIT got $actual_manifest"

    note "rewriting common project to deprecated ACK namespace"
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
        if project.get("name") == "common" or project.get("path") == "common":
            matches.append((path, tree, project))

if len(matches) != 1:
    raise SystemExit(f"expected exactly one common project, found {len(matches)}")

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

    note "pinning official ACK common to $ACK_COMMON_REF"
    git -C common fetch --depth=1 "$ACK_COMMON_REPO" "$ACK_COMMON_REF"
    fetched_common="$(git -C common rev-parse 'FETCH_HEAD^{}')"
    [[ "$fetched_common" == "$ACK_COMMON_COMMIT" ]] ||
      die "ACK tag peeled to unexpected commit: $fetched_common"
    git -C common checkout --detach "$ACK_COMMON_COMMIT"

    actual_common="$(git -C common rev-parse HEAD)"
    [[ "$actual_common" == "$ACK_COMMON_COMMIT" ]] ||
      die "ACK common commit mismatch: expected $ACK_COMMON_COMMIT got $actual_common"

    verify_common_constants "$KERNEL_ROOT/common"

    python3 - "$KERNEL_ROOT/common/BUILD.bazel" <<'PY'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text()
i = s.find('name = "kernel_aarch64"')
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

    SOURCE_COMMON_REPO="$ACK_COMMON_REPO"
    SOURCE_COMMON_REF="$ACK_COMMON_REF"
    SOURCE_COMMON_COMMIT="$ACK_COMMON_COMMIT"
    SOURCE_BUILD_MODE=kleaf-dist
    SOURCE_KMI_MODE=kleaf-strict
    SOURCE_MANIFEST_COMMIT="$actual_manifest"
    ;;
esac

cat > "$WORKDIR/source-provenance.env" <<EOF
SOURCE_PROFILE=$SOURCE_PROFILE
SOURCE_BUILD_MODE=$SOURCE_BUILD_MODE
SOURCE_KMI_MODE=$SOURCE_KMI_MODE
SOURCE_MANIFEST_COMMIT=$SOURCE_MANIFEST_COMMIT
SOURCE_COMMON_REPO=$SOURCE_COMMON_REPO
SOURCE_COMMON_REF=$SOURCE_COMMON_REF
SOURCE_COMMON_COMMIT=$SOURCE_COMMON_COMMIT
ACK_BRANCH=$VERIFIED_ACK_BRANCH
KERNEL_VERSION=$VERIFIED_KERNEL_VERSION
KMI_GENERATION=$VERIFIED_KMI_GENERATION
CLANG_VERSION=$VERIFIED_CLANG_VERSION
EOF

note "source ready: profile=$SOURCE_PROFILE mode=$SOURCE_BUILD_MODE common=$SOURCE_COMMON_COMMIT"
