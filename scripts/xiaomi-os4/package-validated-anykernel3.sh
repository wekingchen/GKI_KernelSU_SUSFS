#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"
source "$ROOT/.github/config/pandora-os4-full-parity-lkg.env"

IMAGE="${1:?usage: package-validated-anykernel3.sh <Image> <output-dir>}"
OUTDIR="${2:?usage: package-validated-anykernel3.sh <Image> <output-dir>}"

EXPECTED_IMAGE_SHA256="$LKG_IMAGE_SHA256"
EXPECTED_RELEASE="$LKG_KERNEL_RELEASE"
EXPECTED_BUILD="$LKG_SYSTEM_BUILD"
DEVICE="$LKG_DEVICE"

[[ -s "$IMAGE" ]] || { echo "::error::validated Image missing: $IMAGE"; exit 1; }
actual_sha="$(sha256sum "$IMAGE" | awk '{print $1}')"
[[ "$actual_sha" == "$EXPECTED_IMAGE_SHA256" ]] || {
  echo "::error::validated Image SHA mismatch: $actual_sha"; exit 1;
}
grep -aFq "$EXPECTED_RELEASE" "$IMAGE" || {
  echo "::error::validated kernel release marker missing"; exit 1;
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
AK3="$TMP/AnyKernel3"
PKG="$TMP/package"
mkdir -p "$OUTDIR" "$PKG"

git clone -q --filter=blob:none --no-checkout "$OS4_ANYKERNEL3_REPO" "$AK3"
git -C "$AK3" fetch -q --depth=1 origin "$OS4_ANYKERNEL3_COMMIT"
git -C "$AK3" checkout -q --detach "$OS4_ANYKERNEL3_COMMIT"
[[ "$(git -C "$AK3" rev-parse HEAD)" == "$OS4_ANYKERNEL3_COMMIT" ]] || {
  echo "::error::AnyKernel3 commit mismatch"; exit 1;
}

cp -a "$AK3/META-INF" "$PKG/"
cp -a "$AK3/tools" "$PKG/"
cp -f "$IMAGE" "$PKG/Image"

cat > "$PKG/anykernel.sh" <<'AK3EOF'
### AnyKernel3 Ramdisk Mod Script
## Xiaomi 17 Pro / pandora / HyperOS 4 validated R62 kernel installer

properties() { '
kernel.string=Xiaomi 17 Pro OS4 R62 Full Parity / BakaSU + SUSFS + NoMount + DroidSpaces
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=pandora
device.name2=
device.name3=
device.name4=
device.name5=
supported.versions=17
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
ui_print "Xiaomi 17 Pro / pandora";
ui_print "HyperOS 4 validated R62 Full Parity persistent LKG";
ui_print "Kernel: 6.12.69-android16-6-os4r62-dspids-dscore-full-parity-kmi-4k";
ui_print "Replaces only the active boot kernel payload.";
ui_print "Preserves ramdisk and does not touch init_boot/vendor_boot/dtbo/vbmeta.";
ui_print " ";

build="$(getprop ro.build.version.incremental 2>/dev/null)"
[ -z "$build" ] && build="$(getprop ro.system.build.version.incremental 2>/dev/null)"
if [ "$build" != "OS4.0.5.0.XBLCNXM" ]; then
  abort "Unsupported OS build: $build (expected OS4.0.5.0.XBLCNXM)";
fi

split_boot;

# Built-in BakaSU must not race the legacy KernelSU LKM from the user's
# previous boot setup. Preserve any existing blacklist entries and append
# kernelsu only when needed.
if [ -f "$SPLITIMG/cmdline.txt" ]; then
  current_cmdline="$(cat "$SPLITIMG/cmdline.txt")";
else
  current_cmdline="$(grep '^cmdline=' "$SPLITIMG/header" 2>/dev/null | cut -d= -f2-)";
fi
blacklist="$(echo "$current_cmdline" | tr ' ' '\n' | grep '^module_blacklist=' | head -n1 | cut -d= -f2-)";
if [ "$blacklist" ]; then
  if ! echo "$blacklist" | tr ',' '\n' | grep -qx 'kernelsu'; then
    patch_cmdline "module_blacklist=" "module_blacklist=$blacklist,kernelsu";
  fi
else
  patch_cmdline "module_blacklist=" "module_blacklist=kernelsu";
fi

flash_boot;
AK3EOF

cat > "$PKG/README.txt" <<EOF
Xiaomi 17 Pro / pandora
HyperOS build: $EXPECTED_BUILD
Validated kernel release: $EXPECTED_RELEASE
Validated Image SHA256: $EXPECTED_IMAGE_SHA256

This package replaces the active boot partition kernel payload through
AnyKernel3 and preserves the existing ramdisk.

It also ensures module_blacklist contains kernelsu so the legacy KernelSU LKM
cannot load alongside Built-in BakaSU.

Do not use on another device or OS build.
EOF

for forbidden in boot.img boot_a.img boot_b.img init_boot.img vendor_boot.img \
                 vendor_kernel_boot.img dtbo.img vbmeta.img; do
  if find "$PKG" -type f -name "$forbidden" -print -quit | grep -q .; then
    echo "::error::forbidden partition image leaked into package: $forbidden"; exit 1
  fi
done

ZIP="$OUTDIR/Xiaomi17Pro-pandora-OS4.0.5.0-R62-FULL-PARITY-AnyKernel3.zip"
(
  cd "$PKG"
  zip -qr9 "$ZIP" .
)

unzip -t "$ZIP" >/dev/null
listing="$(unzip -Z1 "$ZIP")"
for required in Image anykernel.sh README.txt tools/ak3-core.sh META-INF/com/google/android/update-binary; do
  grep -qx "$required" <<<"$listing" || {
    echo "::error::AnyKernel3 ZIP missing $required"; exit 1;
  }
done
if grep -Eq '(^|/)(init_boot|vendor_boot|vendor_kernel_boot|dtbo|vbmeta|boot)(_[ab])?\.img$' <<<"$listing"; then
  echo "::error::forbidden partition image found in ZIP"; exit 1
fi

sha256sum "$ZIP" > "$ZIP.sha256"
echo "PACKAGE=$ZIP"
echo "PACKAGE_SHA256=$(awk '{print $1}' "$ZIP.sha256")"
echo "VALIDATED_IMAGE_SHA256=$EXPECTED_IMAGE_SHA256"
echo "VALIDATED_RELEASE=$EXPECTED_RELEASE"
echo "TARGET_BUILD=$EXPECTED_BUILD"
echo "PERSISTENT_FLASH=MANUAL_ONLY"
echo "PERSISTENT_DEVICE_VALIDATION=PASS"
