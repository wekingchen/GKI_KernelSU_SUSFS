# Xiaomi 17 Pro OS4 当前 LKG 与动态上游策略

本文记录 Xiaomi 17 Pro OS4 的当前稳定 LKG、日常自定义编译上游策略，以及 **现有 R62 范围内的** LKG 晋升/复现机制。完整功能和新 OTA 的已完成/待实现边界见 [2026-11-01 OS4 端到端审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。

核心原则：

- **自定义编译追最新稳定上游**：每次 run 开始时重新解析各功能的稳定渠道，并把本次解析结果锁成精确 SHA；
- **LKG 是用户显式标记的当前稳定版本**：会在受支持的版本化晋升链完成真机确认与严格校验后移动，不能把新 OTA 的开发指针当作 LKG；
- **旧 LKG 自动归档**：新 LKG 晋升时，旧机器可读状态写入 `.github/config/lkg-history/`；
- **LKG 只负责稳定复现/回退，不阻止新版构建**：候选版本与 LKG 不同会标记为 `CUSTOM-UNVERIFIED`，但只要安全门禁通过就继续编译并输出 AnyKernel3。

## 当前适用范围

- 设备：Xiaomi 17 Pro
- 代号：`pandora`
- 系统：HyperOS 4 `OS4.0.5.0.XBLCNXM`
- GKI：Android 16 KMI / 6.12.69
- 当前 Gen 3 内核：`6.12.69-android16-6-os4r62-custom-4k`
- 最初真机验证的 Gen 1 基线内核：`6.12.69-android16-6-os4r62-dspids-dscore-full-parity-kmi-4k`

不要把本结论外推到其他机型、其他 HyperOS 版本或 OTA 后的新 boot 布局。

## 当前 LKG 身份（唯一权威来源）

**当前 LKG 以仓库 `dev` 中的机器可读配置为准，不以本文的历史示例为准：**

```text
.github/config/pandora-os4-full-parity-lkg.env
```

最近一次已完成的晋升为 **Gen 3**（2026-10-31，来源自定义编译 Run `41210530544`，用户确认真机稳定后自动合并 PR #25）。
Gen 2 已归档至：

```text
.github/config/lkg-history/pandora-os4-r62-gen-2-run-41206357785.env
```

更早的 Gen 1 Full Parity 基线来源 Run `41068829461`，其已验证 AnyKernel3 打包来源 Run `41072834543`。这两个 Run **不是当前 Gen 3 LKG**；仅用于历史回溯。

`LKG_PACKAGE_NAME` 如果仍包含 `UNVERIFIED`，表示该 Artifact **在首次构建时尚未经真机确认**，是来源产物的原始文件名。成功晋升后须以当前 `LKG_PROMOTION_GENERATION` 和用户的真机确认作为稳定身份；不能因为文件名推断晋升失败。

## 已验证功能（Full Parity 真机基线）

以下运行时证据来自先前已完成的 Full Parity 真机检查；后续 Gen 3 是经用户独立真机验证并晋升的版本。配置字段或功能勾选本身**不能替代**逐项运行时验证。

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

当前 LKG 已验证版本：

```text
Re-Kernel version: 11.7
Generic Netlink family: rekernel
```

旧 legacy netlink 保持关闭。

## 当前 LKG 复现与晋升

当前 LKG 的严格复现入口：

```text
.github/workflows/xiaomi-sm8850-os4-lkg.yml
小米17 Pro OS4 / 当前 LKG 复现与打包
```

它不会解析最新上游，而是读取：

```text
.github/config/pandora-os4-full-parity-lkg.env
```

里面记录的：

- 功能选择；
- 每个外接组件的 ref 类型、ref 名称与精确 commit；
- kernel release；
- final.config / Module.symvers；
- Image normalization 元数据；
- boot fixture / ABI lock；
- 来源 run / AnyKernel3 / fastboot boot 哈希。

该工作流按**当前 R62 体系**在晋升时锁定的身份重新编译，并对配置、ABI/KMI 与归一化 Image 做严格比较。后续 **R62 范围内**若再次晋升，晋升成功后 GitHub 的 workflow_run 会尝试自动接力复现、归档。**这套历史 R62 工作流仍不通用于新 OTA**。新 OTA 已另行实现[版本化 LKG 单次交易入口](xiaomi-17-pro-os4-cross-ota-lkg.md)，独立按原始 Run 重建、校验、归档与晋升；代码已测试，真实新 OTA 尚待验证。外部源码或工具链失去可访问性时，精确 SHA 也不能单独保证未来永久可复现。

当某次正式自定义构建经过真机启动、持久化使用并由用户确认稳定后，使用：

```text
.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml
小米17 Pro OS4 / 将自定义构建晋升为 LKG
```

**统一晋升入口支持 R62 与已验证新 OTA 的正式 `dev` 自定义 Run ID**。GitHub 根据唯一的未过期 Artifact 自动路由：`pandora-OS4-R62-CUSTOM-run-<id>` 走历史 R62 ABI 锁和自动复现接力，`pandora-OTA-CUSTOM-<build>-run-<id>` 走新 OTA 版本化严格复现和归档链；两者都必须经过三项真实稳定确认。对 R62 Run，原有晋升流程会：

1. 下载并重新校验该 run 的 Image / config / Module.symvers / fastboot boot / AnyKernel3；
2. 重新执行 ABI/KMI 固定锁；
3. 把旧 LKG 自动归档至 `.github/config/lkg-history/`；
4. 生成下一代当前 LKG 文件；
5. 创建 PR 之前**强制执行上游隔离预检**（包括未提交的 LKG 文件和历史快照）；
6. 提交 LKG 配置到专用分支，再次对**已提交的准确差异**执行上游隔离门禁；仅允许当前 LKG 指针与一份旧 LKG 历史快照；
7. 自动创建非草稿 PR，并核对 PR head/base、服务器侧变更文件清单、当前 `dev` 的基线 SHA、GitHub 可合并状态；
8. 上述所有校验成功才由 GitHub 自动 squash 合并到 `dev`，更新当前 LKG，并清理临时分支。若任何检查失败或分支保护禁止合并，则停止并保留 PR 供排查，**不会擅自更新当前 LKG**。
9. 本次晋升 Run ID 与新的 `LKG_PROMOTION_RUN_ID` 一起保存；**晋升 Workflow 确认成功结束后**，GitHub `workflow_run` 自动启动严格 LKG 复现。复现仅接受当前 LKG 的同一晋升 Run ID，拒绝过期触发、跳过用户确认的晋升和跨代复现。
10. 严格复现成功结束后，再由 GitHub `workflow_run` 自动执行长期 Release 归档；强制核对原始真机版本、BakaSU Manager、复现 Image、SHA256 与锁定组件快照，上传后从 Release 下载回检，完成才发布。任何阶段失败会阻断后续自动步骤，但已晋升的 LKG 不会被自动回滚。

**不需要人工合并 LKG 晋升 PR**。机器人创建 PR 时 GitHub 可能要求人工批准其独立 CI；因此晋升所需的校验全部在本工作流内完成，不依赖该异步 CI。独立隔离 Workflow 仍用于 `os4-*`、`xiaomi-*`、`pandora-*` 开发分支及开发 PR；仅包含 LKG 指针和历史快照变更的 PR 不触发它。

**历史说明：**Gen 3 的严格复现 Run `41213989920` 与 Release `pandora-os4-lkg-gen3` 已在旧流程下实际验证成功。新自动接力的端到端成功需要未来真正受支持的晋升 Run 另行证明；当前不能把新 OTA 的开发指针或编译成功当成 Gen 4 稳定晋升。

因此 LKG 是“**用户确认后移动的稳定指针**”，而不是永久停在某个历史 SHA。

## Gen 3 当前 LKG 复现：已验证通过

截至 2026-10-31，**Gen 3 首次真实复现构建已成功**：

| 项目 | 记录 |
|---|---|
| 复现工作流 | `小米17 Pro OS4 / 当前 LKG 复现与打包` |
| 运行 | [Run #41213989920](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41213989920)（#1，成功） |
| 运行来源 | `dev` / `d9cb8b16b8cd1836c42eaa50d1d286224281e4bc` |
| 当前 LKG 代次 | `LKG_PROMOTION_GENERATION=3` |
| 原始真机验证来源 | `LKG_SOURCE_RUN_ID=41210530544` |
| 内核标识 | `6.12.69-android16-6-os4r62-custom-4k` |
| Artifact | `pandora-OS4.0.5.0-R62-CURRENT-LKG` |
| Artifact ID | `13047254063` |
| Artifact 保留期 | 至 2026-11-30 15:22 UTC（以 GitHub 实时状态为准） |

该次实际执行并通过了 **当前 LKG 身份、固定 boot fixture / ABI lock、`Module.symvers`、`final.config`、kernel release、归一化 Image、fastboot boot、AnyKernel3 打包及 Artifact 上传** 各步骤。工作流中的 `EXACT_LKG_SELECTION=1` 检查为强制通过条件。

**验证边界：** 此次已证实仓库锁定的 Gen 3 可重新构建并通过归一化哈希校验；构建成功不等于已证明重新生成的 Image 逐字节相同，也不等于将新生成的 boot 再次刷入真机验证。无需仅为离线复现测试再次刷机或晋升。

Artifact 会到期；长期恢复能力应依靠可重建的固定源码 SHA、工具链和 fixture，以及本机已知可启动的备份，不能只依赖临时 Artifact。未来 OTA 或系统版本改变时须重建适配基线。

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

### 动态稳定上游快照

每次正式自定义 workflow 启动时，先运行统一 resolver：

```text
scripts/xiaomi-os4/resolve-stable-upstreams.sh
```

当前策略：

| 组件 | 自定义编译的稳定来源 |
|---|---|
| BakaSU | `main` 当前 HEAD（按用户明确要求） |
| SUSFS | `gki-android16-6.12` 稳定分支 HEAD |
| NoMount | GitHub 最新正式 Release（排除 draft/prerelease） |
| DroidSpaces | GitHub 最新正式 Release（排除 draft/prerelease） |
| NTSync patch | `Goldzxcbug/Droidspaces_Kernel_patch:main` HEAD |
| Baseband Guard | GitHub 最新正式 Release |
| Re-Kernel | GitHub 最新正式 Release |

resolver 在 run 开始时只解析一次，并输出本次稳定快照 SHA256。内核、BakaSU Manager、ccache key、Artifact 元数据都使用同一份快照；构建过程中上游再更新也不会造成“半新半旧”。

如果任一启用组件的本次 SHA 与当前 LKG 不同：

- **不会回退到 LKG 旧版本**；
- 仍直接使用最新稳定版继续适配和编译；
- ABI/KMI、patch、Kconfig 等安全门禁继续执行；
- 成功后生成 fastboot 测试镜像与 `CUSTOM-UNVERIFIED` AnyKernel3；
- **对 R62 版本**，真机稳定后可以用现有晋升工作流；**对新 OTA 版本**，只能先作为自定义待测版使用，暂不可直接走旧 R62 LKG 晋升工作流。

只有“功能选择 + 启用组件精确 SHA”都与当前 LKG 相同，构建结果才具有当前 LKG 身份。

网络增强（BBR / IPSet / FQ / FQ_CODEL / CAKE / WireGuard / CIFS）来自**本次选中的 GKI 内核源码**本身（R62 或经过验证的新 OTA GKI），没有独立第三方版本 resolver；CVE 修复链按当前源码审计/必要时回补，不作为普通第三方版本号处理。跨新 OTA 的补丁、Kconfig 与 OEM ABI 不保证自动适配。

### BakaSU Manager 与上游跟进

OS4 正式自定义工作流恢复旧 OS3 的上游跟随方式，并进一步保证同一次构建的内核与 Manager 来源一致：

- 每次 workflow 启动时先解析 `Baka-SU/BakaSU:main` 当前最新 SHA，并把这个 SHA 锁定为本次 run 的统一 BakaSU 来源；
- `bakasu` / `bakasu-susfs` 共用本次解析的精确 BakaSU SHA；`none` 不获取管理器。

### BakaSU Manager

BakaSU 是动态上游快照的一部分。每次 run 解析 `Baka-SU/BakaSU:main` 当前 SHA 后：

- 内核使用该 SHA；
- Manager 只接受 BakaSU 官方 `build-manager.yml` 中 **head SHA 完全相同** 的成功构建；
- Manager `KSU_VERSION` 必须与本次内核目标 KSU 版本完全一致；
- 普通 Manager 与 Spoofed Manager 分别保留；
- 如果官方 Manager CI 尚未完成，会等待同 SHA 产物，不回退旧 APK；
- `root_mode=none` 时自动跳过 Manager。

BakaSU 的 Kbuild 会把整个仓库 HEAD 的 commit count / SHA 写入内核版本身份，因此即使某次更新只动 userspace，只要 BakaSU SHA 前进，也视为新候选内核，直到该 revision 被用户真机验证并晋升为 LKG。

### 暂未加入菜单

ZRAM / LZ4K / LZ4KD 仍属于待适配功能，在完成 OS4 模块形态、ABI 和真机验证之前，不提供无效或未经验证的编译开关。

---

## 新固件 / OTA

OTA 后不要直接沿用当前 LKG。先用新版 `collect-pandora-stock-input.cmd` 只读采集新系统和 OEM 模块，再把新的 `*-xm.zip` 上传到固定的 stock-input Release。

现行 OTA 主工作流：

```text
.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml
```

它会自动检查新固件、构建候选 GKI、静态对比 OEM 模块 ABI/KMI；仅在检查允许时输出**供 fastboot boot 临时测试、尚未认证的候选 IMG**。随后通过一次纯 GKI 真机结果反馈，GitHub 才会固化该版本的 fixture/verification 和开发指针；以后仍在原「自定义内核」入口自动选新 OTA，成功编译就同次输出待测 IMG 与 `OTA_CUSTOM_UNVERIFIED` AnyKernel3（无需第二次反馈才能取得 ZIP）。**这是开发基线的切换，不是新 OTA 稳定 LKG 晋升。** 旧的独立 stock-intake Workflow 已删除。

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

## 跨 OTA LKG（2026-11-01 新实现，待新版本真实验收）

新 OTA 与 R62 共用一个 `xiaomi-sm8850-os4-promote-lkg.yml` 人工入口，内部按 Run 的真实产物自动分流。当你已经真机稳定使用某次新 OTA 自定义功能内核后，在 [将自定义构建晋升为 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) 输入该自定义 Run ID，确认已启动、已持久稳定使用和已选功能正常。GitHub 会按这个 Run **实际使用的仓库提交、GKI commit、所有功能 ref/commit、配置和同 OTA fixture** 重编，严格核对 `final.config`、`Module.symvers` 和已知非确定区域归一化 Image，原始/复现双产物长期归档 Release 并下载验算，然后才合并版本化 LKG 指针 `.github/config/ota-lkg-current.json` 与公开 Release。

以 Gen 3 为历史基线，首个新 OTA LKG 从 Gen 4 开始；以后同一入口依次晋升 Gen 5……不会再通过旧 R62 工作流生成冲突代次。这个方案**已实现并做离线模拟门禁，但没有真实新 OTA 可进行跨版本构建、真机和完整晋升验收**。见 [完整设计及草稿 Release 故障修复](xiaomi-17-pro-os4-cross-ota-lkg.md)。
