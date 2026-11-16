#!/usr/bin/env bash
# LTO 编译期间持续输出 cgroup 内存、swap 和磁盘数据，定位 Runner 异常关闭。
# 只观测，不改内核源码、Kconfig 或 LTO 模式。
set -euo pipefail
log_dir="$1"
[[ -n "$log_dir" ]] || { echo "::error::missing log directory" >&2; exit 2; }
interval="$(printenv GKI_MONITOR_INTERVAL || echo 60)"
[[ "$interval" =~ ^[0-9]+$ ]] && (( interval >= 1 && interval <= 600 )) ||
  { echo "::error::invalid monitor interval" >&2; exit 2; }
mkdir -p "$log_dir"

while true; do
  now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  mem_cur="$(cat /sys/fs/cgroup/memory.current 2>/dev/null || echo unknown)"
  mem_peak="$(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo unknown)"
  mem_max="$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo unknown)"
  mem_events="$(tr '\n' ' ' < /sys/fs/cgroup/memory.events 2>/dev/null || echo unavailable)"
  swap_free="$(awk '/SwapFree:/ {print $2}' /proc/meminfo)"
  runner_tmp="$(printenv RUNNER_TEMP || echo /tmp)"
  disk_free="$(df -BG --output=avail "$runner_tmp" | tail -n 1 | tr -dc '0-9')"
  line="[GKI MONITOR] $now mem_current=$mem_cur mem_peak=$mem_peak mem_max=$mem_max swap_free_kb=$swap_free disk_free_gib=$disk_free mem_events=$mem_events"
  printf '%s\n' "$line" | tee -a "$log_dir/resource-samples.log"
  sleep "$interval"
done
