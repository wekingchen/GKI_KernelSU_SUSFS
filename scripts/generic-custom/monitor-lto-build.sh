#!/usr/bin/env bash
# 持续记录 LTO 构建资源：优先读取 cgroup v2 / v1，若宿主不提供则明确标注 proc 回退。
# 只观测，不修改上游源码、内核 FULL LTO 选项或 Runner 内核参数。
set -euo pipefail

log_dir="${1:?缺少构建日志目录}"
once="${2:-}"
[[ -z "$once" || "$once" == "--once" ]] || { echo "::error::未知监控参数: $once" >&2; exit 2; }
interval="${GKI_MONITOR_INTERVAL:-60}"
[[ "$interval" =~ ^[0-9]+$ ]] && (( interval >= 1 && interval <= 600 )) ||
  { echo "::error::无效的采样间隔: $interval" >&2; exit 2; }

cg_root="${GKI_MONITOR_CGROUP_ROOT:-/sys/fs/cgroup}"
proc_root="${GKI_MONITOR_PROC_ROOT:-/proc}"
runner_tmp="${RUNNER_TEMP:-/tmp}"
mkdir -p "$log_dir"

read_metric() {
  if [[ -r "$1" ]]; then
    head -n 1 "$1" || echo unavailable
  else
    echo unavailable
  fi
}
read_events() {
  if [[ -r "$1" ]]; then
    tr '\n' ' ' < "$1" || echo unavailable
  else
    echo unavailable
  fi
}
read_proc_metric() {
  local path="$1" name="$2"
  if [[ -r "$path" ]]; then
    awk -v name="$name" '$1 == name {print $2; found=1; exit} END {if (!found) print "unavailable"}' "$path"
  else
    echo unavailable
  fi
}

while true; do
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  memory_source=host_proc_only
  memory_current_bytes=unavailable
  memory_peak_bytes=unavailable
  memory_limit_bytes=unavailable
  memory_events=unavailable
  cgroup_swap_bytes=unavailable

  if [[ -r "$cg_root/memory.current" ]]; then
    memory_source=cgroup_v2
    memory_current_bytes="$(read_metric "$cg_root/memory.current")"
    memory_peak_bytes="$(read_metric "$cg_root/memory.peak")"
    memory_limit_bytes="$(read_metric "$cg_root/memory.max")"
    memory_events="$(read_events "$cg_root/memory.events")"
    cgroup_swap_bytes="$(read_metric "$cg_root/memory.swap.current")"
  else
    # 部分 GitHub-hosted Runner 使用 cgroup v1：控制器可能直接挂载，也可能位于 memory/。
    v1_root="$cg_root"
    if [[ -r "$cg_root/memory/memory.usage_in_bytes" ]]; then
      v1_root="$cg_root/memory"
    fi
    if [[ -r "$v1_root/memory.usage_in_bytes" ]]; then
      memory_source=cgroup_v1
      memory_current_bytes="$(read_metric "$v1_root/memory.usage_in_bytes")"
      memory_peak_bytes="$(read_metric "$v1_root/memory.max_usage_in_bytes")"
      memory_limit_bytes="$(read_metric "$v1_root/memory.limit_in_bytes")"
      memory_events="failcnt=$(read_metric "$v1_root/memory.failcnt")"
      cgroup_swap_bytes="$(read_metric "$v1_root/memory.memsw.usage_in_bytes")"
    fi
  fi

  # proc 是宿主机指标，绝不能冒充为当前 CI Job 的 cgroup 内存使用量。
  host_mem_total_kb="$(read_proc_metric "$proc_root/meminfo" MemTotal:)"
  host_mem_available_kb="$(read_proc_metric "$proc_root/meminfo" MemAvailable:)"
  host_swap_free_kb="$(read_proc_metric "$proc_root/meminfo" SwapFree:)"
  host_oom_kill="$(read_proc_metric "$proc_root/vmstat" oom_kill)"
  if [[ -d "$runner_tmp" ]]; then
    disk_free_gib="$(df -BG --output=avail "$runner_tmp" | tail -n 1 | tr -dc '0-9')"
  else
    disk_free_gib=unavailable
  fi

  message="[GKI MONITOR] timestamp=$timestamp memory_source=$memory_source memory_current_bytes=$memory_current_bytes memory_peak_bytes=$memory_peak_bytes memory_limit_bytes=$memory_limit_bytes cgroup_swap_bytes=$cgroup_swap_bytes host_mem_total_kb=$host_mem_total_kb host_mem_available_kb=$host_mem_available_kb host_swap_free_kb=$host_swap_free_kb host_oom_kill=$host_oom_kill disk_free_gib=$disk_free_gib memory_events=[$memory_events]"
  printf '%s\n' "$message" | tee -a "$log_dir/resource-samples.log"
  [[ "$once" != "--once" ]] || break
  sleep "$interval"
done
