#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.github/config/xiaomi-sm8850-os4-6.12.69.env"

IMAGE="${1:?usage: package-pandora-406-run37-anykernel3.sh <Image> <output-dir>}"
OUTDIR="${2:?usage: package-pandora-406-run37-anykernel3.sh <Image> <output-dir>}"

BUILD="OS4.0.6.0.XBLCNXM"
RELEASE="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
SOURCE_IMAGE_SHA="3daba0524738ab872ebf75653f25754433c36a624eb8002198440a4cb1cb1dc0"
CI_REBUILT="${PANDORA_RUN37_CI_REBUILT:-0}"
if [[ "$CI_REBUILT" == "1" ]]; then
  IMAGE_SHA="${PANDORA_RUN37_CI_IMAGE_SHA256:?missing PANDORA_RUN37_CI_IMAGE_SHA256}"
  [[ "$IMAGE_SHA" =~ ^[a-f0-9]{64}$ ]] || { echo "::error::bad CI rebuilt Image SHA"; exit 1; }
  PACKAGE="Xiaomi17Pro-pandora-OS4.0.6.0-run37-REBUILT-CI-ONLY-AnyKernel3.zip"
  INSTALLER_LABEL="Exact run37 source / CI-rebuilt kernel - NOT device tested"
  VALIDATION_LEVEL="CI_REBUILT_FROM_PERSISTENT_VERIFIED_RUN37_SOURCE"
else
  IMAGE_SHA="$SOURCE_IMAGE_SHA"
  PACKAGE="Xiaomi17Pro-pandora-OS4.0.6.0-run37-PERSISTENT-CANDIDATE-AnyKernel3.zip"
  INSTALLER_LABEL="Exact standard-workflow run #37 persistent verified kernel"
  VALIDATION_LEVEL="PERSISTENT_VERIFIED_EXACT_RUN37"
fi
STOCK_BOOT_SHA="a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b"
STOCK_BOOT_SIZE="100663296"
EEXIST_PATCH_SHA="5aab8a0a41369829707d6ea5ade437bc91a75dda4a5ac1fb6b1cb60158bef5ee"
AK3_COMMIT="dca9dc370838d919d56c1f59ec78b27a14a72c68"

RUNTIME_GATE="$ROOT/.github/config/ota-verified/OS4.0.6.0.XBLCNXM/runtime-selected-oem-gate.json"
PERSISTENT_GATE="$ROOT/.github/config/ota-verified/OS4.0.6.0.XBLCNXM/persistent-boot-equivalence.json"

[[ -s "$IMAGE" ]] || { echo "::error::Image missing: $IMAGE"; exit 1; }
[[ "$(sha256sum "$IMAGE" | awk '{print $1}')" == "$IMAGE_SHA" ]] || {
  echo "::error::run37 Image SHA mismatch"; exit 1;
}
grep -aFq "$RELEASE" "$IMAGE" || { echo "::error::kernel release marker missing"; exit 1; }
if [[ "$CI_REBUILT" != "1" && "$IMAGE_SHA" != "$SOURCE_IMAGE_SHA" ]]; then
  echo "::error::non-CI package must use exact user-tested run37 Image"
  exit 1
fi

python3 - "$RUNTIME_GATE" "$PERSISTENT_GATE" <<'PY'
import json, sys
from pathlib import Path
runtime=json.loads(Path(sys.argv[1]).read_text())
persistent=json.loads(Path(sys.argv[2]).read_text())
assert runtime["status"] == "PASS_RUNTIME_SELECTED_EXACT_OS406"
assert runtime["stock_build"] == "OS4.0.6.0.XBLCNXM"
assert runtime["feature_workflow_run_id"] == 45047763911
assert runtime["feature_image_sha256"] == "3daba0524738ab872ebf75653f25754433c36a624eb8002198440a4cb1cb1dc0"
assert runtime["eligible_for_persistent_kernel_payload"] is True
assert runtime["persistent_boot_equivalence"] == "PASS_EXACT_RUN37"
assert runtime["actual_persistent_install_verified"] is True
assert runtime["lkg_promotion"] is True
assert persistent["status"] == "PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37"
assert persistent["stock_boot_sha256"] == "a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b"
assert persistent["stock_partition_dump_size"] == 100663296
assert persistent["tested_fastboot_boot_sha256"] == "230a16fa271c3ccbaa14309adbd2905ae04430032a9f7b9d0853478aa7751d27"
assert persistent["semantic_payload"]["byte_exact_to_true_device_tested_run37"] is True
assert persistent["anykernel3"]["commit"] == "dca9dc370838d919d56c1f59ec78b27a14a72c68"
assert persistent["anykernel3"]["audit"] == "PASS"
assert persistent["anykernel3"]["repacked_cmdline"] == "module_blacklist=kernelsu pandora_rust_binder_eexist=1"
assert persistent["anykernel3"]["repacked_boot_size"] == 100663296
assert persistent["eligible_for_persistent_kernel_payload"] is True
assert persistent["actual_persistent_install_verified"] is True
assert persistent["lkg_promotion"] is True
PY

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
AK3="$TMP/AnyKernel3"
PKG="$TMP/package"
mkdir -p "$OUTDIR" "$PKG"

git clone -q --filter=blob:none --no-checkout "$OS4_ANYKERNEL3_REPO" "$AK3"
git -C "$AK3" fetch -q --depth=1 origin "$AK3_COMMIT"
git -C "$AK3" checkout -q --detach "$AK3_COMMIT"
[[ "$(git -C "$AK3" rev-parse HEAD)" == "$AK3_COMMIT" ]]

cp -a "$AK3/META-INF" "$PKG/"
cp -a "$AK3/tools" "$PKG/"
cp -f "$IMAGE" "$PKG/Image"

cat > "$PKG/anykernel.sh" <<'AK3EOF'
### AnyKernel3 Ramdisk Mod Script
## Xiaomi 17 Pro / pandora / OS4.0.6 exact run37 persistent candidate

properties() { '
kernel.string=Xiaomi 17 Pro OS4.0.6 / run37 persistent candidate
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
ui_print "Xiaomi 17 Pro / pandora / OS4.0.6";
ui_print "Exact standard-workflow run #37 persistent candidate";
ui_print "Kernel: 6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k";
ui_print "This installer is fail-closed and accepts only the exact stock boot.";
ui_print " ";

build="$(getprop ro.mi.os.version.incremental 2>/dev/null)"
[ -z "$build" ] && build="$(getprop ro.build.version.incremental 2>/dev/null)"
[ "$build" = "OS4.0.6.0.XBLCNXM" ] || abort "Unsupported OS build: $build";

split_boot;

# This candidate was audited only from the exact untouched OS4.0.6 boot
# partition. Refuse any unknown/mutated source boot before modifying it.
source_size="$(wc -c < "$BOOTIMG" | tr -d ' ')";
[ "$source_size" = "100663296" ] || abort "Unexpected boot partition dump size: $source_size";

source_sha="$(tools/busybox sha256sum "$BOOTIMG" | awk '{print $1}')";
[ "$source_sha" = "a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b" ] ||
  abort "Active boot is not the audited stock OS4.0.6 image; refusing persistent install.";

if [ -f "$SPLITIMG/cmdline.txt" ]; then
  current_cmdline="$(cat "$SPLITIMG/cmdline.txt")";
else
  current_cmdline="$(grep '^cmdline=' "$SPLITIMG/header" 2>/dev/null | cut -d= -f2-)";
fi

# Keep any pre-existing blacklist values and append kernelsu exactly once.
blacklist_count="$(echo "$current_cmdline" | tr ' ' '\n' | grep -c '^module_blacklist=' || true)";
[ "$blacklist_count" -le 1 ] || abort "Ambiguous module_blacklist in stock boot";
blacklist="$(echo "$current_cmdline" | tr ' ' '\n' | grep '^module_blacklist=' | cut -d= -f2-)";
if [ "$blacklist" ]; then
  if ! echo "$blacklist" | tr ',' '\n' | grep -qx 'kernelsu'; then
    patch_cmdline "module_blacklist=" "module_blacklist=$blacklist,kernelsu";
  fi
else
  patch_cmdline "module_blacklist=" "module_blacklist=kernelsu";
fi

# Exact EEXIST compatibility parameter required by the #37 true-device proof.
if [ -f "$SPLITIMG/cmdline.txt" ]; then
  current_cmdline="$(cat "$SPLITIMG/cmdline.txt")";
else
  current_cmdline="$(grep '^cmdline=' "$SPLITIMG/header" 2>/dev/null | cut -d= -f2-)";
fi
eexist_count="$(echo "$current_cmdline" | tr ' ' '\n' | grep -c '^pandora_rust_binder_eexist=' || true)";
[ "$eexist_count" -le 1 ] || abort "Ambiguous pandora_rust_binder_eexist in boot cmdline";
eexist="$(echo "$current_cmdline" | tr ' ' '\n' | grep '^pandora_rust_binder_eexist=' || true)";
if [ "$eexist" ]; then
  [ "$eexist" = "pandora_rust_binder_eexist=1" ] ||
    abort "Conflicting pandora_rust_binder_eexist value";
else
  patch_cmdline "pandora_rust_binder_eexist=" "pandora_rust_binder_eexist=1";
fi

# Verify the exact post-patch cmdline contract before magiskboot repacks/writes.
if [ -f "$SPLITIMG/cmdline.txt" ]; then
  final_cmdline="$(cat "$SPLITIMG/cmdline.txt")";
else
  final_cmdline="$(grep '^cmdline=' "$SPLITIMG/header" 2>/dev/null | cut -d= -f2-)";
fi
echo "$final_cmdline" | tr ' ' '\n' | grep -qx 'pandora_rust_binder_eexist=1' ||
  abort "EEXIST compatibility parameter not present after patch";
final_blacklist="$(echo "$final_cmdline" | tr ' ' '\n' | grep '^module_blacklist=' | cut -d= -f2-)";
echo "$final_blacklist" | tr ',' '\n' | grep -qx 'kernelsu' ||
  abort "KernelSU LKM blacklist not present after patch";

ui_print "Source boot SHA verified.";
ui_print "Persistent cmdline contract verified.";
ui_print "Repacking exact run37 kernel with pinned AnyKernel3...";
flash_boot;
AK3EOF

python3 - "$PKG/anykernel.sh" "$INSTALLER_LABEL" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1])
label=sys.argv[2]
s=p.read_text()
s=s.replace("Exact standard-workflow run #37 persistent candidate", label)
s=s.replace("run37 persistent candidate", label)
p.write_text(s)
PY

cat > "$PKG/README.txt" <<EOF
Xiaomi 17 Pro / pandora / OS4.0.6.0.XBLCNXM
Exact standard custom workflow run #37 persistent candidate

Image SHA256:
$IMAGE_SHA

Expected source boot SHA256:
$STOCK_BOOT_SHA

AnyKernel3 commit:
$AK3_COMMIT

Persistent boot equivalence:
PASS_PERSISTENT_BOOT_EQUIVALENCE_EXACT_OS406_RUN37

Runtime-selected OEM ABI gate:
PASS_RUNTIME_SELECTED_EXACT_OS406

The installer refuses to run unless:
- device is pandora;
- OS build is exactly OS4.0.6.0.XBLCNXM;
- active boot partition dump is exactly 100663296 bytes;
- active boot SHA256 is exactly the audited stock boot SHA.

It patches only:
- kernel payload -> exact run #37 Image;
- module_blacklist -> contains kernelsu;
- pandora_rust_binder_eexist=1.

It does not touch init_boot, vendor_boot, vendor_kernel_boot, dtbo or vbmeta.

STATUS: $VALIDATION_LEVEL.
The exact source run37 package passed two true-device persistent reboots.
If this is a CI-rebuilt package, it is archived as CI-only and is NOT independently device tested.
EOF

# No raw partition images are allowed inside the installer.
for forbidden in boot.img boot_a.img boot_b.img init_boot.img vendor_boot.img \
                 vendor_kernel_boot.img dtbo.img vbmeta.img; do
  if find "$PKG" -type f -name "$forbidden" -print -quit | grep -q .; then
    echo "::error::forbidden partition image leaked into candidate: $forbidden"
    exit 1
  fi
done

ZIP="$OUTDIR/$PACKAGE"
(
  cd "$PKG"
  zip -qr9 "$ZIP" .
)
unzip -t "$ZIP" >/dev/null

listing="$(unzip -Z1 "$ZIP")"
for required in Image anykernel.sh README.txt tools/ak3-core.sh META-INF/com/google/android/update-binary; do
  grep -qx "$required" <<<"$listing" || { echo "::error::missing $required"; exit 1; }
done
if grep -Eq '(^|/)(init_boot|vendor_boot|vendor_kernel_boot|dtbo|vbmeta|boot)(_[ab])?\.img$' <<<"$listing"; then
  echo "::error::forbidden partition image found in ZIP"
  exit 1
fi

unzip -p "$ZIP" Image | sha256sum | grep -q "^$IMAGE_SHA  -" ||
  { echo "::error::ZIP Image hash mismatch"; exit 1; }
unzip -p "$ZIP" anykernel.sh | grep -Fq 'pandora_rust_binder_eexist=1' ||
  { echo "::error::EEXIST patch missing from installer"; exit 1; }
unzip -p "$ZIP" anykernel.sh | grep -Fq "$STOCK_BOOT_SHA" ||
  { echo "::error::stock boot fail-closed SHA missing"; exit 1; }

sha256sum "$ZIP" > "$ZIP.sha256"
echo "PACKAGE=$ZIP"
echo "PACKAGE_SHA256=$(awk '{print $1}' "$ZIP.sha256")"
echo "IMAGE_SHA256=$IMAGE_SHA"
echo "SOURCE_BOOT_SHA256=$STOCK_BOOT_SHA"
echo "VALIDATION_LEVEL=$VALIDATION_LEVEL"
echo "SOURCE_RUN37_IMAGE_SHA256=$SOURCE_IMAGE_SHA"
echo "ACTUAL_PERSISTENT_INSTALL_VERIFIED=YES_FOR_SOURCE_RUN37"
if [[ "$CI_REBUILT" == "1" ]]; then
  echo "REBUILT_DEVICE_TESTED=NO"
  echo "LKG_ARCHIVE_ROLE=REBUILT_CI_ONLY"
else
  echo "REBUILT_DEVICE_TESTED=SOURCE_EXACT_TRUE_DEVICE_VERIFIED"
  echo "LKG_ARCHIVE_ROLE=ORIGINAL_USER_ATTESTED"
fi
