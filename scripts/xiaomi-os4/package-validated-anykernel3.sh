#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"
source "$ROOT/.github/config/pandora-os4-full-parity-lkg.env"

IMAGE="${1:?usage: package-validated-anykernel3.sh <Image> <output-dir>}"
OUTDIR="${2:?usage: package-validated-anykernel3.sh <Image> <output-dir>}"

MODE="${XIAOMI_AK3_MODE:-validated-lkg}"
EXPECTED_BUILD="${XIAOMI_AK3_BUILD:-$LKG_SYSTEM_BUILD}"
EXPECTED_RELEASE="${XIAOMI_AK3_RELEASE:-$LKG_KERNEL_RELEASE}"
DEVICE="$LKG_DEVICE"
RUN_ID="${GITHUB_RUN_ID:-manual}"

case "$MODE" in
  validated-lkg)
    PROFILE_LABEL="Validated byte-exact LKG"
    VALIDATION_LEVEL="VERIFIED_BYTE_EXACT_LKG"
    DEFAULT_PACKAGE="Xiaomi17Pro-pandora-OS4.0.5.0-R62-FULL-PARITY-AnyKernel3.zip"
    ;;
  full-parity-rebuild)
    PROFILE_LABEL="Validated Full Parity rebuild"
    VALIDATION_LEVEL="VERIFIED_FULL_PARITY_REBUILD"
    DEFAULT_PACKAGE="Xiaomi17Pro-pandora-OS4.0.5.0-R62-FULL-PARITY-AnyKernel3.zip"
    ;;
  custom)
    PROFILE_LABEL="Custom selectable build (UNVERIFIED)"
    VALIDATION_LEVEL="CUSTOM_UNVERIFIED"
    DEFAULT_PACKAGE="Xiaomi17Pro-pandora-OS4.0.5.0-R62-CUSTOM-run-${RUN_ID}-UNVERIFIED-AnyKernel3.zip"
    ;;
  *)
    echo "::error::unsupported XIAOMI_AK3_MODE: $MODE"
    exit 1
    ;;
esac

PACKAGE_NAME="${XIAOMI_AK3_PACKAGE_NAME:-$DEFAULT_PACKAGE}"

[[ -s "$IMAGE" ]] || { echo "::error::Image missing: $IMAGE"; exit 1; }
actual_sha="$(sha256sum "$IMAGE" | awk '{print $1}')"
grep -aFq "$EXPECTED_RELEASE" "$IMAGE" || {
  echo "::error::kernel release marker missing: $EXPECTED_RELEASE"
  exit 1
}

case "$MODE" in
  validated-lkg)
    [[ "$actual_sha" == "$LKG_IMAGE_SHA256" ]] || {
      echo "::error::validated LKG Image SHA mismatch: $actual_sha"
      exit 1
    }
    ;;
  full-parity-rebuild)
    [[ "$EXPECTED_RELEASE" == "$LKG_KERNEL_RELEASE" ]] || {
      echo "::error::Full Parity rebuild release drift: $EXPECTED_RELEASE"
      exit 1
    }
    python3 "$ROOT/scripts/xiaomi-os4/verify-lkg-image-equivalence.py" "$IMAGE"       --expected-size "$LKG_IMAGE_SIZE"       --build-id-payload-offset "$LKG_IMAGE_BUILD_ID_PAYLOAD_OFFSET"       --cert-offset "$LKG_IMAGE_MODULE_CERT_OFFSET"       --cert-length "$LKG_IMAGE_MODULE_CERT_LENGTH"       --expected-normalized-sha256 "$LKG_IMAGE_NORMALIZED_SHA256"
    ;;
  custom)
    # The caller must already have passed the common ABI/KMI lock.
    # Custom combinations are packaged for the user's OS3-style workflow,
    # but are deliberately marked UNVERIFIED until that exact combination
    # completes a real-device boot test.
    ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
AK3="$TMP/AnyKernel3"
PKG="$TMP/package"
mkdir -p "$OUTDIR" "$PKG"

git clone -q --filter=blob:none --no-checkout "$OS4_ANYKERNEL3_REPO" "$AK3"
git -C "$AK3" fetch -q --depth=1 origin "$OS4_ANYKERNEL3_COMMIT"
git -C "$AK3" checkout -q --detach "$OS4_ANYKERNEL3_COMMIT"
[[ "$(git -C "$AK3" rev-parse HEAD)" == "$OS4_ANYKERNEL3_COMMIT" ]] || {
  echo "::error::AnyKernel3 commit mismatch"
  exit 1
}

cp -a "$AK3/META-INF" "$PKG/"
cp -a "$AK3/tools" "$PKG/"
cp -f "$IMAGE" "$PKG/Image"

cat > "$PKG/anykernel.sh" <<'AK3EOF'
### AnyKernel3 Ramdisk Mod Script
## Xiaomi 17 Pro / pandora / HyperOS 4 R62 selectable kernel installer

properties() { '
kernel.string=Xiaomi 17 Pro OS4 R62 / @@PROFILE_LABEL@@
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
ui_print "HyperOS 4 R62 / @@PROFILE_LABEL@@";
ui_print "Kernel: @@EXPECTED_RELEASE@@";
ui_print "Validation: @@VALIDATION_LEVEL@@";
ui_print "Replaces only the active boot kernel payload.";
ui_print "Preserves ramdisk and does not touch init_boot/vendor_boot/dtbo/vbmeta.";
@@CUSTOM_WARNING@@
ui_print " ";

build="$(getprop ro.build.version.incremental 2>/dev/null)"
[ -z "$build" ] && build="$(getprop ro.system.build.version.incremental 2>/dev/null)"
if [ "$build" != "@@EXPECTED_BUILD@@" ]; then
  abort "Unsupported OS build: $build (expected @@EXPECTED_BUILD@@)";
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

python3 - "$PKG/anykernel.sh" "$PROFILE_LABEL" "$EXPECTED_RELEASE" "$VALIDATION_LEVEL" "$EXPECTED_BUILD" "$MODE" <<'PY'
from pathlib import Path
import sys

path, profile, release, validation, build, mode = sys.argv[1:]
p = Path(path)
text = p.read_text()
warning = (
    'ui_print "WARNING: this exact custom feature combination has not been real-device validated.";'
    if mode == "custom" else
    'ui_print "Full Parity rebuild path: real-device temporary-boot validation PASS.";'
)
replacements = {
    "@@PROFILE_LABEL@@": profile,
    "@@EXPECTED_RELEASE@@": release,
    "@@VALIDATION_LEVEL@@": validation,
    "@@EXPECTED_BUILD@@": build,
    "@@CUSTOM_WARNING@@": warning,
}
for old, new in replacements.items():
    text = text.replace(old, new)
if "@@" in text:
    raise SystemExit("unresolved AnyKernel3 template placeholder")
p.write_text(text)
PY
cat > "$PKG/README.txt" <<EOF
Xiaomi 17 Pro / pandora
HyperOS build: $EXPECTED_BUILD
Kernel release: $EXPECTED_RELEASE
Image SHA256: $actual_sha
Packaging mode: $MODE
Validation level: $VALIDATION_LEVEL

This package replaces the active boot partition kernel payload through
AnyKernel3 and preserves the existing ramdisk.

It also ensures module_blacklist contains kernelsu so the legacy KernelSU LKM
cannot load alongside Built-in BakaSU.

$(if [[ "$MODE" == "custom" ]]; then
  echo "WARNING: this exact custom feature combination has not completed a real-device boot validation."
  echo "Keep a known-good boot image available for recovery."
else
  echo "This Full Parity path has passed Xiaomi 17 Pro OS4 real-device temporary-boot validation."
fi)

Do not use on another device or OS build.
EOF

for forbidden in boot.img boot_a.img boot_b.img init_boot.img vendor_boot.img                  vendor_kernel_boot.img dtbo.img vbmeta.img; do
  if find "$PKG" -type f -name "$forbidden" -print -quit | grep -q .; then
    echo "::error::forbidden partition image leaked into package: $forbidden"
    exit 1
  fi
done

ZIP="$OUTDIR/$PACKAGE_NAME"
(
  cd "$PKG"
  zip -qr9 "$ZIP" .
)

unzip -t "$ZIP" >/dev/null
listing="$(unzip -Z1 "$ZIP")"
for required in Image anykernel.sh README.txt tools/ak3-core.sh META-INF/com/google/android/update-binary; do
  grep -qx "$required" <<<"$listing" || {
    echo "::error::AnyKernel3 ZIP missing $required"
    exit 1
  }
done
if grep -Eq '(^|/)(init_boot|vendor_boot|vendor_kernel_boot|dtbo|vbmeta|boot)(_[ab])?\.img$' <<<"$listing"; then
  echo "::error::forbidden partition image found in ZIP"
  exit 1
fi

sha256sum "$ZIP" > "$ZIP.sha256"
echo "PACKAGE=$ZIP"
echo "PACKAGE_NAME=$PACKAGE_NAME"
echo "PACKAGE_SHA256=$(awk '{print $1}' "$ZIP.sha256")"
echo "IMAGE_SHA256=$actual_sha"
echo "VALIDATION_LEVEL=$VALIDATION_LEVEL"
echo "KERNEL_RELEASE=$EXPECTED_RELEASE"
echo "TARGET_BUILD=$EXPECTED_BUILD"
echo "PERSISTENT_FLASH=MANUAL_ONLY"
