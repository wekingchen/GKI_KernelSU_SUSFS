#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KERNEL_ROOT="${1:?usage: integrate-susfs.sh <kernel-root> <fragment>}"
FRAGMENT="${2:?usage: integrate-susfs.sh <kernel-root> <fragment>}"
SUSFS_DIR="$KERNEL_ROOT/SUSFS"

[[ -d "$KERNEL_ROOT/common" ]] || die "common kernel tree not found"
[[ -f "$FRAGMENT" ]] || die "config fragment not found: $FRAGMENT"
[[ ! -e "$SUSFS_DIR" ]] || die "SUSFS checkout already exists"

note "cloning SUSFS $SUSFS_BRANCH at immutable commit $SUSFS_COMMIT"
git clone --filter=blob:none --no-checkout --branch "$SUSFS_BRANCH" "$SUSFS_REPO" "$SUSFS_DIR"
git -C "$SUSFS_DIR" fetch --depth=1 origin "$SUSFS_COMMIT"
git -C "$SUSFS_DIR" checkout --detach "$SUSFS_COMMIT"
actual="$(git -C "$SUSFS_DIR" rev-parse HEAD)"
[[ "$actual" == "$SUSFS_COMMIT" ]] ||
  die "SUSFS commit mismatch: expected $SUSFS_COMMIT got $actual"

patch_file="$SUSFS_DIR/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch"
[[ -f "$patch_file" ]] || die "missing Android 16 / 6.12 SUSFS patch"

# This r51 ACK contains Google's page-size migration helper. Do not silently
# rewrite SUSFS if the expected base API is absent; fail so the source mismatch
# is visible instead.
if grep -q 'VMA_PAD_START' "$patch_file"; then
  grep -Rqs '^#define VMA_PAD_START' "$KERNEL_ROOT/common/include/linux" ||
    die "SUSFS expects VMA_PAD_START but pinned ACK does not provide it"
fi

cp -f "$SUSFS_DIR"/kernel_patches/fs/* "$KERNEL_ROOT/common/fs/"
cp -f "$SUSFS_DIR"/kernel_patches/include/linux/* "$KERNEL_ROOT/common/include/linux/"

cd "$KERNEL_ROOT/common"
note "dry-running SUSFS kernel patch"
patch --dry-run -p1 --forward < "$patch_file"
note "applying SUSFS kernel patch (failure is fatal)"
patch -p1 --forward --no-backup-if-mismatch < "$patch_file"

if find . -type f -name '*.rej' -print -quit | grep -q .; then
  find . -type f -name '*.rej' -print >&2
  die "SUSFS produced .rej files"
fi

for line in   'CONFIG_KSU_SUSFS=y'   'CONFIG_KSU_SUSFS_SUS_PATH=y'   'CONFIG_KSU_SUSFS_SUS_MOUNT=y'   'CONFIG_KSU_SUSFS_SUS_KSTAT=y'   'CONFIG_KSU_SUSFS_SPOOF_UNAME=y'   'CONFIG_KSU_SUSFS_ENABLE_LOG=y'   'CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y'   'CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y'   'CONFIG_KSU_SUSFS_OPEN_REDIRECT=y'   'CONFIG_KSU_SUSFS_SUS_MAP=y'
do
  append_config "$FRAGMENT" "$line"
done

note "SUSFS integrated strictly: commit=$actual"
