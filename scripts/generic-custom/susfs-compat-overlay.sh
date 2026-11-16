#!/usr/bin/env bash
# 只在本仓自定义构建副本运行；所有修复只写入 Runner 下载的内核树。
set -euo pipefail
: "${KERNEL_ROOT:?需要 KERNEL_ROOT 环境变量}"
: "${KSU_VARIANT:?需要 KSU_VARIANT 环境变量}"
cd "$KERNEL_ROOT/common"
if [ ! -f fs/susfs.c ]; then
  echo "没有 SUSFS 源码，无需兼容处理"
  exit 0
fi

# 部分旧 SUSFS 补丁会留下未使用的静态凭据辅助函数，开启 Werror 时失败。
if grep -qE '^static (struct cred \*|void )susfs_(switch_to_ksu_domain|restore_creds)\(' fs/susfs.c; then
  echo "为旧 SUSFS 凭据辅助函数标记 __maybe_unused"
  sed -i -E 's/^static (struct cred \*|void )(susfs_switch_to_ksu_domain|susfs_restore_creds)\(/static __maybe_unused \1\2(/' fs/susfs.c
fi

# 仅缺失时补入 priority UID 选项；新版 SukiSU-Nova 已提供则不重复添加。
KSU_KCONFIG="$KERNEL_ROOT/KernelSU/kernel/Kconfig"
if [ -f "$KSU_KCONFIG" ] \
  && [ -f include/linux/susfs.h ] \
  && grep -qF 'CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER' include/linux/susfs.h \
  && ! grep -qE '^config KSU_SUSFS_PRIORITY_UID_FILTER$' "$KSU_KCONFIG" \
  && grep -RqsE --include='*.c' 'susfs_(parse_priority_app_strings|set_priority_uid_filter)\(' "$KERNEL_ROOT/KernelSU/kernel"; then
  echo "为旧 $KSU_VARIANT 内核源码补齐 SUSFS priority UID 配置"
  cat >> "$KSU_KCONFIG" <<'EOF'

config KSU_SUSFS_PRIORITY_UID_FILTER
	bool "Enable to allow adding user-defined uids that will be hidden from getpriority/setpriority/ioprio_get/ioprio_set syscall"
	depends on KSU_SUSFS
	default y
	help
	  - Allow hiding user-defined uids from syscalls like getpriority/setpriority/ioprio_get/ioprio_set.
	  - Effective on all processes with uid >= 10000.
EOF
fi
