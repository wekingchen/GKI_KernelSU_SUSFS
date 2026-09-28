# 小米 17 系列 / SM8850 — Android 16 / Linux 6.12.23

本文档记录本仓库针对小米 17 系列（Qualcomm SM8850）的专用内核构建方案、真机验证结果、源码基线、CI 校验、刷入范围以及上游同步与恢复机制。

该构建路径与仓库原有通用 GKI 工作流相互隔离。小米相关实现已经完整合入默认分支 `dev`，但尽量限制在本仓库独有的 Xiaomi 文件和目录中，从而在继续同步上游 `zzh20188/GKI_KernelSU_SUSFS:dev` 时降低冲突概率。

## 当前仓库结构

小米 17 系列构建目前采用“一个人工入口 + 一个内部构建工作流”的结构：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`：唯一人工编译入口，名称为 **Xiaomi 17 系列 - 自定义内核**。负责接收图形界面中的设备、Root、SUSFS、DroidSpaces、NTSync、ZRAM、BBG、Re-Kernel、NoMount、网络增强、CVE 修复等选项，并同时调用内核构建和 ReSukiSU Manager 获取流程。
- `.github/workflows/kernel-xiaomi-sm8850.yml`：内部实际构建工作流。负责源码准备、功能集成、缓存、编译、校验、AnyKernel3 打包以及 PR 回归测试；不再提供独立的 `workflow_dispatch` 人工入口，只通过 `workflow_call` 或 PR 事件运行。
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`：小米 SM8850 固定源码、工具链和关键版本配置。
- `scripts/xiaomi-sm8850/`：小米专用源码准备、功能集成、构建、校验和打包脚本。
- `docs/xiaomi-sm8850.md`：本文档。

日常人工编译只需要运行 **Xiaomi 17 系列 - 自定义内核**。

## 已支持设备范围

| 机型 | 代号 | 平台 | 当前状态 |
|---|---|---|---|
| 小米 17 | `pudding` | Qualcomm SM8850 | 支持构建，待同等级真机验证 |
| 小米 17 Pro | `pandora` | Qualcomm SM8850 | 主验证设备，已真机验证 |
| 小米 17 Pro Max | `popsicle` | Qualcomm SM8850 | 支持构建，待同等级真机验证 |

小米 MiCode 的 `popsicle-w-oss` 分支将这一设备家族标识为 `release-w-qcom-sm8850`。其根 BSP 内核树基于 Linux 6.11，因此这里只将其作为厂商 BSP 参考，不直接作为 Linux 6.12.23 启动内核 Image 的源码来源。

## 原厂内核依据

已上传并检查的小米 17 Pro OS3.0.319.0.WBLCNXM 原厂 boot 镜像包含以下内核版本：

```text
6.12.23-android16-5-g75e9b1c7ae7c-abogki463945075-4k
```

此前曾导致循环开机的旧通用构建使用：

```text
6.12.23-android16-5-g13ff069897df9-ab10024759-4k
```

对应 Actions 日志证明，`g13ff069...` 当时确实是 Google `deprecated/android16-6.12-2025-06` 源码分支的实际最新提交，而不只是人为修改的版本字符串。

因此，仅仅匹配：

```text
6.12.23 / android16-5 / 4K
```

并不足以证明与小米厂商模块兼容。对于此设备，源码基线、KMI、工具链及实际提交来源都需要同时控制。

## 源码方案

小米工作流目前保留两套固定源码方案，但两者的验证等级并不相同。

> **重要：截至目前，本项目所有成功编译并用于小米 17 Pro（`pandora`）真机刷入、启动验证和运行时功能验证的内核，全部来自 `gold-cctv`。**
>
> `ack-r51` 现已完成一次与当前推荐功能组合一致的 CI 全功能编译验证，但尚未进行真机刷入验证。因此它可以描述为“CI 编译通过”，不能描述为“真机已验证可用”。日常正式编译和真机使用仍以 `gold-cctv` 为稳定路径。

### `gold-cctv` — 默认推荐基线

这一路径采用 DroidSpaces 小米 17 系列条目以及已知可启动 Gold 6.12.23 内核包所对应的公开源码家族：

- 仓库：`cctv18/android_gki_kernel_common`
- 分支家族：`android16-6.12-2025-06`
- 固定提交：`9e91eb74a201e8cee839c8db6d642ff9b8408388`

这里将它定义为**与 Gold 构建体系兼容的公开源码线**，并不声称这个精确提交就是此前手机上测试过的某个 Gold ZIP 二进制的唯一源码来源。

由于公开分支会继续前进，本工作流固定使用明确提交，而不是跟随移动中的分支最新提交。

### `ack-r51` — 官方 ACK 对照基线（CI 全功能编译已通过，未真机验证）

这一方案使用 Android 16 / Linux 6.12 官方 ACK 2025-06 后期修订版作为干净对照。当前已经完成一次与推荐功能组合一致的完整 CI 编译、最终配置校验和 AnyKernel3 打包，但尚未将其产物刷入小米 17 Pro，因此它仍不属于真机已验证路径：

- 标签：`android16-6.12-2025-06_r51`
- 提交：`5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- KMI 代数：5
- Clang：`r536225`

从工作流设计上，两套方案使用同一套固定 ACK 工具链/构建支持快照，但采用不同的构建方式：

- `gold-cctv`：直接执行 `make gki_defconfig Image`，贴近公开 Gold/cctv18 构建体系，只生成启动所需内核 Image，避免 Kleaf 对无关 system-DLKM 模块集合的额外要求。
- `ack-r51`：通过 Kleaf/Bazel 执行 `//common:kernel_aarch64_dist`，保留严格 KMI 校验，但不再人为强制 ThinLTO。原因是 R51 的 `CONFIG_RUST` 在 `DEBUG_INFO_BTF=y` 时要求非 LTO；强制 ThinLTO 会导致 Rust Binder 配置被静默关闭并使 `rust_binder.ko` 缺失。

实际执行构建时，构建方式和最终 LTO 设置会写入产物中的 `build-metadata.txt`。目前已有实际产物和真机验证记录的均为 `gold-cctv`。

## 当前自定义构建器

小米专用路径已经完成最初的 A/B/C 兼容性阶梯验证，目前已经进入可自由选择功能的自定义构建阶段。

小米 17 Pro（`pandora`）已完成的主要真机验证如下。**以下所有条目使用的内核源码均为 `gold-cctv`，没有任何一项来自 `ack-r51`：**

- A / 基础内核：#60 —— 成功启动，并通过短时间硬件及稳定性检查。
- B / ReSukiSU：#62 —— 成功启动；Manager 显示版本代码 35184；Root 授权正常。
- C / ReSukiSU + SUSFS：#63 —— 成功启动；SUSFS v2.3.0 可正常识别并工作。
- 全功能候选：#76 —— 成功启动，首次开机后的基础检查未发现明显异常。
- 当前自定义链路：后续自定义构建已完成缓存、DroidSpaces/NTSync、直接 AnyKernel3 ZIP、ReSukiSU Manager 等整套流程验证；最新已刷入版本在小米 17 Pro 上未发现异常。

#76 全功能候选在已经验证的 C 基础上，同时启用了除 KPM 之外当时通过独立 CI 验证的全部小米可选功能：

- SUSFS 扩展功能
- ZRAM / LZ4 增强
- Baseband Guard（BBG）
- Re-Kernel
- NoMount
- Android 16 / Linux 6.12 网络增强
- DroidSpaces
- NTSync
- CVE-2026-43499 / CVE-2026-53163 修复链

KPM 目前仍保持关闭。原因是当前此构建链使用的 ReSukiSU 主线没有声明 `CONFIG_KPM`。小米集成脚本会直接拒绝不受支持的 KPM 请求，而不是在实际未启用的情况下伪装成已开启。

### 推荐的人工编译默认值

用户无需修改 YAML。唯一人工入口 **Xiaomi 17 系列 - 自定义内核** 已设置为当前推荐的小米 17 Pro 配置：

- 设备：小米 17 Pro（`pandora`）
- 源码：Gold/cctv18 Linux 6.12.23（当前唯一完成实际编译与真机验证的源码路径）
- Root：ReSukiSU + SUSFS
- SUSFS 扩展：开启
- ZRAM / LZ4K / LZ4KD：开启
- Baseband Guard：开启
- Re-Kernel：开启
- 网络增强：开启
- DroidSpaces：开启
- NTSync：开启
- CVE 修复链：开启
- KPM：关闭，因为当前 ReSukiSU 主线没有声明 `CONFIG_KPM`
- **NoMount：默认关闭。** 使用 Magic Mount 的 ReSukiSU 用户仅为了正常使用模块并不需要开启 NoMount；只有明确准备使用 NoMount VFS 注入 / Metamodule 路径时才建议启用。
- 默认产物模式：仅直接发布 AnyKernel3 ZIP

图形界面同时提供小米 17（`pudding`）和小米 17 Pro Max（`popsicle`），但这两个设备目前还没有获得与 `pandora` 同等级的真机验证。

PR 回归测试与用户默认配置故意不同：PR 的 `full` 组合回归仍会启用 NoMount，以确保这一可选集成持续获得编译回归覆盖。

## 验证等级

以下三种状态必须严格区分，不能混为一谈。`gold-cctv` 已达到 CI 集成验证、真机启动验证和多项运行时功能验证；`ack-r51` 当前只达到第 1 级 CI 集成验证，尚未达到第 2 级真机启动验证和第 3 级功能行为验证：

1. **CI 集成验证通过**：补丁和配置成功集成，内核成功编译，并通过最终自动校验。
2. **真机启动验证通过**：生成的 AnyKernel3 可刷包能够在小米 17 Pro 上正常启动。
3. **功能行为验证通过**：对应功能已经在真机上实际调用，并确认运行时行为符合预期。

#74 已证明各个可选功能可以分别达到第 1 级；#75/#76 已证明组合后的全功能配置达到第 1 级；#76 达到第 2 级。

在 2026-09-28 对运行中的小米 17 Pro 进一步检查后，多项功能还完成了额外运行时验证：

| 功能 | 真机依据 | 当前结论 |
|---|---|---|
| ZRAM | `/dev/block/zram0` 作为 12 GiB Swap 正常工作；LZ4K/LZ4KD 后端已注册；当前 HyperOS 实际压缩算法仍为 `lzo-rle` | 运行时已验证 |
| Baseband Guard | `dmesg` 中出现实时 `baseband_guard` 事件，并按 SELinux 域识别真实进程 | 运行时已验证 |
| SUSFS 扩展 | `ksu_susfs v2.3.0 show enabled_features` 显示 SPOOF_UNAME、HIDE_KSU_SUSFS_SYMBOLS、SPOOF_CMDLINE_OR_BOOTCONFIG、OPEN_REDIRECT、SUS_MAP | 运行时接口已验证 |
| 网络增强 | BBR 已注册并可在运行时选择；存在 IPSet 符号；iptables nat/mangle/raw/filter 表存在；CIFS 已注册 | 运行时已验证 |
| NTSync | `/dev/ntsync` 杂项设备存在，NTSync 运行时符号与初始化调用均存在 | 运行时已验证 |
| DroidSpaces 前置能力 | 使用 `unshare` 成功创建 IPC/PID/User namespace；PID namespace 中子进程以 PID 1 运行 | 内核/运行时前置能力已验证；完整用户态负载仍待验证 |
| Re-Kernel | 内置符号存在；只读 Generic Netlink `GET_VERSION` 探测从运行内核返回 `11.7` | 用户态 ABI 已验证；未破坏性测试各 Hook 行为 |
| NoMount | 内置符号存在；只读 NoMount `NM_CMD_GET_VERSION` 探测从运行内核返回 `20` | 用户态 ABI 已验证；验证期间未修改路径规则 |
| CVE 修复链 | 补丁、配置和编译校验均通过 | 不在真机上主动触发漏洞进行测试 |

这里故意采用保守标准：仅有内置符号存在，并不等于已经证明对应用户态协议或每一条 Hook 路径都实际执行过。

## ACK-R51 CI 验证记录

2026-09-28，ACK-R51 对照路径完成一次全功能 CI 验证。

对应一次性验证运行：

```text
Xiaomi ACK-R51 一次性全功能验证 #4
Run ID: 36399059661
```

结果为 `success`，并通过以下关键校验：

- 设备：`pandora`
- 变体：`resukisu-susfs`
- 源码：`ack-r51`
- common 提交：`5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- Android 分支：`android16-6.12`
- 内核版本：`6.12.23`
- KMI 代数：5
- 页面大小：4K
- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- Kleaf 严格 KMI 校验通过
- ReSukiSU 内建
- SUSFS 与扩展功能开启
- ZRAM / LZ4K / LZ4KD 开启
- Baseband Guard 开启
- Re-Kernel 开启
- 网络增强开启
- DroidSpaces 开启
- NTSync 开启
- CVE 修复链开启
- NoMount 关闭
- KPM 关闭

最终版本字符串：

```text
6.12.23-android16-5-4k
```

此前 Kleaf 非 stamp 模式会自动加入 `-maybe-dirty` 占位符。当前 ACK 专用构建逻辑仅在 `kleaf-dist` 路径中移除这一占位符，并增加校验防止其重新出现；不会修改 `gold-cctv` 的版本字符串逻辑。

ACK-R51 全功能编译过程中还修正了两个只属于 ACK/Kleaf 的兼容问题：

1. Xiaomi boot-only 方案将 ZRAM、ZSMALLOC 和 NETFS 相关能力直接编入 Image，因而不再生成对应 `.ko`。ACK 专用逻辑会从 Kleaf 的预期 GKI 模块输出列表中移除这些已明确改为 built-in 的模块项。
2. 不再强制 ThinLTO，以保持 R51 的 Rust Binder 官方配置可成立。

这些兼容处理均位于 `ack-r51 / kleaf-dist` 分支，不修改 `gold-cctv / make-image` 的源码、构建目标、缓存、版本字符串或打包流程。

**当前结论：ACK-R51 已完成 CI 全功能编译验证，但尚未进行真机刷入和运行时验证。**

## Root 与 SUSFS 版本追踪

正常自定义构建会跟随指定上游分支获取 ReSukiSU / SUSFS，但每次都会把最终解析到的精确提交写入构建产物，方便复现。

当前已经获得真机验证的基础版本：

- ReSukiSU：`fa8311f632a215b5381ec644627c6198d1e8a13e`，标签 `v4.2.0-rc3`，版本代码 `35184`
- SUSFS `gki-android16-6.12`：`b213c54126fb243595ce7876e91d84d6e0861fec`，版本 `v2.3.0`
- AnyKernel3：`dca9dc370838d919d56c1f59ec78b27a14a72c68`

ReSukiSU 以内置方式编译，使用 `CONFIG_KSU=y`，不采用 LKM 模式。

SUSFS 补丁采用快速失败策略：

- 先进行 dry-run 检查；
- 补丁应用失败立即中止；
- 出现任何 `.rej` 文件都直接判定构建失败。

## #76 全功能候选版本来源

已完成真机启动验证的 #76 全功能产物，其工作流提交为：

```text
adce911ce19573f148ada2c066f2b52b93a97bdf
```

校验后的内核版本为：

```text
6.12.23-android16-5-g9e91eb74a201-xiaomi-4k
```

产物中记录的主要功能源码提交包括：

- ZRAM 补丁栈：`2844bf492f557fb39113fc93a2dd1602e05790d7`
- Re-Kernel：`ac08296174d7fb2801c0eee1084f067a34f8a0fe`
- NoMount：`6b1be186322d4e0bdc465cf27f6fc0d3679087c6`
- DroidSpaces：`b24eec0194e9b0ce8981152eba4603b40bf919e5`

对应产物校验和：

```text
Image
49c26004039b0230ff207c7183483685ff9556a106c31d95866eb609b7f23277

Xiaomi17Series-pandora-Android16-6.12.23-resukisu-susfs-AnyKernel3.zip
998535cb5f0946460011a1398fff5e933300b29f3ab680e1ded33ec78b6004fa
```

## CI 安全校验

最终生成的内核 Image 必须通过以下检查：

- ARM64
- Linux 6.12.23
- `android16-5`
- 4K 页面大小
- KMI 第 5 代
- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- 可重复、确定性的本地版本字符串，不能意外多出结尾 `+`
- Gold 路径必须精确匹配固定源码提交
- 启用 ReSukiSU / SUSFS 时必须记录最终解析到的来源提交
- 用户请求开启的可选功能必须真实出现在最终配置中
- 不允许存在补丁拒绝文件

`gold-cctv` 路径通过已知兼容的直接 make 方式构建内核 Image，也是目前唯一完成真机刷入和运行时验证的源码路径；`ack-r51` 已完成 Kleaf/Bazel 全功能 CI 编译验证，但仍未进行真机刷入。

PR CI 会首先对小米脚本执行 `bash -n` 语法检查，然后根据改动范围选择回归等级。

当前主要回归配置：

- `baseline`：已获得真机验证的 ReSukiSU + SUSFS 核心组合，关闭额外可选功能。
- `full`：同时开启当前 CI 支持的全部小米可选功能，但 KPM 除外。

此前 #74 的十配置矩阵仍作为各个可选功能可以独立编译通过的历史证据。

## 缓存策略

小米 Gold 构建路径使用三层安全缓存：

- 固定 Gold common Git 对象仓库缓存
- 固定 `r536225` 工具链缓存
- ccache 编译对象缓存

common 源码缓存永远不会直接作为已经被修改过的工作树使用。每次构建都会从缓存对象重新创建干净 checkout，然后再应用 ReSukiSU、SUSFS 和各项可选功能。

内核 `out/` 目录故意不做缓存。

实际热缓存测试已经证明，在相同功能配置下，单次新增可缓存编译调用的 ccache 命中率可以达到约 99.9%，完整工作流耗时也会从冷缓存构建的大约二十多分钟显著下降。

### ACK-R51 缓存结论

ACK-R51 当前**故意不启用跨 GitHub Runner 的持久编译缓存**，正式构建保持已验证通过的 Kleaf `--config=fast` 路径，缓存仅限单次 runner 生命周期。2026-09-28/29 已实际验证以下方案均不适合作为正式 ACK 缓存：

- Bazel `--disk_cache`：热缓存可命中大量外围 action，但最耗时的 `KernelBuild` 仍完整执行，整体耗时几乎不变。
- Kleaf 持久 `--cache_dir`：能够恢复约 1 GiB 的旧 `OUT_DIR`，但 fresh runner 的源码重新同步后仍触发主内核重编，未得到有效加速。
- ACK ccache wrapper：将 wrapper 强行置于 Kleaf toolchain 前方会改变 R51 的编译器可用性判定，导致 `CONFIG_RUST`、`CONFIG_ASHMEM_RUST` 和 `CONFIG_ANDROID_BINDER_IPC_RUST` 被移除，破坏官方 R51 配置语义，因此明确弃用。

因此 ACK-R51 以**构建正确性、Rust Binder、strict KMI 和可复现性优先**；除非未来 Kleaf 官方提供适合临时 CI runner 的稳定缓存接口，否则不再为 ACK 强行注入跨 runner 编译缓存。此结论只适用于 `ack-r51 / kleaf-dist`，不会改变已经验证有效的 `gold-cctv` 缓存策略。

## AnyKernel3 打包行为

生成的 AnyKernel3 包是**仅刷 boot 的设备限定包**，其中只包含内核 Image 和必要的 AnyKernel3 脚本/工具。

其行为包括：

- 目标分区为 `boot`
- 自动识别当前活动槽位
- 不修改 vbmeta 标志
- 使用 `split_boot; flash_boot;`
- 不打包或刷写 `init_boot`
- 不打包或刷写 `vendor_boot`
- 不打包或刷写 `vendor_kernel_boot`
- 不打包或刷写 `dtbo`
- 不打包或刷写 `vbmeta`

人工编译默认使用“仅上传 AnyKernel3.zip”模式时，可刷 ZIP 会直接发布到固定 Release，而不是再套一层 GitHub Artifact ZIP。

## ReSukiSU Manager

人工入口 **Xiaomi 17 系列 - 自定义内核** 在 Root 模式不为 `none` 时，会并行调用共享的 `get-manager.yml`：

- 自动识别当前 ReSukiSU 版本代码
- 查找与内核版本代码最匹配的 ReSukiSU Manager 构建
- ReSukiSU 模式只保留 ARM64 release APK
- 同时获取 SUSFS 模块产物

这一 Manager 获取任务与小米内核构建逻辑分离，因此不会影响内核缓存和编译流程。

## 后续真机验证方向

当前完整功能栈已经在 `pandora` 上完成启动和大量运行时检查。仍可继续补充但不影响日常使用的验证项目包括：

- 如有必要，在安全条件下实际走一次 Re-Kernel Hook 路径；其 Generic Netlink 用户态 ABI 已经验证。
- 如有必要，使用可丢弃测试路径实际验证一次 NoMount 路径规则；其用户态 ABI 已经验证。
- 运行真实 DroidSpaces 用户态/容器工作负载；namespace 创建和 NTSync 已经验证。
- 继续进行正常日常使用观察；不要为了验证 CVE 修复而主动在真机上触发漏洞。

只有在剩余用户态路径也实际运行后，才适合将整个功能栈描述为“全部功能行为均已完整验证”。

`pudding` 和 `popsicle` 虽属于同一 SM8850 构建路径，但目前仍未获得与 `pandora` 相同等级的真机验证。

## 上游同步策略

小米 17 系列支持已经完全合入默认分支 `dev`，不再依赖长期功能分支。

为了降低 fork 与上游同步时的冲突概率，小米定制尽量只放在本仓库独有的文件和目录中：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`
- `.github/workflows/kernel-xiaomi-sm8850.yml`
- `.github/workflows/xiaomi-sm8850-watchdog.yml`
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`
- `scripts/xiaomi-sm8850/`
- `docs/xiaomi-sm8850.md`

日常同步 `zzh20188/GKI_KernelSU_SUSFS:dev` 时，应使用正常的 GitHub **Sync fork / Update branch / merge** 流程。

不要使用以下方式把本地 `dev` 强行覆盖成上游：

- `git reset --hard upstream/dev`
- force push
- Discard commits

正常 merge 同步只会合并上游发生变化的内容，本仓库独有的小米文件会继续保留。只有当上游未来新增同名文件或修改同一路径时，才需要人工处理真实冲突。

同步完成后可以运行一次 **Xiaomi 17 系列 - 自定义内核**，确认 dispatcher 仍能正常调用本地 `kernel-xiaomi-sm8850.yml`。

## 误点 Discard commits 的恢复

仓库保留长期恢复分支 `xiaomi-sm8850-stable`。该分支不参与日常上游同步，用于保存已经确认可用的小米 17 系列实现。

如果误操作导致默认分支 `dev` 被重置为上游状态：

1. 不要继续执行强制同步。
2. 不要删除恢复分支。
3. 优先将 `xiaomi-sm8850-stable` 通过正常 Pull Request / merge 恢复到 `dev`。
4. 如果此时上游已经存在新的提交，则正常合并两边改动并处理真实冲突。
5. 禁止为了恢复而直接 force push 覆盖历史。

恢复后应确认以下路径重新存在：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`
- `.github/workflows/kernel-xiaomi-sm8850.yml`
- `.github/workflows/xiaomi-sm8850-watchdog.yml`
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`
- `scripts/xiaomi-sm8850/`
- `docs/xiaomi-sm8850.md`

然后运行一次 **Xiaomi 17 系列 - 自定义内核** 完成 CI 验证。

## 稳定分支与恢复层级

为了避免日常 `dev` 开发、上游同步或误点 **Discard commits** 影响已经验证过的小米方案，仓库采用三层恢复结构。

### 第一层：`dev`

日常开发、功能调整以及上游同步都发生在这里。

### 第二层：`xiaomi-sm8850-stable`

这是可移动的稳定恢复点。

只有在对应版本满足以下条件后才推进：

- CI 正常
- 核心工作流结构正常
- 修改不会破坏已确认稳定的内核方案
- 涉及实际内核行为变化时，原则上应获得对应真机确认

该分支不需要用户手动维护。

### 第三层：`xiaomi-sm8850-lkg-20260928`

这是永久保留的**最后已知可用版本（LKG）**里程碑。

它指向第一阶段完成合并、且对应核心实现已经在小米 17 Pro / `pandora` 上获得真机验证的提交：

```text
a6739500cf10f9d73453d6eb4f86bf17c6e722a4
```

这个 LKG 分支不随 `dev` 或 `stable` 更新。

正常情况下用户只使用 `dev`。不要对 `xiaomi-sm8850-stable` 或 LKG 分支执行 Sync fork、Discard commits、force push、reset 或删除操作。

如果未来 `dev` 被误重置：

- 首选从 `xiaomi-sm8850-stable` 恢复。
- 如果 stable 本身也存在疑问，则使用 `xiaomi-sm8850-lkg-20260928` 作为最后兜底。
- 恢复过程禁止 force push 覆盖已有历史。

## 自动看门狗

默认分支 `dev` 内置：

```text
.github/workflows/xiaomi-sm8850-watchdog.yml
```

它负责自动检查小米专用方案是否仍然完整。

当前检查内容包括：

- 每天定时运行一次
- 小米关键工作流、配置、脚本或本文档发生改动时立即运行
- 校验小米关键文件和目录是否仍然存在
- 校验 dispatcher 仍调用本地 `kernel-xiaomi-sm8850.yml`
- 检查是否意外重新出现 `xiaomi-sm8850-pandora` 跨分支依赖
- 校验 `xiaomi-sm8850-stable` 是否仍存在
- 校验固定 LKG 分支是否仍存在
- 校验 LKG 是否仍指向预期提交，没有被意外移动
- 异常时让该 Actions 运行明确失败
- 在条件允许时，从 stable 向 dev 创建普通恢复 PR
- 不执行自动 merge
- 不执行 force push
- 不执行 reset
- 不执行分支删除

由于 GitHub 的定时工作流必须依赖默认分支中的 workflow 文件，如果整个 `dev` 被 **Discard commits** 重置成上游、连 watchdog 文件本身一起消失，那么同仓库 Action 无法继续检查自己。

因此另保留一个低频外部兜底，只负责确认以下三项仍存在：

- `xiaomi-sm8850-watchdog.yml`
- `xiaomi-sm8850-stable`
- `xiaomi-sm8850-lkg-20260928`

日常完整检查由 GitHub Actions 完成，外部兜底只用于覆盖“看门狗本身被一起删除”的极端情况。

## 维护原则

后续维护遵循以下原则：

- 用户日常只操作 `dev` 和 **Xiaomi 17 系列 - 自定义内核**。
- 不要求用户手动维护 stable 或 LKG。
- 内核功能修改优先在 `dev` 完成并经过 CI。
- 真机确认稳定后，再推进 `xiaomi-sm8850-stable`。
- 永久 LKG 不移动。
- 上游同步使用正常 merge/Sync fork，不使用强制覆盖。
- 小米专用逻辑继续限制在独立文件和目录中，避免污染上游通用 GKI 工作流。
