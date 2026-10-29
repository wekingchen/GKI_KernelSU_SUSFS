#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
guard="$script_dir/guard-gki-abi.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

printf 'CONFIG_CGROUP_PIDS=y\nCONFIG_MACVLAN=y\n' > "$tmp/unsafe.config"
if bash "$guard" "$tmp/unsafe.config" > "$tmp/unsafe.log" 2>&1; then
  echo 'FAIL: CONFIG_CGROUP_PIDS=y must be rejected' >&2
  exit 1
fi
grep -q 'CONFIG_CGROUP_PIDS must remain disabled' "$tmp/unsafe.log"

printf 'CONFIG_CGROUP_PIDS=m\n' > "$tmp/invalid.config"
if bash "$guard" "$tmp/invalid.config" > /dev/null 2>&1; then
  echo 'FAIL: CONFIG_CGROUP_PIDS=m must be rejected conservatively' >&2
  exit 1
fi

printf '# CONFIG_CGROUP_PIDS is not set\nCONFIG_MACVLAN=y\nCONFIG_CFS_BANDWIDTH=y\n' > "$tmp/safe.config"
bash "$guard" "$tmp/safe.config" | grep -q 'GKI ABI guard PASS'

printf 'CONFIG_MACVLAN=y\n' > "$tmp/absent.config"
bash "$guard" "$tmp/absent.config" | grep -q 'GKI ABI guard PASS'

if bash "$guard" "$tmp/nonexistent.config" > /dev/null 2>&1; then
  echo 'FAIL: missing config must be rejected' >&2
  exit 1
fi

echo 'PASS: GKI ABI guard rejects enabled PIDs and accepts safe known configs'
