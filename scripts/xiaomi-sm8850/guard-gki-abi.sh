#!/usr/bin/env bash
set -euo pipefail

# Xiaomi SM8850 GKI 6.12.23: do not enable ABI-changing PIDs controller while
# booting with stock vendor modules. #24 with PIDs=y bootlooped; #23 and the
# Macvlan-only kernel with PIDs disabled were physically boot-tested.
config_file="${1:?usage: guard-gki-abi.sh <resolved-kernel-config>}"
[[ -s "$config_file" ]] || {
  echo "[xiaomi-sm8850] ERROR: GKI ABI guard: missing kernel config: $config_file" >&2
  exit 1
}

if grep -Eq '^CONFIG_CGROUP_PIDS=(y|m)$' "$config_file"; then
  echo "[xiaomi-sm8850] ERROR: GKI ABI guard: CONFIG_CGROUP_PIDS must remain disabled for stock Xiaomi vendor modules." >&2
  echo "[xiaomi-sm8850] #23/Macvlan-only booted with PIDs disabled; #24 bootlooped with PIDs enabled." >&2
  echo "[xiaomi-sm8850] PIDs is not an approved Xiaomi SM8850 feature; do not bypass module ABI checks." >&2
  exit 1
fi

echo "[xiaomi-sm8850] GKI ABI guard PASS: CONFIG_CGROUP_PIDS is not enabled"
