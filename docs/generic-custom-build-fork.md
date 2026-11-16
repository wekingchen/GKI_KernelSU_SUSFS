# Android 内核构建-自定义：上游隔离修复版

当前适用的是上游通用自定义 GKI 工作流。**不是小米 17 Pro OS4 的 6.12.69 专用内核编译入口。** 小米 OS4 仍应通过 `xiaomi-sm8850-os4-custom.yml` 编译。

## 失败记录和判断

- 最初排查的失败（历史）：[`kernel-custom.yml` Run #40112987860](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/40112987860)，2026-10-25 北京时间，Android 12 / 5.10.209 / 2024-05 / BakaSU。宿主 Runner 在 LTO `vmlinux.o` 链接期间收到 shutdown signal，**没有编译器给出的致命链接错误可以直接归因**；这可能是 Runner 中断、资源压力或其它宿主事件，无法凭日志确认 OOM。
- 另一个已知问题：BBG `genheaders` 在 Android `build/build.sh` 提前收缩的 `PATH` 中用 clang-12 编译 host 工具时报 `Executable "ld" doesn't exist`，其后生成 `flask.h` 失败。
- 更早的 [Run #38128504763](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/38128504763) 是 BakaSU 与 SUSFS 的独立兼容性门禁拒绝：`susfs_compat.mk: Please wait susfs update`。最新 Run 已跨过该阻断点。**绝对不应删除兼容门禁或伪造 SUSFS 能力来换取“成功”。**

## 为什么不直接改原工作流

`.github/workflows/kernel-custom.yml` 与 `zzh20188/GKI_KernelSU_SUSFS` 上游 dev 的文件哈希完全相同；`.github/workflows/build.yml` 也属于上游共用路径。本项目上游隔离策略要求这两条路径随上游同步，因此不能直接在里面加入私有补丁。

本修复新增两条**本仓自有、非上游同名路径**的独立工作流：

- [`kernel-custom-fork.yml`](../.github/workflows/kernel-custom-fork.yml)：**Android 内核构建-自定义（本仓隔离修复版）**。原来的构建选项、自动版本解析、Manager 构建入口都保留，但调用本仓自己的 `build-fork-custom.yml`。
- [`build-fork-custom.yml`](../.github/workflows/build-fork-custom.yml)：由同一时间的原 `build.yml` 快照复制，只追加有限资源与 BBG host 工具修补。该副本由下文的每日自动同步与真实构建门禁维护；上游未更新时不重复编译，冲突时保留已验证版本。

## 改动及安全范围

| 补丁 | 具体行为 |
|---|---|
| 修复 BBG clang-12 找不到 `ld` | 在 **Runner 内下载的 Android 源码树** `build/build-tools/path/linux-x86` 中，仅当原本不存在可用 `ld` 时建立指向 `/usr/bin/ld` 的链接；不会写仓库跟上游同步的文件；已有有效 linker 原样保留，坏链接/缺 host ld 直接失败 |
| 降低资源峰值 | `JOBS=2`、`MAKEFLAGS=-j2 -l2`、`NINJAFLAGS=-j2`；磁盘空间允许时尝试添加 8GiB swap；Runner 不允许 swap 则给警告并用低并发继续 |
| 延长运行边界 | 整体 Job 由 60 分钟提高至 360 分钟；编译步骤单次限制由 30 提高至 120 分钟，最多两次超时重试 |
| 保持可刷内核特性 | 不关闭 SUSFS、BBG 或 LTO，不跳过 KMI/ABI、编译器、Image 的原有门禁，也不修改任何用户的设备 |

## 操作和验证

进入 [**Android 内核构建-自定义（本仓隔离修复版）**](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/kernel-custom-fork.yml)，在 `dev` 上按设备需要选择功能。历史验证组合为 5.10 / 2024-05 / BakaSU，Run 41239924766 已完成编译和产物上传，用户已确认红米 K50 Pro 刷入成功，无需重复最初失败排查。

`generic-custom-fork-guard.yml` 会持续检查 YAML、Shell、host linker 的缺失/坏链接/可执行权限，以及新旧 workflow 选择项一致性，并拒绝改动上游共用路径。它**不是真实完整内核编译**。

**关键边界：**10 月 25 日的 Runner shutdown 不是可复现的 kernel C 编译错误，资源修复能减少常见的内存/时间风险，但不能保证不会再次遭遇 GitHub 的基础设施中断；最终只能以新入口对应真实编译 Run `conclusion=success`、Image/ZIP 有效和上传成功为准。隔离版后续已由 Run 41239924766 完成真实编译，用户已确认红米 K50 Pro 真机刷入成功；该结果不能推及所有其它设备。

## 2026-11-16：原版 #112 / 隔离版 #4 回归排查

- [上游原版 #112](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43882343458)：BBG 宿主编译曾输出 `clang-12: error: Executable "ld" doesn't exist!`，但后续内核仍进入 `LTO vmlinux.o`，最终 GitHub 报 Runner 收到 shutdown signal。不能把它误诊为普通内核 C 编译错误。
- [隔离版 #4](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43885825971)：已通过依赖同步、补丁集成和 host ld 准备，进入 `编译内核` 后运行异常结束；GitHub Job 的日志端点当时返回 `BlobNotFound`，且步骤状态没有正常结束回执。因此没有足够日志证明是 OOM、LTO 代码报错或 GitHub 底层宿主故障。
- **对照**：[隔离版 #3](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43014413241) 在 2026-11-11 编译成功，最终配置真实包含 `CONFIG_LTO_CLANG_FULL=y`，并在编译前成功启用 8 GiB swap。这证明我们不能为通过新编译而擅自切换 Thin LTO / LTO_NONE。
- 对比 #3 与 #4 的隔离版主工作流，主要变化是增加 fork 专属 SUSFS 兼容处理，不能仅据此认定 LTO 或内核源码回归。

### 本仓限定的增强

1. `prepare-lto-resources.sh` 根据构建时实际剩余磁盘空间选择 0/8/12/16 GiB swap，保留内核编译目录空间；只有 `swapon` 成功才报告已启用。5.10 在 swap 正常时保持此前成功的 `JOBS=2`，无法启用时退到 `JOBS=1`。
2. `monitor-lto-build.sh` 在编译期间持续采集内存、交换空间和磁盘余量：优先读取 cgroup v2，其次 cgroup v1；两者均不可用时明确标记 `memory_source=host_proc_only`，以 `/proc/meminfo`、`/proc/vmstat` 提供**宿主级趋势信息（不是单个 Job 的 OOM 证据）**。结果同时写入 Job 日志和 `build-logs/resource-samples.log`。
3. 资源步骤和监控注入同时固化在 `sync_fork_build.py` 的可逆叠加规则中；后续自动跟进上游时不会丢失，更不修改任何上游原文件。
4. **验证范围**：单元测试和隔离门禁通过只代表脚本安全；内核编译、构建产物、真机启动仍需新的真实 Run 单独验收。Runner 若在编译中直接被强制销毁，Job 后续的 Artifact 上传仍可能无法运行，不能宣称完全解决底层宿主故障。

## 2026-11-17：#5 完整构建验收与收尾结论

- **CI 已验证成功：**[Android 内核构建-自定义（本仓隔离修复版）#5](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43904918314)，运行提交 `e0df6147da6a93b91fcd28eac1d055f057255cda`，三个 Job 全部成功；Android 12 / 5.10.209 / BakaSU 完成内核编译、链接、Image 及 AnyKernel3 上传，另有 BakaSU Manager 和 SUSFS 模块产物。
- **编译一致性：**日志真实显示 `CONFIG_LTO_CLANG_FULL=y`，进入并通过 `LTO vmlinux.o`；启用 16 GiB swap，`JOBS=2`，磁盘剩余充足。新增修复保留既有 LTO 模式，不依赖禁用 Root、SUSFS 或 BBG 来规避编译失败。
- **未宣称的验收：**#5 是**编译验证成功**，并没有 #5 对应的新真机刷入记录。仓库 `generic-custom-route.json` 中的 `validated_kernel_run_id=41239924766` 仍指向此前已通过红米 K50 Pro 真机验证的版本；不因 #5 的 CI 成功而覆盖。
- **监控兼容性：**#5 宿主未暴露预期的 cgroup v2 `memory.current` 等文件，旧版监控因此留下 `unknown`。收尾补丁改为识别 v1/v2 并在不可用时使用**标注来源的宿主级 /proc 数据**，不会把宿主内存信息冒充为 Job 内存峰值；该改动仅增强诊断，不触及 kernel/编译输入。
- **仍待仓库授权：**[上游自动同步 #23](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43904050708) 因缺少仓库 Secret `UPSTREAM_SYNC_PAT` 而失败。该权限只能由仓库拥有者安全配置；没有 Token 就不能保证后续无人值守同步成功，也不能把失败记为已修复。

## 自动跟进上游（首次必须授权，之后无人值守）

**2026-11-16 权限确认：**此前 [K50 Pro 自动同步 Run #43882595245](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/43882595245) 因 GitHub 默认令牌缺少 Workflows 写入权限，无法推送私有 `build-fork-custom.yml`。完整上游自动同步由 `upstream-exact-auto-sync.yml` 实现，本仓共享文件仍由逐字节门禁保护。

请先在本仓仓库 GitHub **Settings → Secrets and variables → Actions → New repository secret** 配置 **`UPSTREAM_SYNC_PAT`**。建议创建一个 **Fine-grained personal access token**，仅授权 `wekingchen/GKI_KernelSU_SUSFS`，权限要求：

- **Contents**：Read and write（创建和合并上游同步提交）
- **Workflows**：Read and write（修改私有 Actions 工作流文件）
- **Actions**：Read and write（调用 workflow_dispatch 并读取构建结果）
- **Pull requests**：Read and write（自动创建同步 PR）

使用最短合理有效期，并在到期前轮换；不要把 Token 粘贴到聊天、代码或 Action 日志。授权后分别从工作流页面手动运行一次验证。**未配置或授权不完整时自动同步会明确失败，不会修改已验证的 OS4 LKG 或已部署的内核。**



已新增 [`红米 K50 Pro / 上游 build.yml 无人值守同步`](../.github/workflows/generic-custom-auto-sync.yml)，在仓库默认分支 `dev` 上**每天自动检查一次**（UTC 03:17；北京时间 11:17），也支持手动检查，但完成首次授权后常规操作不需要人工启动。上游未变更时立即结束，不会浪费约 40 分钟重新编译。

具体机制：

1. 从 `zzh20188/GKI_KernelSU_SUSFS` 的 `dev` 抓取最新 `.github/workflows/build.yml`，与上次记录的**精确 Git blob SHA** 对比，获取上次原文件作为三方合并基线。
2. 从当前 `build-fork-custom.yml` **可逆还原**本仓之前的定制基线，对上游差异进行真正的三方合并，然后按固定规则重放 BBG host `ld`、JOBS、swap、超时等已验证补丁，不简单覆盖、不删除本仓既有定制。
3. 对生成版本执行 YAML、shell、补丁可逆性、上游隔离和恶意/冲突数据自动测试。遇到冲突、失去补丁锚点、版本来源不一致或安全门禁被移除，立即失败，**继续使用旧的稳定 `dev`**。
4. 只在候选临时分支发起与 [成功 Run #41239924766](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41239924766) **相同功能组合**的 Android 12 / 5.10.209 / BakaSU 完整内核构建（包括 SUSFS、BBG、NoMount、Re-Kernel、DroidSpaces、网络增强、CVE）。
5. GitHub 实际构建结果为 `success`，且目标构建 Job 与 AnyKernel3 Artifact 均成功后，再次验证 `dev` 和上游 SHA 未在运行期间变动。只有全部通过才把**生成的隔离版**与 SHA 元数据快速推进到 `dev`，不改上游共用 `build.yml`、`kernel-custom.yml` 或其它共享路径。
6. 任务结束自动核验并清理临时候选分支。失败只保留 GitHub Actions 日志与失败结果，以备追查；下一轮可自动重新尝试，无须你手动合并 PR。

**边界：**这套机制可以对安全可合并且能通过实际构建的上游更新实现无人值守自动跟进；**不能**安全地承诺无论上游怎样不兼容都自动修好并刷机。冲突、新版本编译失败、GitHub Runner 故障、GitHub 仓库策略阻止写入、或未来上游彻底改写工作流时，系统会拒绝发布有问题的版本，保留旧版稳定构建入口并输出失败原因。它永远不会自动把编译产物刷入红米 K50 Pro，真机长期可靠性仍需与编译成功区分。

版本来源与本仓私有基线的 Git blob SHA 记录在 `.github/config/generic-custom-upstream-sync.json`，同步脚本和回归测试在 `scripts/generic-custom/`，不会成为上游仓库的同名脚本。私有构建工作流更新后仍保留你现在使用的单独入口 `kernel-custom-fork.yml`。

## 上游恢复后自动停用隔离修复版（不再要求真机确认）

自 2026-11-01 的“原版恢复”改造起，每次自动检查首先比较 `zzh20188/GKI_KernelSU_SUSFS` 的**原版** `.github/workflows/kernel-custom.yml` 和 `.github/workflows/build.yml`，而不是仅查看隔离副本的 SHA。初始模式为 `fork`，来源状态保存在 `.github/config/generic-custom-route.json`。

- **来源未变：**不重复编译。当前模式为 `fork` 则沿用原隔离同步逻辑；已恢复 `upstream` 则不运行隔离补丁同步。
- **上游任一原版工作流变更：**先验证原版仍包含已用功能菜单和构建契约、不会强制使用未经 K50 Pro 真机验证的 Thin LTO。条件不满足直接跳过原版恢复，保留安全的旧版。
- **安全条件通过：**创建仅供测试的临时分支，把上述两份上游文件**原样**放入该分支，不改变正式 `dev`，用原始 `Android 内核构建-自定义` 和 [成功 Run #41239924766](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41239924766) 的全部功能配置执行实际编译。
- **原版 CI 成功：**同时检查构建 Run、Git 提交、5.10.209/BakaSU 内核 Job、AnyKernel3 Artifact、BBG 宿主头文件错误及 LTO 链接阶段证据，随后再次核对正式 `dev` 和上游文件 Git SHA 未发生变化。以上全部通过即可**自动恢复原版**：把原始 `build.yml` 和 `kernel-custom.yml` 与路由状态一同更新到正式 `dev`。不要求用户确认真机刷入，也不会自动给设备刷机。
- **原版验证失败：**不改正式分支，清理候选分支；继续尝试把可安全合并的上游变更同步到隔离版，并用其真实编译结果决定是否更新。
- **恢复后：**`mode=upstream`，私有 `build-fork-custom.yml` 的定时同步自动停用。每天的上游检查**仍保留**，后续新的上游变更仍需再通过原版完整 CI 才能更新 `dev`；隔离版及补丁文件保留为应急回退，不会自动删除。
- **严格限制：**原版恢复时覆盖正式 `dev` 上的共用 `build.yml`，但内容必须与刚刚通过 CI 的上游原文件逐字相同；这是有意恢复上游，并不是往共用路径添加私有补丁。由于其它通用设备工作流也可能使用该共用文件，无法保证它们都和 K50 Pro 一样可用；K50 Pro 的通过结果不能替代其它设备测试。

路由检测、真实构建调度和 SHA 门禁在 `scripts/generic-custom/try_native_upstream.sh`；配置安全策略在 `scripts/generic-custom/native_upstream_policy.py`；回归用例在 `scripts/generic-custom/test_native_upstream_policy.py`。

**当前状态（2026-11-02 核对仓库配置）**：`generic-custom-route.json` 记录 mode=fork、validated_kernel_run_id=41239924766，因此仍使用用户已真机确认的隔离版。是否恢复上游由自动检查及真实编译决定，不根据文档猜测最新上游状态，也不要求用户再次确认刷机才自动停用隔离版。
