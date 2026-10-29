# 小米 17 Pro / pandora — 澎湃 OS 4（Android 17 / Linux 6.12.69）适配

> **状态：源码预检 / 尚未开始可刷机编译，绝不可把实验报告当作刷机包。**

## 已确定的设备事实（2026-10-29）

| 项目 | 原厂实际读取值 |
| --- | --- |
| 系统 | `OS4.0.5.0.XBLCNXM` |
| Android | 17 |
| 内核 | `6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k` |
| 平台 | 小米 17 Pro `pandora`，4K |
| Root | 现阶段 KernelSU LKM 正常；`su -c id` 返回 uid=0 |
| Cgroup PIDs | 原厂 `/proc/cgroups` 不包含 pids；暂不作为新内核主线阻断项 |

6.12.69 是新的目标，KMI 从 `android16-5` 变成 `android16-6`。虽然 Android 平台是 17，Google 仍支持 `android16-6.12` GKI 系列，**不应误改为 `android17-6.18`**。

## 旧版基线保持不变

- `dev` 及 `xiaomi-sm8850-stable`、`xiaomi-sm8850-lkg-20260928` 中的 Android 16 / Gold 6.12.23 实现与恢复分支暂时不更改、不重命名、不发布到 OS4。
- OS3 实刷成功的 Gold #23 和 Macvlan-only 仍是历史证据，但不能在 OS4 上刷回。PR #13 的 PIDs 禁用门禁仅是针对旧基线的安全保护。
- 新 OS4 的源码、构建缓存、配置检查、AnyKernel3 包的版本门禁、功能补丁和启动验证需要独立开展；不能把 `6.12.23` 替换成 `6.12.69` 就开始打包。

## 新内核源候选（未证明匹配小米 stock）

- Google 正式发布家族：`android16-6.12-2026-03`（Linux 6.12.69）。
- 第一轮审计候选标签：`android16-6.12-2026-03_r62`，common commit `e2b8ca7c8d0551a6124b1a7322f5ae532845f1b5`。参考：https://android.googlesource.com/kernel/common/+/refs/tags/android16-6.12-2026-03_r62
- 这不是用户 stock 内核标识 `g43b5ab7e247d`。**源码版本相同不代表具有相同 vendor ABI 或行为。**
- 上述候选仅用于发现源码、KMI、编译器、SUSFS/DroidSpaces 补丁兼容性。它不享有旧 Gold 真机通过的结论。

### 独立的首轮预检

`.github/workflows/xiaomi-sm8850-os4-preflight.yml` 仅在隔离分支 `os4/pandora-6.12.69-adaptation-20261029` 内指定文件有变化时运行；不调用原有编译脚本，不生成 Image，不打包 AnyKernel3，也不写入 dev。

预检做四件事：
1. 拉取官方 R62 标签，验证解析到的 commit 与预置 SHA、Makefile 的 Linux 版本、`build.config.constants` 的 GKI 分支/KMI/Clang。
2. 检查官方源码是否含小米 KMI symbol list 与用于兼容的关键 Kconfig；缺少时输出报告，不假定可移植。
3. 对 SUSFS `gki-android16-6.12` 与 DroidSpaces 6.12 kABI 补丁做**不改变源码的 dry-run**，记录需要移植的冲突；dry-run 通过也不等于功能可用。
4. 上传报告供后续构建链选择使用。预检成功仅证明静态源码验收，不能标为可开机。

## 迁移实施顺序

1. **源码确认**：取得正确 GKI tag/commit、KMI generation、Clang 和对应 manifest/Bazel 构建依赖。
2. **最小基线**：先做无 BakaSU、无 SUSFS、无附加特性的纯净 6.12.69 Image；配置/符号/模块版本、CRC 与原厂 `boot.img` 对照。
3. **ABI 审核**：特别覆盖厂商 `vendor_dlkm`、`system_dlkm` 的预编译模块与导出符号，不能只看单一 `Module.symvers`。
4. **分层叠加**：BakaSU Built-in → SUSFS → NoMount → DroidSpaces/Macvlan → 其它勾选特性；每层都做 CI、启动和运行时验收。
5. **独立可刷包**：仅在获得此 **精确 OS4 版本**的原厂 `boot.img`、恢复方式和合适的模块兼容证据后，才恢复直出 AnyKernel3.zip，包内严格限制 Android 17 / 6.12.69 / pandora；不可复用旧 ZIP。
6. **真机验收**：除开机和 Root 外，重点检查移动数据、VoLTE/IMS/双卡、摄像头、指纹、Wi-Fi、蓝牙、待机。CI 绿不代表可刷。

## 社区已知风险

小米 17 `pudding` 的 OS4 6.12.69 R62 研究项目已实现可开机的实验内核，但公开测试也记录蜂窝数据、IMS 和通话失败：https://github.com/2824799/droidspaces-xiaomi-17-kernel/blob/main/docs/README.md 。这不是 `pandora` 已故障的证据，却足以要求本项目把**蜂窝/通话**列为必须验证项。

### 当前不做

- 不调整现有 OS3 的默认值、Gold 缓存和可刷工作流；
- 不把 PIDs Controller 的问题作为 OS4 移植的前置障碍；
- 不向用户推荐刷 OS3 的 AnyKernel3；
- 不从字符串 `g43b5ab7e247d` 推断已找到小米内部完整源码，或用改 `uname -r` 冒充原厂兼容。

## 首轮 Actions 源码预检结果（2026-10-29）

[Run #1 / ID 40829503036](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/40829503036) 通过。实际下载的审查 Artifact 为 `xiaomi-pandora-os4-6.12.69-source-audit`（ID `12877933057`），记录如下：

| 检查点 | 实际结果 |
| --- | --- |
| 官方 `android16-6.12-2026-03_r62` tag 对应提交 | `e2b8ca7c8d0551a6124b1a7322f5ae532845f1b5`，PASS |
| Makefile | `6.12.69`，PASS |
| build.config.constants / GKI 分支 | `android16-6.12`，PASS |
| KMI generation | `6`，PASS |
| Clang | `r536225`，PASS |
| `gki/aarch64/symbols/xiaomi` | 存在 |
| 当前 SUSFS `gki-android16-6.12` | `519c86c5d8ad3832ff4a2e1a81dc1b81076f1693`，上游完整补丁 **未通过** dry-run |
| DroidSpaces `kernel-6.12` kABI 补丁 | `4344dc5fc4ab981f1cf2df54c93bf32a6ebbdc85`，dry-run **PASS** |

SUSFS 失败位置：`fs/proc/task_mmu.c` 第 5、6 个 hunk，与 R62 源码上下文不一致；其余部分存在位置偏移。必须做**源码层专门适配并重新进行全量 dry-run/编译**，不能忽略这两个 hunk、强制 `patch --force`、也不能用旧 6.12.23 的兼容结果代替。预检的补丁 dry-run 本身不会写入源码，因此不会掩盖失败。

**注意：** `DroidSpaces kABI` 补丁 dry-run 通过只表示可以应用，后续的配置、符号 ABI、模块加载和运行时尚未验证。BakaSU/NoMount 的 6.12.69 兼容也尚未得到验证。上述 Run #1 **没有生成 Image 或刷机 ZIP**，对 OS4 内核可启动性没有证明作用。
