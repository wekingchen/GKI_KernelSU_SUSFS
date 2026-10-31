#!/usr/bin/env bash
# Private fork-only build compatibility shim. Never changes a shared file in
# this repository; acts only on Android source downloaded inside the CI runner.
set -euo pipefail

root="${1:-}"
[[ -n "$root" ]] || { echo "usage: prepare-host-linker.sh <downloaded-GKI-root>" >&2; exit 2; }
tools_dir="$root/build/build-tools/path/linux-x86"
host_ld="${HOST_LD_OVERRIDE:-/usr/bin/ld}"
[[ -d "$tools_dir" ]] || { echo "::error::Android host build tools directory missing: $tools_dir" >&2; exit 1; }
[[ -x "$host_ld" ]] || { echo "::error::Host linker missing: $host_ld" >&2; exit 1; }
target="$tools_dir/ld"
if [[ -L "$target" && ! -e "$target" ]]; then
  echo "::error::Broken ld symlink; refusing to overwrite silently: $target" >&2
  exit 1
fi
if [[ -e "$target" ]]; then
  [[ -x "$target" ]] || { echo "::error::Existing ld is not executable: $target" >&2; exit 1; }
  echo "Host linker already present: $target"
else
  ln -s "$host_ld" "$target"
  echo "Added host ld only inside the downloaded Android build tools tree"
fi
[[ -x "$target" ]]
"$target" --version | head -n 1
