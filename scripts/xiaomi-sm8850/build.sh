#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

DEVICE="${1:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
VARIANT="${2:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
WORKDIR="${3:?usage: build.sh <device> <variant> <workdir> [source-profile]}"
SOURCE_PROFILE="${4:-$DEFAULT_SOURCE_PROFILE}"

validate_device "$DEVICE"
validate_variant "$VARIANT"
validate_source_profile "$SOURCE_PROFILE"

OUT="$WORKDIR/output/$DEVICE/$VARIANT"
mkdir -p "$OUT"

bash "$XIAOMI_SCRIPT_DIR/prepare-source.sh" "$WORKDIR" "$SOURCE_PROFILE"
KERNEL_ROOT="$WORKDIR/kernel"
FRAGMENT="$KERNEL_ROOT/common/arch/arm64/configs/xiaomi_sm8850.fragment"
: > "$FRAGMENT"

case "$VARIANT" in
  base)
    note "Variant A: source=$SOURCE_PROFILE; no root integration"
    ;;
  resukisu)
    note "Variant B: source=$SOURCE_PROFILE + ReSukiSU built-in (tracepoint)"
    bash "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" tracepoint "$FRAGMENT"
    ;;
  resukisu-susfs)
    note "Variant C: source=$SOURCE_PROFILE + ReSukiSU built-in + SUSFS"
    bash "$XIAOMI_SCRIPT_DIR/integrate-resukisu.sh" "$KERNEL_ROOT" susfs "$FRAGMENT"
    bash "$XIAOMI_SCRIPT_DIR/integrate-susfs.sh" "$KERNEL_ROOT" "$FRAGMENT"
    ;;
esac

# Optional feature integration is shared by both source profiles; source-
# specific build and compatibility policy stays isolated below.
bash "$XIAOMI_SCRIPT_DIR/integrate-features.sh" "$KERNEL_ROOT" "$FRAGMENT" "$WORKDIR"

# shellcheck disable=SC1090
source "$WORKDIR/source-provenance.env"

case "$SOURCE_BUILD_MODE" in
  make-image)
    clang_bin="$KERNEL_ROOT/gold-toolchain/clang19/bin/clang"
    [[ -x "$clang_bin" ]] || die "pinned Gold clang not found: $clang_bin"
    clang_line="$("$clang_bin" --version | head -n1)"

    note "building Gold-compatible profile with standalone make/Image path"
    bash "$XIAOMI_SCRIPT_DIR/build-gold-make.sh" "$KERNEL_ROOT" "$FRAGMENT" "$OUT"

    build_target="make O=out gki_defconfig + Image"
    lto_mode="source-default (not forced by Kleaf)"
    kmi_enforced="not-applicable (Image-only make path)"
    kmi_strict="not-applicable (Image-only make path)"
    ;;

  kleaf-dist)
    cd "$KERNEL_ROOT"

    # ReSukiSU derives version metadata from its .git directory. A normal
    # Kleaf sandbox intentionally exposes only declared source inputs, so .git
    # metadata is absent and upstream Kbuild aborts. Resolve the pinned metadata
    # before entering Bazel and replace only the Git-probing block with
    # deterministic values. This ACK-only compatibility layer keeps the action
    # hermetic/cacheable; the Gold make path remains untouched.
    if [[ -d "$KERNEL_ROOT/ReSukiSU/.git" ]]; then
      ksu_kbuild="$KERNEL_ROOT/ReSukiSU/kernel/Kbuild"
      [[ -f "$ksu_kbuild" ]] || die "ReSukiSU Kbuild missing: $ksu_kbuild"

      ksu_local_version="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-list --count HEAD)"
      ksu_version="$((30000 + ksu_local_version + 700))"
      ksu_tag="$(git -C "$KERNEL_ROOT/ReSukiSU" describe --abbrev=0 --tags 2>/dev/null || echo v4.1.0)"
      ksu_commit="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-parse --short=8 HEAD)"
      ksu_branch="$(git -C "$KERNEL_ROOT/ReSukiSU" branch --show-current 2>/dev/null || true)"
      [[ -n "$ksu_branch" ]] || ksu_branch="detached"

      note "freezing ReSukiSU metadata for ACK sandbox: version=$ksu_version tag=$ksu_tag commit=$ksu_commit branch=$ksu_branch"

      python3 - "$ksu_kbuild" "$ksu_local_version" "$ksu_version" "$ksu_tag" "$ksu_commit" "$ksu_branch" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
local_version, version, tag, commit, branch = sys.argv[2:]
text = path.read_text()

start = text.find("LOCAL_GIT_EXISTS :=")
end_marker = "KSU_BRANCH_NAME := $(shell cd $(KSU_SRC); $(GIT_BIN) branch --show-current 2>/dev/null || echo \"unknown\")"
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("ReSukiSU Git metadata block layout changed; refusing unsafe ACK patch")
end += len(end_marker)

replacement = f"""# ACK/Kleaf sandbox: metadata resolved before Bazel; do not require .git.
ifdef KBUILD_EXTMOD
include $(KSU_SRC)/tools/ddk_compatible.mk
endif

KSU_LOCAL_VERSION := {local_version}
KSU_VERSION := {version}
KSU_TAG_NAME := {tag}
KSU_COMMIT_SHA := {commit}
KSU_BRANCH_NAME := {branch}"""

text = text[:start] + replacement + text[end:]
path.write_text(text)
PY

      grep -q "^KSU_VERSION := $ksu_version$" "$ksu_kbuild" ||
        die "failed to freeze ReSukiSU ACK metadata"
    fi

    clang_bin="$KERNEL_ROOT/prebuilts/clang/host/linux-x86/clang-$CLANG_VERSION/bin/clang"
    [[ -x "$clang_bin" ]] || die "pinned ACK clang not found: $clang_bin"
    clang_line="$("$clang_bin" --version | head -n1)"
    note "toolchain: $clang_line"

    python3 - common/BUILD.bazel <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
i=s.find('name = "kernel_aarch64"')
if i < 0:
    raise SystemExit("kernel_aarch64 target missing")
chunk=s[i:i+7000]
for required in ("kmi_enforced = True", "kmi_symbol_list_strict_mode = True", "trim_nonlisted_kmi = True"):
    if required not in chunk:
        raise SystemExit(f"source KMI guardrail missing before Xiaomi compatibility patch: {required}")
PY

    # Xiaomi ACK compatibility:
    # The stock R51 kernel_aarch64 target is strict GKI/KMI. The initial strict
    # build compiled cleanly but did not boot on pandora. The validated Xiaomi
    # policy keeps the official R51 source/build engine while disabling KMI
    # trimming and protected-module enforcement so vendor/vendor_dlkm modules
    # retain the broader symbol surface. MODULE_SCMVERSION stays unchanged.
    python3 - common/BUILD.bazel <<'PY'
from pathlib import Path

path = Path("common/BUILD.bazel")
text = path.read_text()
start = text.find('common_kernel(\n    name = "kernel_aarch64",')
if start < 0:
    raise SystemExit("kernel_aarch64 common_kernel block missing")
end = text.find("\n)\n", start)
if end < 0:
    raise SystemExit("kernel_aarch64 common_kernel block end missing")
end += 3
block = text[start:end]

replacements = {
    "    kmi_enforced = True,\n": "    kmi_enforced = False,\n",
    "    kmi_symbol_list_strict_mode = True,\n": "    kmi_symbol_list_strict_mode = False,\n",
    "    trim_nonlisted_kmi = True,\n": "    trim_nonlisted_kmi = False,\n",
    '    kmi_symbol_list = "gki/aarch64/symbols/base",\n': "",
    '    protected_module_names_list = ":gki_aarch64_protected_module_names",\n': "",
}
for old, new in replacements.items():
    count = block.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one ACK compat target entry {old.strip()!r}, found {count}")
    block = block.replace(old, new, 1)

for forbidden in (
    'kmi_enforced = True',
    'kmi_symbol_list_strict_mode = True',
    'trim_nonlisted_kmi = True',
    'kmi_symbol_list = "gki/aarch64/symbols/base"',
    'protected_module_names_list = ":gki_aarch64_protected_module_names"',
):
    if forbidden in block:
        raise SystemExit(f"ACK compat patch incomplete: {forbidden}")

for required in (
    'kmi_enforced = False',
    'kmi_symbol_list_strict_mode = False',
    'trim_nonlisted_kmi = False',
):
    if required not in block:
        raise SystemExit(f"ACK compat patch missing: {required}")

path.write_text(text[:start] + block + text[end:])
PY

    SOURCE_KMI_MODE="$ACK_XIAOMI_KMI_MODE"
    python3 - "$WORKDIR/source-provenance.env" "$SOURCE_KMI_MODE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = sys.argv[2]
text = path.read_text()
needle = "SOURCE_KMI_MODE="
matches = [line for line in text.splitlines() if line.startswith(needle)]
if len(matches) != 1:
    raise SystemExit(f"expected exactly one SOURCE_KMI_MODE entry, found {len(matches)}")
lines = [f"SOURCE_KMI_MODE={value}" if line.startswith(needle) else line for line in text.splitlines()]
path.write_text("\n".join(lines) + "\n")
PY
    note "ACK Xiaomi compatibility: disabled KMI trimming/protected-module policy for kernel_aarch64"

    frag_flag=()
    if [[ -s "$FRAGMENT" ]]; then
      note "defconfig fragment:"
      cat "$FRAGMENT"

      cat >> common/BUILD.bazel <<'EOF'
exports_files(
    ["arch/arm64/configs/xiaomi_sm8850.fragment"],
    visibility = ["//visibility:public"],
)
EOF
      frag_flag=("--defconfig_fragment=//common:arch/arm64/configs/xiaomi_sm8850.fragment")
    fi

    # ACK's stock GKI module list expects several drivers as .ko outputs.
    # Xiaomi's boot-only AnyKernel path intentionally compiles selected
    # features into Image (=y), so those .ko files no longer exist. Keep the
    # features built-in and teach Kleaf not to require module outputs that the
    # selected fragment deliberately converted to built-ins.
    ack_builtin_modules=()
    if [[ "${XIAOMI_USE_ZRAM:-false}" == "true" ]]; then
      ack_builtin_modules+=(
        "drivers/block/zram/zram.ko"
        "mm/zsmalloc.ko"
      )
    fi
    if [[ "${XIAOMI_USE_NETWORKING:-false}" == "true" ]]; then
      ack_builtin_modules+=(
        "fs/netfs/netfs.ko"
      )
    fi

    if (("${#ack_builtin_modules[@]}" > 0)); then
      note "adjusting ACK Kleaf module expectations for Xiaomi built-ins:"
      printf '  - %s\n' "${ack_builtin_modules[@]}"

      python3 - common/modules.bzl "${ack_builtin_modules[@]}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
remove = sys.argv[2:]
text = path.read_text()

marker = "# Deprecated - Use `get_gki_modules_list` function instead."
if marker not in text:
    raise SystemExit("unable to locate end of common GKI module list")

gki_list, rest = text.split(marker, 1)

for module in remove:
    needle = f'    "{module}",\n'
    count = gki_list.count(needle)
    if count != 1:
        raise SystemExit(
            f"expected exactly one common GKI output entry for {module}, found {count}"
        )
    gki_list = gki_list.replace(needle, "", 1)

path.write_text(gki_list + marker + rest)
PY

      for module in "${ack_builtin_modules[@]}"; do
        if grep -Fq "\"$module\"" common/modules.bzl | head -n1; then
          # The same path may legitimately remain in the unprotected-module
          # helper list. Only the first GKI output-list entry is removed above.
          note "ACK module path still appears in helper metadata: $module"
        fi
      done
    fi

    # Kleaf uses "-maybe-dirty" as a deliberate placeholder when stamping
    # is disabled (our fast local-control build). It does not mean this source
    # tree is actually dirty. Remove only that ACK/Kleaf fallback marker so the
    # generated release is deterministic; exact source provenance remains in
    # build-metadata.txt. This runs only in the kleaf-dist / ack-r51 branch.
    stamp_bzl="$KERNEL_ROOT/build/kernel/kleaf/impl/stamp.bzl"
    [[ -f "$stamp_bzl" ]] || die "ACK Kleaf stamp file missing: $stamp_bzl"
    if grep -q 'stable_scmversion_cmd.*-maybe-dirty' "$stamp_bzl"; then
      sed -i '/stable_scmversion_cmd/s/-maybe-dirty//' "$stamp_bzl"
      note "removed ACK Kleaf non-stamp maybe-dirty placeholder"
    else
      die "ACK Kleaf maybe-dirty fallback layout changed; refusing unverified version patch"
    fi

    # Do not force ThinLTO on ACK-R51. This R51 GKI defconfig enables
    # DEBUG_INFO_BTF + RUST + rust_binder=m, while CONFIG_RUST requires !LTO
    # when BTF is enabled. Forcing --lto=thin silently disables CONFIG_RUST,
    # then Kleaf still expects rust_binder.ko and fails at module collection.
    # Keep the official R51 build engine and source-default LTO. The only KMI
    # policy deviation is the validated Xiaomi compatibility adjustment above;
    # Gold source/build behavior is not involved.
    note "building ACK Xiaomi compatibility with //common:kernel_aarch64_dist + source-default LTO + relaxed Xiaomi KMI policy"
    tools/bazel build \
      --config=fast \
      "${frag_flag[@]}" \
      //common:kernel_aarch64_dist

    IMAGE="$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image"
    [[ -s "$IMAGE" ]] || die "built Image not found: $IMAGE"
    cp -f "$IMAGE" "$OUT/Image"
    if [[ -s "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" ]]; then
      cp -f "$KERNEL_ROOT/bazel-bin/common/kernel_aarch64/Image.lz4" "$OUT/Image.lz4"
    fi

    build_target="//common:kernel_aarch64_dist"
    lto_mode="source-default (R51; ThinLTO not forced)"
    kmi_enforced="false (Xiaomi ACK compatibility)"
    kmi_strict="false (Xiaomi ACK compatibility)"
    ;;

  *)
    die "unknown build mode from provenance: $SOURCE_BUILD_MODE"
    ;;
esac

IMAGE="$OUT/Image"
[[ -s "$IMAGE" ]] || die "Image missing after build"

"$KERNEL_ROOT/common/scripts/extract-ikconfig" "$IMAGE" > "$OUT/final.config.embedded"
[[ -s "$OUT/final.config.embedded" ]] ||
  die "failed to extract embedded config from final Image"
mv -f "$OUT/final.config.embedded" "$OUT/final.config"

kernel_string="$(strings -a "$IMAGE" | grep -m1 '^Linux version ' || true)"
[[ -n "$kernel_string" ]] || die "Linux version string not found in Image"

resukisu_ref="${XIAOMI_RESUKISU_REF:-$RESUKISU_DEFAULT_REF}"
resukisu_actual="N/A"
resukisu_tag="N/A"
resukisu_version_code="N/A"
susfs_ref="${XIAOMI_SUSFS_REF:-$SUSFS_DEFAULT_REF}"
susfs_actual="N/A"
susfs_version="N/A"
if [[ -d "$KERNEL_ROOT/ReSukiSU/.git" ]]; then
  resukisu_actual="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-parse HEAD)"
  resukisu_tag="$(git -C "$KERNEL_ROOT/ReSukiSU" describe --abbrev=0 --tags 2>/dev/null || echo v4.1.0)"
  resukisu_commit_count="$(git -C "$KERNEL_ROOT/ReSukiSU" rev-list --count HEAD)"
  resukisu_version_code="$((30000 + resukisu_commit_count + 700))"
fi
if [[ -d "$KERNEL_ROOT/SUSFS/.git" ]]; then
  susfs_actual="$(git -C "$KERNEL_ROOT/SUSFS" rev-parse HEAD)"
  susfs_version="$(awk '/^#define[[:space:]]+SUSFS_VERSION[[:space:]]+/ {gsub(/"/,"",$3); print $3; exit}' "$KERNEL_ROOT/SUSFS/kernel_patches/include/linux/susfs.h" 2>/dev/null || true)"
  [[ -n "$susfs_version" ]] || susfs_version="unknown"
fi

cat > "$OUT/build-metadata.txt" <<EOF
device=$DEVICE
device_name=$(device_marketing_name "$DEVICE")
variant=$VARIANT
source_profile=$SOURCE_PROFILE
source_build_mode=$SOURCE_BUILD_MODE
source_kmi_source_mode=$SOURCE_KMI_SOURCE_MODE
source_kmi_mode=$SOURCE_KMI_MODE
android_version=$ANDROID_VERSION
kernel_expected=$KERNEL_VERSION
stock_reference=$EXPECTED_STOCK_RELEASE
manifest_commit=$SOURCE_MANIFEST_COMMIT
source_common_repo=$SOURCE_COMMON_REPO
source_common_ref=$SOURCE_COMMON_REF
source_common_commit=$SOURCE_COMMON_COMMIT
kmi_generation=$KMI_GENERATION
clang_revision=$CLANG_VERSION
clang_version=$clang_line
resukisu_requested_ref=$resukisu_ref
resukisu_commit=$resukisu_actual
resukisu_tag=$resukisu_tag
resukisu_version_code=$resukisu_version_code
resukisu_last_known_good_commit=$RESUKISU_LAST_KNOWN_GOOD_COMMIT
susfs_requested_ref=$susfs_ref
susfs_commit=$susfs_actual
susfs_version=$susfs_version
susfs_last_known_good_commit=$SUSFS_LAST_KNOWN_GOOD_COMMIT
susfs_previous_pinned_commit=$SUSFS_PREVIOUS_PINNED_COMMIT
susfs_extra_features=${XIAOMI_SUSFS_EXTRA_FEATURES:-false}
kernel_string=$kernel_string
build_target=$build_target
lto=$lto_mode
kmi_enforced=$kmi_enforced
kmi_symbol_list_strict_mode=$kmi_strict
EOF

if [[ -s "$WORKDIR/feature-provenance.env" ]]; then
  cat "$WORKDIR/feature-provenance.env" >> "$OUT/build-metadata.txt"
fi

bash "$XIAOMI_SCRIPT_DIR/validate.sh" "$DEVICE" "$VARIANT" "$WORKDIR"
bash "$XIAOMI_SCRIPT_DIR/package-anykernel3.sh" "$DEVICE" "$VARIANT" "$WORKDIR"

sha256sum "$OUT/Image" "$OUT"/*.zip > "$OUT/SHA256SUMS"
note "build complete: $OUT"
