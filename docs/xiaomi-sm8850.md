# 小米 17 系列 / SM8850 — Android 16 / Linux 6.12.23

本文档记录本仓库针对小米 17 系列（Qualcomm SM8850）的专用内核构建方案、真机验证结果、源码基线、CI 校验、刷入范围以及上游同步与恢复机制。

该构建路径与仓库原有通用 GKI 工作流相互隔离。小米相关实现已经完整合入默认分支 `dev`，但尽量限制在本仓库独有的 Xiaomi 文件和目录中，从而在继续同步上游 `zzh20188/GKI_KernelSU_SUSFS:dev` 时降低冲突概率。

## 当前仓库结构

小米 17 系列构建目前采用“一个人工入口 + 一个内部构建工作流”的结构：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`：唯一人工编译入口，名称为 **Xiaomi 17 系列 - 自定义内核**。负责接收图形界面中的设备、Root、SUSFS、DroidSpaces、NTSync、ZRAM、BBG、Re-Kernel、NoMount、网络增强、CVE 修复等选项，并同时调用内核构建和 BakaSU Manager 获取流程。
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

当前保留两套固定源码方案，二者都已经在小米 17 Pro（`pandora`）完成真机启动验证，但定位不同：

- `gold-cctv`：默认日用路径。构建简单、已有更完整的真机运行时验证和缓存收益。
- `ack-r51`：官方 ACK R51 对照路径。用于验证更接近 Google ACK 的源码/构建行为，并保留 Kleaf/Bazel 构建链。

### `gold-cctv` — 默认日用基线

- 仓库：`cctv18/android_gki_kernel_common`
- 分支家族：`android16-6.12-2025-06`
- 固定提交：`9e91eb74a201e8cee839c8db6d642ff9b8408388`
- 构建方式：`make gki_defconfig` + `Image`

在 cctv18 这条 fork 历史中，该固定提交以官方 R51 common 提交 `5a0e85dd...` 为祖先，向前增加 18 个提交；这些提交混合了 Android/common 后续修复以及 cctv18 的构建/功能改动。源码里存在 ADIOS、TCP Brutal、Re-Kernel 等附加代码，并不代表最终成品默认启用它们；本项目仍以最终 `.config` 和独立功能集成为准。

`gold-cctv` 继续作为默认值，主要因为它已经积累了更完整的 `pandora` 运行时验证，并且直接 make + ccache 路径的构建速度更适合日常使用。

### `ack-r51` — 官方 ACK R51 对照基线

- 标签：`android16-6.12-2025-06_r51`
- common 提交：`5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- KMI 代数：5
- Clang：`r536225`
- 构建方式：Kleaf/Bazel `//common:kernel_aarch64_dist`

ACK 源码在进入 Xiaomi 兼容层之前会先验证原始 `kernel_aarch64` 目标仍保持 stock strict KMI 配置；随后只对最终 Xiaomi 构建关闭 `kmi_enforced`、`kmi_symbol_list_strict_mode`、`trim_nonlisted_kmi`，并移除 base KMI symbol list / protected-module list，同时保留 `CONFIG_MODULE_SCMVERSION=y`。

这样做的原因来自真机结果：最初 strict-policy ACK 构建能够通过 CI，但 `pandora` 无法完成启动；放宽 trimming / protected-module policy 后的 Xiaomi compatibility A 在 Run #7（Run ID `36511075743`，HEAD `17576f5465d55a17b9ec529e450b1a2bd0e3b79b`）成功刷入并正常启动。

因此 ACK 当前的准确描述是：**官方 R51 源码 + Xiaomi 专用 KMI 兼容策略**，而不是“完全按 Google strict GKI policy 输出的原样 R51”。

构建产物会同时记录：

- `source_kmi_source_mode`：源码进入 Xiaomi 层前的策略；ACK 为 `kleaf-strict`。
- `source_kmi_mode`：最终实际构建策略；ACK 为 `kleaf-xiaomi-compat`。

两条路径都可正常启动，但 ACK 目前获得的真机验证主要是启动/基础可用性；Gold 已有更多运行时功能验证，所以日常默认仍保持 `gold-cctv`。
## 当前自定义构建器

小米专用路径已经完成最初的 A/B/C 兼容性阶梯验证，目前进入可自由选择功能的自定义构建阶段。

Gold 路径在小米 17 Pro（`pandora`）上的主要历史里程碑如下：

- A / 基础内核：#60 —— 成功启动，并通过短时间硬件及稳定性检查。
- B / BakaSU：#62 —— 成功启动；Manager 显示版本代码 35184；Root 授权正常。
- C / BakaSU + SUSFS：#63 —— 成功启动；SUSFS v2.3.0 可正常识别并工作。
- 全功能候选：#76 —— 成功启动，首次开机后的基础检查未发现明显异常。
- 当前自定义链路：后续自定义构建已完成缓存、DroidSpaces/NTSync、直接 AnyKernel3 ZIP、BakaSU Manager 等整套流程验证；最新已刷入版本在小米 17 Pro 上未发现异常。
- ACK-R51 Xiaomi compatibility：Run #7 / `36511075743` 已完成真机刷入并正常启动，证明当前 ACK 兼容策略可以在 `pandora` 使用。

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

KPM 目前仍保持关闭。原因是当前此构建链使用的 BakaSU 主线没有声明 `CONFIG_KPM`。小米集成脚本会直接拒绝不受支持的 KPM 请求，而不是在实际未启用的情况下伪装成已开启。

### 推荐的人工编译默认值

唯一人工入口 **Xiaomi 17 系列 - 自定义内核** 当前默认值为：

- 设备：小米 17 Pro（`pandora`）
- 源码：`gold-cctv`（默认日用；`ack-r51` 保留为官方 R51 对照）
- Root：BakaSU + SUSFS
- SUSFS 扩展：开启
- ZRAM / LZ4K / LZ4KD：开启
- Baseband Guard：开启
- Re-Kernel：开启
- NoMount VFS 注入：开启
- 网络增强：开启
- DroidSpaces：开启
- NTSync：开启
- CVE-2026-43499 / CVE-2026-53163 修复链：开启
- KPM：关闭；当前 BakaSU 主线没有声明 `CONFIG_KPM`
- 产物模式：仅上传 AnyKernel3 ZIP

图形界面同时提供小米 17（`pudding`）和小米 17 Pro Max（`popsicle`），但这两个设备还没有获得与 `pandora` 相同等级的真机验证。

PR 回归不再机械地每次跑 Full：文档/dispatcher/watchdog 修改不触发内核编译；Gold 专属脚本只回归 Gold；共享核心脚本会回归 Gold + ACK baseline；功能集成或固定构建配置变化时才对 Gold + ACK 跑 full 组合。
## 验证等级

以下三种状态必须严格区分，不能混为一谈。当前 `gold-cctv` 和 `ack-r51` 都已达到 CI 集成验证和 `pandora` 真机启动验证；Gold 另外完成了更多运行时功能验证，ACK 暂时不把“能启动”等同于“全部功能行为都已验证”：

1. **CI 集成验证通过**：补丁和配置成功集成，内核成功编译，并通过最终自动校验。
2. **真机启动验证通过**：生成的 AnyKernel3 可刷包能够在小米 17 Pro 上正常启动。
3. **功能行为验证通过**：对应功能已经在真机上实际调用，并确认运行时行为符合预期。

#74 已证明各个可选功能可以分别达到第 1 级；#75/#76 已证明 Gold 全功能组合达到第 1 级，#76 达到第 2 级；ACK compatibility Run #7 也达到第 2 级。

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

## ACK-R51 兼容性验证记录

2026-09-29，第一版 ACK-R51 全功能 AnyKernel3 虽然 CI 通过，但在 `pandora` 上停留于 Xiaomi HyperOS 启动画面。这证明“官方 ACK + strict KMI 校验通过”并不能自动等价于小米 vendor/vendor_dlkm 启动兼容。

随后建立隔离的 Xiaomi compatibility A，只改变 ACK 的 KMI trimming / protected-module policy：

- `kmi_enforced = False`
- `kmi_symbol_list_strict_mode = False`
- `trim_nonlisted_kmi = False`
- 移除 `kmi_symbol_list = "gki/aarch64/symbols/base"`
- 移除 `protected_module_names_list`
- 保留 `CONFIG_MODULE_SCMVERSION=y`

Run #7（Run ID `36511075743`，HEAD `17576f5465d55a17b9ec529e450b1a2bd0e3b79b`）完成编译、校验、AnyKernel3 打包，并由小米 17 Pro 真机刷入后正常启动。该兼容策略随后整理为正式实现并合入 `dev`；实验 workflow 和实验分支均已清理。

现在 ACK 的定位是**可启动的官方 R51 对照路径**。它仍保留 Kleaf/Bazel、R51 source-default LTO 和 Rust Binder 配置，但最终 KMI policy 是已经通过小米真机验证的兼容策略。
### 2026-09-29 Release 覆盖事故

首次 ACK 真机失败后，曾尝试从历史 `xiaomi-custom-latest` Release 下载“Gold #3”回刷，但该包同样无法启动。随后核查确认，这并不能证明原始 Gold #3 失效：旧发布逻辑让所有源码配置共用同一个可变 `xiaomi-custom-latest` tag 和同一个 ZIP 文件名，并使用 `gh release upload --clobber` 覆盖资产。

ACK 自定义构建 #6（Run ID `36408437569`）在 2026-09-28 10:44:58Z 明确以 `source_profile=ack-r51` 上传了同名 ZIP；GitHub Release 中当时的资产创建时间为 10:44:59Z，与该 ACK 运行完全吻合，而 Release 的 `target_commitish` 仍停留在早先 Gold #3 的 `6e612aad...`。因此从该 Release 下载时，页面看起来仍像 Gold #3，实际内容已经是 ACK-R51。

事故时被覆盖资产的 SHA256 为：

```text
b38ff5f9e3b2644b479a4532de5e98f2e2f16260dac6dd4b4dc548712403a928
```

已知能够真机启动的 Gold 自定义 Run #2（Run ID `36373339166`，Artifact ID `10950925575`）原始 AnyKernel3 ZIP 则为：

```text
ZIP   174a915d904ca1cda0f13d6bdf5ad78e45e1e76f67b6d013ee62eca550ca8776
Image 90540ed0f30e5f55a94c607b20bc765f6bd2337a4929413d702e2b597bc704c3
```

因此后续不得再把旧 `xiaomi-custom-latest` 作为来源证明或恢复包。正式发布逻辑已经改为：

- AnyKernel3 文件名包含 `source_profile`，可直接区分 `gold-cctv` 与 `ack-r51`；
- Release tag 按每次 Actions run 唯一生成，不再跨运行覆盖；
- “仅上传 AnyKernel3”模式也额外保存不可变 Workflow Artifact；
- 完整 Artifact 名称同样包含源码 profile 和 Run ID。

在没有取得原始 Gold #3 ZIP 本体并核对哈希之前，当前没有证据表明 Gold #3 内核本身存在启动回归。此前 Gold #3 已有一次实际成功启动记录。

## ACK-R51 构建与校验状态

ACK-R51 当前正式路径固定到：

- common：`5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- manifest：`a17736b7c5c2ce7435426183f1b376e85d59ba7e`
- Android 分支：`android16-6.12`
- 内核：`6.12.23`
- KMI：第 5 代
- 页面大小：4K
- Clang：`r536225`

构建链会先确认 ACK source target 仍是 stock strict policy，再应用 Xiaomi compatibility，并在最终 Image 中校验：

- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- `CONFIG_TRIM_UNUSED_KSYMS` 未启用
- `CONFIG_MODULE_SIG_PROTECT` 未启用
- 不存在有效的 unused-KSYM whitelist / protected-module list
- `CONFIG_MODULE_SCMVERSION=y`
- 内核 release 不含 Kleaf `-maybe-dirty` 占位符

ACK/Kleaf 另外保留两个已经验证必要的处理：

1. 对被 Xiaomi feature fragment 改成 built-in 的 ZRAM/ZSMALLOC/NETFS 项，调整 Kleaf 预期模块输出，避免仍要求不存在的 `.ko`。
2. 不强制 ThinLTO，保持 R51 的 `DEBUG_INFO_BTF + RUST + rust_binder` 配置成立。

最终版本字符串为：

```text
6.12.23-android16-5-4k
```

当前结论：ACK-R51 已同时完成全功能 CI 和 `pandora` 真机启动验证，但 Gold 仍拥有更丰富的运行时行为验证，因此 workflow 默认源码暂不切换。
## Root 与 SUSFS 版本追踪

2026-10-04 起，上游 ReSukiSU 已迁移并更名为 **BakaSU**，正式仓库为 `Baka-SU/BakaSU`。小米专用构建链使用新仓库名和新 Manager 名称；旧的 `resukisu` / `resukisu-susfs` 参数仅作为兼容别名继续接受，新产物统一使用 `bakasu` / `bakasu-susfs`。

正常自定义构建会跟随配置中的上游 ref 获取 BakaSU、SUSFS 以及 NoMount、DroidSpaces、NTSync patch、ZRAM patch、Baseband Guard、Re-Kernel 等移动依赖；每次构建都会记录最终解析到的精确提交，方便追踪和复现。

当前已经获得真机验证的基础版本：

- BakaSU：`fa8311f632a215b5381ec644627c6198d1e8a13e`，标签 `v4.2.0-rc3`，版本代码 `35184`（真机验证时项目仍名 ReSukiSU；该提交仍位于当前 BakaSU 仓库历史中）
- SUSFS `gki-android16-6.12`：`b213c54126fb243595ce7876e91d84d6e0861fec`，版本 `v2.3.0`
- AnyKernel3：`dca9dc370838d919d56c1f59ec78b27a14a72c68`

BakaSU 以内置方式编译，使用 `CONFIG_KSU=y`，不采用 LKM 模式。

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

Xiaomi17Series-pandora-Android16-6.12.23-resukisu-susfs-AnyKernel3.zip  （历史产物文件名，生成于更名前）
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
- 启用 BakaSU / SUSFS 时必须记录最终解析到的来源提交
- 用户请求开启的可选功能必须真实出现在最终配置中
- 不允许存在补丁拒绝文件

两套源码都要求最终 Image 通过同一组架构、版本、页面大小、BakaSU/SUSFS 和功能配置校验；ACK 另外校验“source strict / final Xiaomi-compatible”两阶段 KMI provenance。

PR CI 会先执行全部 Xiaomi shell 脚本的 `bash -n`，然后按改动范围选择回归：

- `baseline`：BakaSU + SUSFS 核心组合，额外可选功能关闭。
- `full`：启用当前支持的全部小米可选功能，但 KPM 除外。
- 共享核心或 ACK 相关脚本：Gold + ACK 双源码回归。
- Gold 专属构建/打包脚本：只跑 Gold。
- 功能集成或固定配置变化：Gold + ACK 双源码 Full。
- 文档、dispatcher、watchdog：只做 preflight，不浪费完整内核编译。

此前 #74 的十配置矩阵仍作为各个可选功能可以独立编译通过的历史证据。

## 缓存策略

小米 Gold 构建路径使用三层安全缓存：

- 固定 Gold common Git 对象仓库缓存
- 固定 `r536225` 工具链缓存（下载时校验 GitHub Release 发布资产 SHA256）
- ccache 编译对象缓存

common 源码缓存永远不会直接作为已经被修改过的工作树使用。每次构建都会从缓存对象重新创建干净 checkout，然后再应用 BakaSU、SUSFS 和各项可选功能。

内核 `out/` 目录故意不做缓存。

实际热缓存测试已经证明，在相同功能配置下，单次新增可缓存编译调用的 ccache 命中率可以达到约 99.9%，完整工作流耗时也会从冷缓存构建的大约二十多分钟显著下降。

### ACK-R51 缓存结论

ACK-R51 当前**故意不启用跨 GitHub Runner 的持久编译缓存**，正式构建保持已验证通过的 Kleaf `--config=fast` 路径，缓存仅限单次 runner 生命周期。2026-09-28/29 已实际验证以下方案均不适合作为正式 ACK 缓存：

- Bazel `--disk_cache`：热缓存可命中大量外围 action，但最耗时的 `KernelBuild` 仍完整执行，整体耗时几乎不变。
- Kleaf 持久 `--cache_dir`：能够恢复约 1 GiB 的旧 `OUT_DIR`，但 fresh runner 的源码重新同步后仍触发主内核重编，未得到有效加速。
- ACK ccache wrapper：将 wrapper 强行置于 Kleaf toolchain 前方会改变 R51 的编译器可用性判定，导致 `CONFIG_RUST`、`CONFIG_ASHMEM_RUST` 和 `CONFIG_ANDROID_BINDER_IPC_RUST` 被移除，破坏官方 R51 配置语义，因此明确弃用。

因此 ACK-R51 继续以**构建正确性、Rust Binder、Xiaomi KMI 兼容策略和可追溯性优先**；除非未来 Kleaf 官方提供适合临时 CI runner 的稳定缓存接口，否则不再为 ACK 强行注入跨 runner 编译缓存。此结论只适用于 `ack-r51 / kleaf-dist`，不会改变已经验证有效的 `gold-cctv` 缓存策略。

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

人工编译默认使用“仅上传 AnyKernel3.zip”模式时，可刷 ZIP 会发布到按 source profile + Run ID 唯一命名的 prerelease，同时保存一份不可变 Workflow Artifact；不同运行和不同源码不会再互相覆盖。

## BakaSU Manager

人工入口 **Xiaomi 17 系列 - 自定义内核** 在 Root 模式不为 `none` 时，会并行调用共享的 `get-manager.yml`：

- 自动识别当前 BakaSU 版本代码
- 查找与内核版本代码最匹配的 BakaSU Manager 构建
- BakaSU 模式只保留 ARM64 release APK
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

仓库保留 `xiaomi-sm8850-stable` 作为可移动恢复点，并保留永久 LKG `xiaomi-sm8850-lkg-20260928`。

如果 `dev` 被 Sync/Discard 等操作破坏，不要把 stable 直接 force push 到 `dev`。正确做法是从当前 `dev` 新建恢复分支，把 Xiaomi 专用路径从 stable 恢复到这个新分支，审核 diff 后再通过普通 PR 合回 `dev`。这样不会抹掉 `dev` 上同时存在的其它上游提交。

需要恢复的 Xiaomi-owned 路径为：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`
- `.github/workflows/kernel-xiaomi-sm8850.yml`
- `.github/workflows/xiaomi-sm8850-watchdog.yml`
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`
- `scripts/xiaomi-sm8850/`
- `docs/xiaomi-sm8850.md`

恢复完成后运行 Xiaomi PR CI，再进行必要的真机确认。不要使用 force push、`reset --hard` 或删除 stable/LKG 来“简化”恢复。

## 稳定分支与恢复层级

### 第一层：`dev`

日常开发、功能调整以及上游同步都发生在这里。

### 第二层：`xiaomi-sm8850-stable`

这是可移动的稳定恢复点。只有在 CI 正常、核心工作流完整，并且涉及内核行为的改动已经获得相应验证后才推进。stable 可以落后于 dev；它的职责是提供已知可恢复的 Xiaomi 文件集合，而不是追踪每一个开发提交。

### 第三层：`xiaomi-sm8850-lkg-20260928`

这是永久保留的最后已知可用里程碑，固定指向：

```text
a6739500cf10f9d73453d6eb4f86bf17c6e722a4
```

LKG 不随 `dev` 或 stable 更新。如果 stable 本身出现疑问，再使用 LKG 作为最后兜底。

## 自动看门狗

`.github/workflows/xiaomi-sm8850-watchdog.yml` 每天运行，并在 Xiaomi-owned 文件变化时立即检查：

- dev 上所有关键 workflow、配置、脚本和文档是否存在；
- 所有 Xiaomi shell 脚本是否通过 `bash -n`；
- dispatcher 是否仍调用本地 `kernel-xiaomi-sm8850.yml`；
- 是否重新出现废弃的 `xiaomi-sm8850-pandora` 跨分支依赖；
- `xiaomi-sm8850-stable` 是否存在并包含完整恢复文件；
- LKG 分支是否存在且仍指向固定 SHA。

看门狗不再尝试用“stable 直接向 dev 开 PR”的方式恢复，因为 stable 通常是 dev 的祖先，这种 PR 并不能还原后来被删除的文件。若检测到 dev 的 Xiaomi 内容损坏且 stable 完整，看门狗会生成一个 `xiaomi-sm8850-stable.patch` Recovery Artifact；该补丁表示“当前 dev → stable Xiaomi 文件集合”的差异，供人工审核后在恢复分支上应用。

看门狗本身只读仓库，不自动 merge、不 force push、不 reset、不删除分支。
## 维护原则

后续维护遵循以下原则：

- 用户日常只操作 `dev` 和 **Xiaomi 17 系列 - 自定义内核**。
- 不要求用户手动维护 stable 或 LKG。
- 内核功能修改优先在 `dev` 完成并经过 CI。
- 真机确认稳定后，再按需推进 `xiaomi-sm8850-stable`；stable 不要求与 dev 实时同步。
- 永久 LKG 不移动。
- 上游同步使用正常 merge/Sync fork，不使用强制覆盖。
- 小米专用逻辑继续限制在独立文件和目录中，避免污染上游通用 GKI 工作流。
