# Android 内核构建-自定义：上游隔离修复版

当前适用的是上游通用自定义 GKI 工作流。**不是小米 17 Pro OS4 的 6.12.69 专用内核编译入口。** 小米 OS4 仍应通过 `xiaomi-sm8850-os4-custom.yml` 编译。

## 失败记录和判断

- 最近失败：[`kernel-custom.yml` Run #40112987860](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/40112987860)，2026-10-25 北京时间，Android 12 / 5.10.209 / 2024-05 / BakaSU。宿主 Runner 在 LTO `vmlinux.o` 链接期间收到 shutdown signal，**没有编译器给出的致命链接错误可以直接归因**；这可能是 Runner 中断、资源压力或其它宿主事件，无法凭日志确认 OOM。
- 另一个已知问题：BBG `genheaders` 在 Android `build/build.sh` 提前收缩的 `PATH` 中用 clang-12 编译 host 工具时报 `Executable "ld" doesn't exist`，其后生成 `flask.h` 失败。
- 更早的 [Run #38128504763](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/38128504763) 是 BakaSU 与 SUSFS 的独立兼容性门禁拒绝：`susfs_compat.mk: Please wait susfs update`。最新 Run 已跨过该阻断点。**绝对不应删除兼容门禁或伪造 SUSFS 能力来换取“成功”。**

## 为什么不直接改原工作流

`.github/workflows/kernel-custom.yml` 与 `zzh20188/GKI_KernelSU_SUSFS` 上游 dev 的文件哈希完全相同；`.github/workflows/build.yml` 也属于上游共用路径。本项目上游隔离策略要求这两条路径随上游同步，因此不能直接在里面加入私有补丁。

本修复新增两条**本仓自有、非上游同名路径**的独立工作流：

- [`kernel-custom-fork.yml`](../.github/workflows/kernel-custom-fork.yml)：**Android 内核构建-自定义（本仓隔离修复版）**。原来的构建选项、自动版本解析、Manager 构建入口都保留，但调用本仓自己的 `build-fork-custom.yml`。
- [`build-fork-custom.yml`](../.github/workflows/build-fork-custom.yml)：由同一时间的原 `build.yml` 快照复制，只追加有限资源与 BBG host 工具修补。未来上游大改时要逐项比较后重新同步，不应把这个隔离副本误当成能实时自动同步上游的文件。

## 改动及安全范围

| 补丁 | 具体行为 |
|---|---|
| 修复 BBG clang-12 找不到 `ld` | 在 **Runner 内下载的 Android 源码树** `build/build-tools/path/linux-x86` 中，仅当原本不存在可用 `ld` 时建立指向 `/usr/bin/ld` 的链接；不会写仓库跟上游同步的文件；已有有效 linker 原样保留，坏链接/缺 host ld 直接失败 |
| 降低资源峰值 | `JOBS=2`、`MAKEFLAGS=-j2 -l2`、`NINJAFLAGS=-j2`；磁盘空间允许时尝试添加 8GiB swap；Runner 不允许 swap 则给警告并用低并发继续 |
| 延长运行边界 | 整体 Job 由 60 分钟提高至 360 分钟；编译步骤单次限制由 30 提高至 120 分钟，最多两次超时重试 |
| 保持可刷内核特性 | 不关闭 SUSFS、BBG 或 LTO，不跳过 KMI/ABI、编译器、Image 的原有门禁，也不修改任何用户的设备 |

## 操作和验证

进入 [**Android 内核构建-自定义（本仓隔离修复版）**](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/kernel-custom-fork.yml)，在 `dev` 上使用与原失败 Run 相同的选项（5.10 / 2024-05 / BakaSU），对比能否完成 `LTO vmlinux.o`、产物打包和上传。

`generic-custom-fork-guard.yml` 会持续检查 YAML、Shell、host linker 的缺失/坏链接/可执行权限，以及新旧 workflow 选择项一致性，并拒绝改动上游共用路径。它**不是真实完整内核编译**。

**关键边界：**10 月 25 日的 Runner shutdown 不是可复现的 kernel C 编译错误，资源修复能减少常见的内存/时间风险，但不能保证不会再次遭遇 GitHub 的基础设施中断；最终只能以新入口对应真实编译 Run `conclusion=success`、Image/ZIP 有效和上传成功为准。在这之前，状态只能标为「已打补丁、尚未实编验证」。

## 自动跟进上游，不需要手工同步

已新增 [`红米 K50 Pro / 上游 build.yml 无人值守同步`](../.github/workflows/generic-custom-auto-sync.yml)，在仓库默认分支 `dev` 上**每天自动检查一次**（UTC 03:17；北京时间 11:17），也支持手动检查，但常规操作不需要人工启动。上游未变更时立即结束，不会浪费约 40 分钟重新编译。

具体机制：

1. 从 `zzh20188/GKI_KernelSU_SUSFS` 的 `dev` 抓取最新 `.github/workflows/build.yml`，与上次记录的**精确 Git blob SHA** 对比，获取上次原文件作为三方合并基线。
2. 从当前 `build-fork-custom.yml` **可逆还原**本仓之前的定制基线，对上游差异进行真正的三方合并，然后按固定规则重放 BBG host `ld`、JOBS、swap、超时等已验证补丁，不简单覆盖、不删除本仓既有定制。
3. 对生成版本执行 YAML、shell、补丁可逆性、上游隔离和恶意/冲突数据自动测试。遇到冲突、失去补丁锚点、版本来源不一致或安全门禁被移除，立即失败，**继续使用旧的稳定 `dev`**。
4. 只在候选临时分支发起与 [成功 Run #41239924766](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41239924766) **相同功能组合**的 Android 12 / 5.10.209 / BakaSU 完整内核构建（包括 SUSFS、BBG、NoMount、Re-Kernel、DroidSpaces、网络增强、CVE）。
5. GitHub 实际构建结果为 `success`，且目标构建 Job 与 AnyKernel3 Artifact 均成功后，再次验证 `dev` 和上游 SHA 未在运行期间变动。只有全部通过才把**生成的隔离版**与 SHA 元数据快速推进到 `dev`，不改上游共用 `build.yml`、`kernel-custom.yml` 或其它共享路径。
6. 任务结束自动核验并清理临时候选分支。失败只保留 GitHub Actions 日志与失败结果，以备追查；下一轮可自动重新尝试，无须你手动合并 PR。

**边界：**这套机制可以对安全可合并且能通过实际构建的上游更新实现无人值守自动跟进；**不能**安全地承诺无论上游怎样不兼容都自动修好并刷机。冲突、新版本编译失败、GitHub Runner 故障、GitHub 仓库策略阻止写入、或未来上游彻底改写工作流时，系统会拒绝发布有问题的版本，保留旧版稳定构建入口并输出失败原因。它永远不会自动把编译产物刷入红米 K50 Pro，真机长期可靠性仍需与编译成功区分。

版本来源与本仓私有基线的 Git blob SHA 记录在 `.github/config/generic-custom-upstream-sync.json`，同步脚本和回归测试在 `scripts/generic-custom/`，不会成为上游仓库的同名脚本。私有构建工作流更新后仍保留你现在使用的单独入口 `kernel-custom-fork.yml`。
