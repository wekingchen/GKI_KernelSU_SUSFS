#!/usr/bin/env bash
# 仅适用于本仓私有构建，绝不修改上游源码或内核的 FULL LTO 选项。
set -euo pipefail

version="$1"
[[ -n "$version" ]] || { echo "::error::missing kernel version" >&2; exit 2; }
workdir="$(printenv RUNNER_TEMP || echo /tmp)"
[[ -d "$workdir" ]] || { echo "::error::missing runner temporary directory" >&2; exit 1; }
disk_gib="$(printenv GKI_TEST_DISK_GIB || df -BG --output=avail "$workdir" | tail -n 1 | tr -dc '0-9')"
[[ "$disk_gib" =~ ^[0-9]+$ ]] || { echo "::error::invalid free disk space: $disk_gib" >&2; exit 1; }

# 始终预留至少约 24 GiB 空间，以免交换文件挤占内核对象文件。
swap_gib=0
if (( disk_gib >= 44 )); then swap_gib=16
elif (( disk_gib >= 36 )); then swap_gib=12
elif (( disk_gib >= 32 )); then swap_gib=8
fi
echo "[GKI] kernel=$version free_disk=$disk_gib GiB swap_plan=$swap_gib GiB"
echo "[GKI] cgroup memory.max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo unavailable)"
echo "[GKI] cgroup memory.current=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo unavailable)"
free -h
df -h "$workdir"
swapon --show || true

# 仅供测试：不占用磁盘，不需要 sudo 或 GitHub Runner。
if [[ "$(printenv GKI_RESOURCE_DRY_RUN || echo 0)" == "1" ]]; then
  echo "GKI_SWAP_PLAN_GIB=$swap_gib"
  exit 0
fi

# 在 5.10 FULL LTO 已验证配置上只降低编译资源并行，不修改链接模式。
if [[ "$version" == "5.10" ]]; then
  [[ -n "$(printenv GITHUB_ENV || true)" ]] || { echo "::error::missing GITHUB_ENV" >&2; exit 1; }
  {
    echo 'JOBS=1'
    echo 'MAKEFLAGS=-j1 -l1'
    echo 'NINJAFLAGS=-j1'
    echo 'LLVM_PARALLEL_LINK_JOBS=1'
  } >> "$GITHUB_ENV"
  echo "[GKI] 5.10 FULL LTO 保持原样；单线程构建控制内存峰值"
fi

if (( swap_gib == 0 )); then
  echo "::warning::可用空间不足以安全开启 swap；继续构建并记录资源压力"
  exit 0
fi
run_id="$(printenv GITHUB_RUN_ID || echo manual)"
swapfile="$workdir/gki-fork-$run_id.swap"
if [[ -e "$swapfile" ]]; then
  echo "::warning::交换文件已存在，拒绝覆盖: $swapfile"
  exit 0
fi
if sudo fallocate -l "$swap_gib"G "$swapfile" &&
   sudo chmod 600 "$swapfile" &&
   sudo mkswap "$swapfile" >/dev/null &&
   sudo swapon "$swapfile"; then
  echo "[GKI] 已真实启用 $swap_gib GiB swap"
  swapon --show
else
  echo "::warning::本 Runner 不支持 swapon，未将准备文件误报为可用 swap"
  sudo swapoff "$swapfile" 2>/dev/null || true
  sudo rm -f "$swapfile" || true
fi
free -h
