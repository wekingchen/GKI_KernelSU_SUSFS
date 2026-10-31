#!/usr/bin/env bash
# Verify persistent OS4 LKG Release downloads after Actions artifacts have expired.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
source .github/config/pandora-os4-full-parity-lkg.env
tag="${1:-pandora-os4-lkg-gen$LKG_PROMOTION_GENERATION}"
[[ "$tag" =~ ^pandora-os4-lkg-gen[1-9][0-9]*$ ]] || exit 2
repo="${GITHUB_REPOSITORY:-wekingchen/GKI_KernelSU_SUSFS}"
[[ "$repo" == "wekingchen/GKI_KernelSU_SUSFS" ]] || exit 2
export GH_REPO="$repo"
dir="${2:-$(mktemp -d)}"
mkdir -p "$dir"
echo "Downloading release $repo / $tag to $dir"
gh release download "$tag" --dir "$dir"
[[ "$(find "$dir" -maxdepth 1 -type f -name "SHA256SUMS-$tag.txt" | wc -l)" -eq 1 ]]
(cd "$dir" && sha256sum -c "SHA256SUMS-$tag.txt")
for archive in "$dir"/*evidence.tar.zst; do
  [[ -f "$archive" ]] || { echo "Missing evidence tarball"; exit 1; }
  tar -I zstd -tf "$archive" >/dev/null
done
if [[ "$tag" == "pandora-os4-lkg-gen$LKG_PROMOTION_GENERATION" ]]; then
  p="Xiaomi17Pro-pandora-OS4-Gen$LKG_PROMOTION_GENERATION"
  [[ "$(sha256sum "$dir/$p-ORIGINAL-USER-VERIFIED-AnyKernel3.zip" | awk '{print $1}')" == "$LKG_PACKAGE_SHA256" ]]
  [[ "$(sha256sum "$dir/$p-ORIGINAL-USER-VERIFIED-fastboot-boot.img" | awk '{print $1}')" == "$LKG_FASTBOOT_BOOT_SHA256" ]]
  cmp -s "$dir/$p-locked-lkg.env" .github/config/pandora-os4-full-parity-lkg.env || {
    echo "Release metadata differs from current LKG"; exit 1;
  }
fi
echo "RELEASE_RECOVERY_VERIFY=PASS tag=$tag dir=$dir"
