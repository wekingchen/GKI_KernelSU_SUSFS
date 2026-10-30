# Xiaomi 17 Pro OS4 Full Parity LKG

本文只记录当前已完成真机闭环的最终状态，不保留中间试错步骤。历史实验、探针和失败工作流已在收尾阶段从活动代码路径移除。

## 当前适用范围

- 设备：Xiaomi 17 Pro
- 代号：`pandora`
- 系统：HyperOS 4 `OS4.0.5.0.XBLCNXM`
- GKI：Android 16 KMI / 6.12.69
- 最终内核：
  `6.12.69-android16-6-os4r62-dspids-dscore-full-parity-kmi-4k`

不要把本结论外推到其他机型、其他 HyperOS 版本或 OTA 后的新 boot 布局。

## 最终 LKG 身份

```text
source_run_id=41068829461
image_sha256=244772c526f76a33fb96e7c6b8915f1d68e0f79b916bb1624127ccd6eee7a846
module_symvers_sha256=f17b4d56fc3b80497a36826e4c9907bd51939662025a739accef20c2c00e0ae8
fastboot_boot_sha256=6f1972757b1d731a2efd93e4db109df1c49fc2776de97f067b838182193eb228

persistent_package_run_id=41072834543
persistent_package=Xiaomi17Pro-pandora-OS4.0.5.0-R62-FULL-PARITY-AnyKernel3.zip
persistent_package_sha256=df1138d26ba02749cb9902a683d01ddc52693b53c279f16119f02b7e69be437f
```

唯一机器可读真值在：

```text
.github/config/pandora-os4-full-parity-lkg.env
```

## 已验证功能

- Built-in BakaSU Root
- SUSFS
- NoMount（内核侧）
- DroidSpaces：
  - PIDs Controller
  - PID / IPC / USER namespace
  - Macvlan
  - IPv6 NAT
  - devtmpfs 相关能力
- NTSync
- BBR，且当前默认拥塞控制为 `bbr`
- FQ / FQ_CODEL / CAKE
- WireGuard
- CIFS
- IPSet
- Baseband Guard
- Re-Kernel 11.7 + Generic Netlink

持久化刷入后已确认：

```text
sys.boot_completed=1
root context=u:r:ksu:s0
kernelsu LKM=not loaded
active LSM includes baseband_guard
cgroup.controllers includes pids
tcp_congestion_control=bbr
DroidSpaces self-check=all green
```

## 两个必须保留的 OS4 适配约束

### 1. PIDs 不使用普通 CONFIG_CGROUP_PIDS=y

直接启用 `CONFIG_CGROUP_PIDS=y` 的路线曾造成 KMI / vendor ABI 风险，已放弃。

当前 LKG 使用经过真机验证的 KMI-preserving 方案：保留 `CONFIG_CGROUP_PIDS=n`，复用原 `net_prio` subsystem slot，并在运行时暴露为 `pids`。

因此不要“纠正”为普通 PIDs 配置。

### 2. Baseband Guard 必须计入 MAX_LSM_COUNT

R62 原生 `lsm_count.h` 不认识外接的 `CONFIG_BBG`。若不增加 BBG 计数，Baseband Guard 虽然会编译且存在符号，但不会进入 active LSM 列表。

最终修复已经真机验证，active LSM 为：

```text
capability,landlock,safesetid,selinux,bpf,baseband_guard
```

不要移除这项兼容补丁。

## Re-Kernel

最终固定版本：

```text
Re-Kernel version: 11.7
Generic Netlink family: rekernel
```

旧 legacy netlink 保持关闭。

## 构建入口

活动工作流只保留：

```text
.github/workflows/xiaomi-sm8850-os4-lkg.yml
```

它会从固定 R62 源码和固定依赖重新构建 baseline 与 Full Parity LKG，并用已验证 SHA 做强校验，然后生成：

- 原始 Image / Module.symvers / final.config
- fastboot-boot-only 测试镜像
- AnyKernel3 持久化包

工作流不依赖历史 Run Artifact，因此旧 Actions 记录过期后不会断链。

## 新固件 / OTA

OTA 后不要直接沿用当前 LKG。先使用：

```text
.github/workflows/xiaomi-sm8850-os4-stock-intake.yml
```

只读检查新 `xm.zip` 与 stock boot，再重新建立版本级 fixture、ABI/KMI 基线和真机验证。

详细步骤见：

```text
docs/xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md
```

## 恢复基线

当前 OS4 已知可启动备份来自：

```text
build=OS4.0.5.0.XBLCNXM
slot=_a
stock/known-bootable backup sha256=
4f873abec68220c0028c11c8833e7ec8b9652f263e850f1ddb76d19913374653
```

该备份来自当时可启动的 LKM Root 状态，因此它是本机恢复基线，不宣称为完全未修改的原厂 pristine boot。

## 已明确放弃的路线

- ACK-R51：历史真机无法启动，不作为 OS4 基线。
- 普通 `CONFIG_CGROUP_PIDS=y`：不采用。
- Magic Mount：当前路线改为 NoMount。
- 依赖历史 Actions Artifact 的构建链：收尾后不再使用。
- 一次性 Re-Kernel runtime probe / PIDs ABI 分叉 / NoMount 诊断 workflow：验证完成后不保留为生产入口。
