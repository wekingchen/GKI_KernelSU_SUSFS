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

## 稳定 LKG 复现入口

稳定 LKG 的严格复现入口为：

```text
.github/workflows/xiaomi-sm8850-os4-lkg.yml
```

它会从固定 R62 源码和固定依赖重新构建 baseline 与 Full Parity LKG，并用已验证 SHA 做强校验，然后生成：

- 原始 Image / Module.symvers / final.config
- fastboot-boot-only 测试镜像
- AnyKernel3 持久化包

工作流不依赖历史 Run Artifact，因此旧 Actions 记录过期后不会断链。

## 自定义功能编译

当前 OS4 额外提供与旧 OS3 使用习惯一致的图形化选择入口：

```text
.github/workflows/xiaomi-sm8850-os4-custom.yml
小米17 Pro OS4 / 自定义内核
```

可选择：

- Root / SUSFS：
  - `bakasu-susfs`（默认）
  - `bakasu`
  - `none`
- SUSFS 扩展功能；
- NoMount；
- DroidSpaces 完整支持；
- NTSync；
- Baseband Guard；
- Re-Kernel 11.7；
- 网络增强（BBR / IPSet / FQ / FQ_CODEL / CAKE / WireGuard / CIFS）；
- CVE-2026-43499 / CVE-2026-53163 修复链审计。

依赖关系由构建脚本统一解析。NTSync 可独立于 DroidSpaces 开启；每次构建都会把最终实际生效值写入构建元数据。

### 默认组合

所有默认项保持开启时，选择必须复现当前 Full Parity 的配置、ABI/KMI 与 normalized Image。由于模块签名证书及 GNU build-id 会在每次构建时自动生成，raw Image SHA256 不要求与历史 LKG 字节级一致。

固定门禁：

```text
final.config SHA256=f31d8fc1fdc998f36c23ce599ac8be54c1d8ed9297e7733ae931be78000c8ef6
Module.symvers SHA256=f17b4d56fc3b80497a36826e4c9907bd51939662025a739accef20c2c00e0ae8
normalized Image SHA256=5b28d9aa9cb1581cbca185e49fe9be5d81433c10d8725df734a22fbf326dc889
```

正式自定义工作流 run `41112359117` 已通过全部门禁；其重建 Full Parity fastboot boot 镜像随后在 Xiaomi 17 Pro / OS4.0.5.0.XBLCNXM 真机临时启动成功，确认 Root、PIDs Controller、Baseband Guard 与 ZRAM/ZSMALLOC 模块链正常。因此 normalized-equivalent Full Parity 重建现在允许直接生成 AnyKernel3 持久化包。

### 自定义组合

只要任一功能与默认 LKG 不同：

- kernel release 使用 `-android16-6-os4r62-custom-4k`；
- 必须通过固定 KMI/ABI lock；
- 同时生成 `fastboot boot` 临时测试镜像与 AnyKernel3；
- AnyKernel3 文件名和包内 README 明确标记 `CUSTOM-UNVERIFIED`；
- 未经过该精确组合的真机临时启动验证前，不把它标记为“已验证组合”。

这样既保留旧 OS3 的“选择功能 → 编译 → 直接得到 AnyKernel3”使用方式，又把“可生成刷机包”和“已经真机验证”两个状态严格区分。

ABI lock 固定当前已验证基线的 19324 个基础导出及 CRC。允许的 51 个可选功能新增导出单独列在：

```text
.github/config/pandora-os4-r62-abi-allowed-new-exports.txt
```

boot 测试镜像直接由已真机验证 fixture 与 candidate Image 重建，不需要每次先完整重编 baseline。

### BakaSU Manager 与上游跟进

OS4 正式自定义工作流恢复旧 OS3 的上游跟随方式，并进一步保证同一次构建的内核与 Manager 来源一致：

- 每次 workflow 启动时先解析 `Baka-SU/BakaSU:main` 当前最新 SHA，并把这个 SHA 锁定为本次 run 的统一 BakaSU 来源；
- `bakasu` / `bakasu-susfs` 内核直接集成这个最新 `main` 提交，不再长期固定在历史 `OS4_BAKASU_COMMIT`；
- Manager 同样只接受 **与本次内核完全同一个 BakaSU SHA、同一个 KSU_VERSION** 的 BakaSU 官方成功构建产物，禁止 Manager / 内核版本错位；
- 如果 BakaSU 官方 Manager CI 在当前 main 提交刚推送时尚未完成，OS4 workflow 会轮询等待同 SHA 的 Manager，而不是回退到旧 APK；
- `OS4_BAKASU_COMMIT` 继续保留为“已完成真机验证的参考提交”，只用于判断最新 main 的 `kernel/` 子树是否变化；
- 如果最新 main 只更新 userspace / Manager，而 `kernel/` 子树与已验证参考相同，默认 Full Parity 仍可走现有 LKG 等价门禁；
- 如果最新 main 的 `kernel/` 子树发生变化，仍然继续构建最新内核，但自动降级为 `CUSTOM-UNVERIFIED`，继续经过 ABI/KMI 安全门禁并输出 AnyKernel3，直到该新内核完成真机验证；
- `root_mode=none` 时自动跳过 BakaSU Manager；
- 每次 OS4 自定义构建仍会只读检查 `zzh20188/GKI_KernelSU_SUSFS:dev` 和 `kernel-custom.yml` 的新功能变化，绝不自动覆盖 Xiaomi 专用路径。

历史已验证参考：

```text
VALIDATED_BAKASU_REFERENCE=d5e9e025b8b49155f8014684d64c91742b465f65
VALIDATED_KSU_VERSION=35252
VALIDATED_MANAGER=BakaSU_v4.2.0-rc3_35252-arm64-v8a-release.apk
```

从本策略生效后，上述提交只代表最后一个已验证参考点，不再代表每次构建固定使用的 BakaSU 版本。

### 暂未加入菜单

ZRAM / LZ4K / LZ4KD 仍属于待适配功能，在完成 OS4 模块形态、ABI 和真机验证之前，不提供无效或未经验证的编译开关。

---

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
