#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

DEVICE="${1:?usage: package-anykernel3.sh <device> <variant> <workdir>}"
VARIANT="${2:?usage: package-anykernel3.sh <device> <variant> <workdir>}"
WORKDIR="${3:?usage: package-anykernel3.sh <device> <variant> <workdir>}"

validate_device "$DEVICE"
validate_variant "$VARIANT"

OUT="$WORKDIR/output/$DEVICE/$VARIANT"
IMAGE="$OUT/Image"
[[ -s "$IMAGE" ]] || die "Image missing: $IMAGE"

PROVENANCE="$WORKDIR/source-provenance.env"
[[ -f "$PROVENANCE" ]] || die "source provenance missing: $PROVENANCE"
# shellcheck disable=SC1090
source "$PROVENANCE"
case "${SOURCE_PROFILE:-}" in
  gold-cctv|ack-r51) ;;
  *) die "invalid source profile in provenance: ${SOURCE_PROFILE:-missing}" ;;
esac

TMP="$WORKDIR/anykernel3-$DEVICE-$VARIANT"
AK3="$TMP/upstream"
PKG="$TMP/package"
rm -rf "$TMP"
mkdir -p "$TMP" "$PKG"

note "cloning official AnyKernel3 at immutable commit $ANYKERNEL3_COMMIT"
git clone --filter=blob:none --no-checkout "$ANYKERNEL3_REPO" "$AK3"
git -C "$AK3" fetch --depth=1 origin "$ANYKERNEL3_COMMIT"
git -C "$AK3" checkout --detach "$ANYKERNEL3_COMMIT"
actual="$(git -C "$AK3" rev-parse HEAD)"
[[ "$actual" == "$ANYKERNEL3_COMMIT" ]] ||
  die "AnyKernel3 commit mismatch: expected $ANYKERNEL3_COMMIT got $actual"

# Whitelist packaging: no partition images other than the kernel payload.
cp -a "$AK3/META-INF" "$PKG/"
cp -a "$AK3/tools" "$PKG/"
cp -f "$IMAGE" "$PKG/Image"

cat > "$PKG/anykernel.sh" <<EOF
### AnyKernel3 Ramdisk Mod Script
## Xiaomi 17 series / SM8850 conservative boot-only kernel installer

properties() { '
kernel.string=Xiaomi SM8850 Android 16 $KERNEL_VERSION ($SOURCE_PROFILE / $VARIANT)
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=$DEVICE
device.name2=
device.name3=
device.name4=
device.name5=
supported.versions=16
supported.patchlevels=
supported.vendorpatchlevels=
'; }

BLOCK=boot;
IS_SLOT_DEVICE=auto;
SLOT_SELECT=active;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=0;
NO_VBMETA_PARTITION_PATCH=1;
NO_MAGISK_CHECK=1;

. tools/ak3-core.sh;

ui_print " ";
ui_print "Xiaomi SM8850 target: $DEVICE";
ui_print "Source: $SOURCE_PROFILE";
ui_print "Variant: $VARIANT";
ui_print "Kernel: $KERNEL_VERSION / Android 16";
ui_print "Only the active boot slot kernel payload will be replaced.";
ui_print "init_boot/vendor_boot/vendor_kernel_boot/dtbo/vbmeta are not flashed.";
ui_print " ";

# Android 16 boot header v4 devices keep first-stage ramdisk in init_boot.
# Parse boot, replace Image, and flash boot without unpacking/repacking ramdisk.
split_boot;
flash_boot;
EOF

for forbidden in   'boot.img' 'boot_a.img' 'boot_b.img'   'init_boot.img' 'vendor_boot.img' 'vendor_kernel_boot.img'   'dtbo.img' 'vbmeta.img'
do
  if find "$PKG" -type f -name "$forbidden" -print -quit | grep -q .; then
    die "forbidden image leaked into AnyKernel3 package: $forbidden"
  fi
done

zip_name="Xiaomi17Series-$DEVICE-$SOURCE_PROFILE-Android16-$KERNEL_VERSION-$VARIANT-AnyKernel3.zip"
(
  cd "$PKG"
  zip -qr9 "$OUT/$zip_name" .
)

unzip -t "$OUT/$zip_name" >/dev/null
listing="$(unzip -Z1 "$OUT/$zip_name")"
for required in Image anykernel.sh tools/ak3-core.sh META-INF/com/google/android/update-binary; do
  grep -qx "$required" <<<"$listing" || die "AnyKernel3 ZIP missing $required"
done
if grep -Eq '(^|/)(init_boot|vendor_boot|vendor_kernel_boot|dtbo|vbmeta|boot)(_[ab])?\.img$' <<<"$listing"; then
  die "AnyKernel3 ZIP contains a forbidden partition image"
fi

note "AnyKernel3 package ready: $OUT/$zip_name"
