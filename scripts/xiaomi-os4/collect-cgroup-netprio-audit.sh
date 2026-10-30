#!/system/bin/sh
# Xiaomi 17 Pro / pandora OS4：只读采集 cgroup / net_prio / PIDs 用户态依赖。
# 目的：在将 net_prio KMI 槽位内部替换为 PIDs 之前，确认 HyperOS 4 是否显式依赖 net_prio。
# 不读取 /data，不读取应用文件，不修改系统，不挂载/卸载，不刷机。
set -eu
umask 077

EXPECTED_BUILD="OS4.0.5.0.XBLCNXM"
EXPECTED_UNAME="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k"
OUT="/sdcard/Download/pandora-OS4.0.5.0-cgroup-netprio-audit.txt"

[ "$(id -u)" = "0" ] || {
  echo "请使用 Root Shell 执行：su -c 'sh /sdcard/Download/collect-cgroup-netprio-audit.sh'"
  exit 1
}

BUILD="$(getprop ro.build.version.incremental)"
RELEASE="$(uname -r)"
[ "$BUILD" = "$EXPECTED_BUILD" ] || {
  echo "系统版本不一致：$BUILD；预期 $EXPECTED_BUILD，已停止。"
  exit 1
}
[ "$RELEASE" = "$EXPECTED_UNAME" ] || {
  echo "当前不是已记录的 OS4 原厂内核：$RELEASE"
  echo "请先恢复/重启到原厂 OS4 内核后再采集，避免把实验内核状态混入基线。"
  exit 1
}

section() {
  printf '\n===== %s =====\n' "$1"
}

safe_cat() {
  file="$1"
  if [ -r "$file" ]; then
    echo "--- $file"
    cat "$file" 2>/dev/null || true
  fi
}

{
  echo "Xiaomi 17 Pro / pandora OS4 cgroup-net_prio 只读专项审计"
  echo "build=$BUILD"
  echo "uname=$RELEASE"
  echo "android_release=$(getprop ro.build.version.release)"
  echo "date_utc=$(date -u 2>/dev/null || date)"
  echo "scope=system/vendor/product/system_ext/odm only; /data excluded"

  section "内核 cgroup 基线"
  safe_cat /proc/cgroups
  echo "--- /proc/cmdline 中仅输出 cgroup 相关参数"
  tr ' ' '\n' < /proc/cmdline 2>/dev/null | grep -E '^(cgroup|systemd[.]unified_cgroup_hierarchy=)' || true
  echo "--- cgroup mounts"
  grep -E ' cgroup2? ' /proc/mounts 2>/dev/null || true
  safe_cat /proc/self/cgroup

  section "cgroup v2 根节点"
  for f in \
    /sys/fs/cgroup/cgroup.controllers \
    /sys/fs/cgroup/cgroup.subtree_control \
    /sys/fs/cgroup/cgroup.type \
    /sys/fs/cgroup/cgroup.procs
  do
    safe_cat "$f"
  done

  echo "--- 根节点 PIDs 文件"
  for f in /sys/fs/cgroup/pids.current /sys/fs/cgroup/pids.events /sys/fs/cgroup/pids.max /sys/fs/cgroup/pids.peak; do
    if [ -e "$f" ]; then
      echo "PRESENT $f"
      [ -r "$f" ] && head -n 20 "$f" 2>/dev/null || true
    else
      echo "ABSENT  $f"
    fi
  done

  echo "--- legacy net_prio / net_cls 路径"
  for p in \
    /sys/fs/cgroup/net_prio \
    /sys/fs/cgroup/net_cls \
    /sys/fs/cgroup/net_cls,net_prio
  do
    if [ -e "$p" ]; then
      echo "PRESENT $p"
      ls -la "$p" 2>/dev/null | head -n 80 || true
    else
      echo "ABSENT  $p"
    fi
  done

  section "实际 net_prio v1 挂载与 priomap"
  NETPRIO_MOUNTS=0
  while IFS=' ' read -r dev mp fstype opts rest; do
    [ "$fstype" = "cgroup" ] || continue
    echo ",$opts," | grep -q ',net_prio,' || continue
    NETPRIO_MOUNTS=$((NETPRIO_MOUNTS + 1))
    echo "NET_PRIO_MOUNT device=$dev mountpoint=$mp options=$opts"
    if [ -d "$mp" ]; then
      find "$mp" -maxdepth 3 -type f \( -name 'net_prio.ifpriomap' -o -name 'net_prio.prioidx' \) 2>/dev/null | \
        while IFS= read -r file; do
          echo "--- $file"
          cat "$file" 2>/dev/null || true
        done
    fi
  done < /proc/mounts
  echo "NET_PRIO_V1_MOUNT_COUNT=$NETPRIO_MOUNTS"

  section "Android cgroup 配置文件原文"
  FOUND_JSON=0
  for root in /system/etc /system_ext/etc /product/etc /vendor/etc /odm/etc; do
    [ -d "$root" ] || continue
    for f in \
      "$root/cgroups.json" \
      "$root/cgroups_*.json" \
      "$root/task_profiles.json" \
      "$root/task_profiles_*.json"
    do
      for real in $f; do
        [ -f "$real" ] || continue
        FOUND_JSON=1
        echo
        echo "### FILE $real"
        sha256sum "$real" 2>/dev/null || true
        cat "$real" 2>/dev/null || true
      done
    done
  done
  [ "$FOUND_JSON" = "1" ] || echo "没有找到预期的 cgroups/task_profiles JSON"

  section "系统文本配置中的 net_prio / net_cls / PIDs 显式引用"
  MATCH_COUNT=0
  TMP="/sdcard/Download/.pandora-cgroup-audit-matches.$$"
  : > "$TMP"
  for root in /system/etc /system_ext/etc /product/etc /vendor/etc /odm/etc; do
    [ -d "$root" ] || continue
    find "$root" -type f \( \
      -name '*.rc' -o -name '*.json' -o -name '*.conf' -o -name '*.xml' \
      -o -name '*.sh' -o -name '*.prop' -o -name '*.txt' \
    \) 2>/dev/null | while IFS= read -r file; do
      grep -n -E -i 'net_prio|net_cls|pids[.]max|pids[.]current|pids[.]events|cgroup[.]procs|CGROUP_PIDS|CGROUP_NET_PRIO' "$file" 2>/dev/null | \
        sed "s#^#$file:#" || true
    done >> "$TMP"
  done
  if [ -s "$TMP" ]; then
    cat "$TMP"
    MATCH_COUNT="$(wc -l < "$TMP" | tr -d ' ')"
  else
    echo "NO_EXPLICIT_TEXT_MATCH"
  fi
  rm -f "$TMP"

  section "init rc 中 cgroup/task profile 操作"
  for root in /system/etc/init /system_ext/etc/init /product/etc/init /vendor/etc/init /odm/etc/init; do
    [ -d "$root" ] || continue
    find "$root" -type f -name '*.rc' 2>/dev/null | while IFS= read -r file; do
      grep -n -E -i 'task_profile|SetTaskProfiles|cgroup|writepid|pids' "$file" 2>/dev/null | \
        sed "s#^#$file:#" || true
    done
  done

  section "结论标记（仅采集，不自动宣称安全）"
  echo "TEXT_REFERENCE_LINES=$MATCH_COUNT"
  echo "SAFE_TO_FASTBOOT_BOOT=UNDECIDED"
  echo "说明：此报告只排查显式用户态配置依赖；仍需结合 OEM 模块 ABI、实验内核启动及基础功能验证。"
} > "$OUT"

chmod 600 "$OUT" 2>/dev/null || true
echo "采集完成：$OUT"
echo "请只上传这个 txt；脚本未访问 /data，也不会修改系统或分区。"
