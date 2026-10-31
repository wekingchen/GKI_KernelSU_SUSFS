# 小米 17 Pro / HyperOS 4 全功能与端到端流程审计

审计日期：2026-11-01（北京时间）。审计对象：`wekingchen/GKI_KernelSU_SUSFS` 的 `dev` 分支，设备 `pandora`（SM8850）。本报告是 **OS4 当前事实与未完成事项的统一入口**；旧 OS3 文档不再是刷机依据。

## 一、结论与证据等级

| 类型 | 本次核对结论 |
|---|---|
| 已真实验证（历史） | OS4.0.5.0.XBLCNXM、6.12.69 的 Gen 3 LKG 经用户真机确认；其构建/严格复现/长期 Release 归档已在历史运行中完成 |
| 已实现且经过 GitHub 自动化检查 | OTA 工作流、OEM ABI 只读门禁、测试结果回报、开发指针、按当前 OTA 路由自定义构建、同次打包 IMG + 实验性 AnyKernel3、现有 R62 LKG 流程、上游隔离与 Python 合成回归 |
| 已修复、仍待真机端到端复查 | 新 OTA 的 Windows `collect-pandora-stock-input.cmd` 之前曾包含截断 PowerShell 与重复旧打包段；本次恢复完整模块采集并加静态门禁；**不能把 Linux CI 静态测试当成 Windows 真机采集成功** |
| 尚无真实新 OTA 测试样本 | 新 OTA 纯 GKI 候选编译→模块 CRC→`fastboot boot`→反馈→开发指针→新内核功能编译→IMG/AnyKernel3 这条完整路径尚未在另一个 HyperOS 新版本上端到端验证 |
| **未贯通** | **新 OTA 的功能版自动晋升 LKG、跨版本严格 LKG 复现和对应 Release 归档**。现有晋升/复现脚本依赖 R62 配置及其 ABI 锁，不可用它们晋升新 OTA；不能声称这条链已全自动闭环 |

**验证术语**：
- `NEW_OTA_CANDIDATE`：识别到新版输入，不等于可启动。
- `CRC_AND_VERMAGIC_MATCH_CANDIDATE`：采集的厂商模块导入符号 CRC/vermagic 静态通过，不等于 OEM 全面兼容。
- `HUMAN_ATTESTED_BASELINE_BOOTED`：用户报告纯 GKI 临时启动成功，CI 独立验证被测 IMG 来源、SHA256 与 fixture 字节重现；不属于 CI 远程硬件证明。
- `OTA_OS4_SELECTABLE_CUSTOM_UNVERIFIED`：新 OTA 功能版已成功编译并通过当前检查；**未代表 BakaSU/SUSFS/NoMount 等运行时功能正常**。
- `OTA_CUSTOM_UNVERIFIED` AnyKernel3：安装器可供人工选择，但会持久改写活动 boot，不能和“已验证 LKG 安装包”混同。

## 二、当前 OS4 工作流清单：职责、入口、状态

| 工作流 | 实际作用 | 用户需要手动做什么 |
|---|---|---|
| `xiaomi-sm8850-os4-ota-auto-candidate.yml` | 监听固定 Release 的 published/edited、每日补查或可手动触发；只读分析 ZIP；解析官方 GKI；编译候选；OEM CRC/KMI 全绿才生成临时待测 IMG | OTA 后更新固定 Release 的唯一 `*xm.zip`；正常不需另点运行，若立即处理可 Run workflow |
| `xiaomi-sm8850-os4-ota-test-feedback.yml` | 对通过/失败的临时启动提交人工结果；通过则校验 Run / SHA / ABI / 重现 fixture，自动 PR 固化三份开发记录；失败建立 Issue | **新 OTA 纯 GKI 基线通常只提交一次真实测试结果**；失败开不了机时不要求填写无法读取的实际 uname |
| `xiaomi-sm8850-os4-custom.yml` | 首先读取当前 stock-input；旧输入走 R62，新 OTA 已验证走新版本源码；各组件按本次上游快照构建；新 OTA 通过门禁后同次输出 IMG 与 UNVERIFIED AnyKernel3 | 选择功能并运行；拿到两个格式不需再次提交结果 |
| `xiaomi-sm8850-os4-promote-lkg.yml` | 用户明确确认后，把**当前 R62 自定义 Run** 的身份/ABI/产物晋升稳定 LKG | **目前仅 R62 路径支持**；新 OTA 不要输入其 Run ID |
| `xiaomi-sm8850-os4-lkg.yml` | 晋升成功后重建/校验当前稳定 LKG，并提供 boot 与 AnyKernel3 | 为目前 R62/Gen 3 布局服务；不是新 OTA 全版本复现器 |
| `xiaomi-sm8850-os4-archive-lkg-release.yml` | LKG 严格复现成功后归档长期 Release，也提供故障时手动补救入口 | 当前历史 Gen 3 已归档；新 OTA 不能直接依赖此旧版归档链 |
| `xiaomi-upstream-isolation-guard.yml` | 检查 Xiaomi 特有修改不能覆盖上游共享文件，执行 Python 回归、Shell 语法和 Windows 采集器静态完整性检查 | 不需要手动运行；PR 检查自动触发 |

不存在“必须每次功能编译后重新填写一次真机测试，才能获得 AnyKernel3”的要求。**纯 GKI 基线确认**、**功能版编译与打包**、**用户主动晋升稳定 LKG**是三种不同操作。

## 三、完整新 OTA 使用顺序（真实链路）

1. **保留恢复点**：先保留同系统、同 slot 可启动的 boot（以及 init_boot/vendor_boot/dtbo 等备份）。先正常 OTA 升级、正常启动并确认 Root 可用；读取分区及 OEM 模块需要 Root。
2. **Windows 只读采集**：从仓库下载最新版 `scripts/xiaomi-os4/collect-pandora-stock-input.cmd`；在 Windows 10/11 且 adb、tar、PowerShell 可用时执行。按当前活动 slot 读取 boot/init_boot/vendor_boot/dtbo；利用 `su` + `tar` **从手机输出只读字节流到电脑**，本地打包 OEM 模块、计数清单、README、SHA256SUMS。无成功模块采集不应上传 ZIP。
3. **替换固定输入**：在 Release tag `pandora-os4-stock-input` 中，删除旧 `*xm.zip`，只上传一个同 OTA 的新 `*xm.zip`，保存 Release。上传动作不能直接证明新 OTA 可用。
4. **自动候选**：OTA 主工作流检查 build/设备/slot/boot header/kernel marker/KMI；当前只支持 `6.12.x / android16-6` 且已验证工具链 `r536225`；换 KMI/编译器则停在人工适配。官方 GKI 源码可能只是同补丁版本候选，不能自称 Xiaomi 原厂源码。
5. **OEM 静态门禁**：从上传的原始 ZIP 解析 .ko、.ko.xz、.ko.zst、.ko.gz，核对 vermagic 和对 `vmlinux` 的导入符号 CRC；全绿才在 **同 OTA 的 stock boot** 上生成 `UNVERIFIED-FASTBOOT-BOOT-ONLY.img`。此时不生成新 OTA 的持久安装包，也不晋升 LKG。
6. **一次真实纯 GKI 临时启动**：在 PC 上仅运行 `fastboot boot <IMG文件名>`，验证设备、系统 build、`sys.boot_completed=1`、`uname -r`、关键 OEM 模块/网络、基本电话、Root 等实际行为。静态通过不能替代此步骤。不要 `fastboot flash` 候选；失败则回到已经备份的可用系统。
7. **提交结果**：在 `xiaomi-sm8850-os4-ota-test-feedback.yml` 选择 `dev`，填源 OTA Run ID、被测 IMG SHA256、pass/fail。pass 还要填写 Android 内实际 build/uname 并勾选启动和模块检查；fail 可留空无法获取的 build/uname、说明失败现象。GitHub 对 pass 独立重打包与 fixture 复现，不接受输入替换或来源漂移。
8. **开发指针自动切换**：成功时 GitHub PR 只提交该版本独立的 `fixture.json`、`verification.json` 和 `.github/config/ota-development-current.json` 指针，合并后**下一次自定义内核默认选择这个新 OTA**。此变更不触动 Gen 3 LKG。
9. **日常自定义编译**：仍运行现有 `小米17 Pro OS4 / 自定义内核`。BakaSU/SUSFS/NoMount/DroidSpaces/NTSync/BBG/Re-Kernel/网络增强等按菜单选择；每轮按定义的稳定渠道获取新上游快照。在该 OTA 的 GKI commit 上尝试补丁，检查 Kconfig、Module.symvers 核心 CRC 和内核 release。失败不会悄悄回退 R62。
10. **同次得到两个产物**：若本轮编译与静态门禁全绿，同一个 `pandora-OTA-CUSTOM-<build>-run-<id>` Artifact 同时提供 fastboot 临时 IMG 与标记 `OTA_CUSTOM_UNVERIFIED` 的 AnyKernel3 ZIP；两者使用同一个 Image，无需再次提交测试即可取得压缩包。建议仍先临时启动验证，再决定是否持久安装。
11. **稳定版晋升暂不支持新 OTA**：当前 R62 晋升工作流不会识别新 OTA 的 Artifact、ABI 锁/fixture，不能以新版本自定义 Run ID 走原晋升链。未来需要版本化 promotion、LKG 复现和归档适配及独立验证后才可开放。

### 固件未确认时的确定行为

| 输入/编译状态 | 预期行为 |
|---|---|
| 当前 `OS4.0.5.0.XBLCNXM`、无新 OTA 开发指针 | 原 R62 稳定构建路径；Gen 3 仍是当前 LKG |
| 上传新 OTA 但未通过纯 GKI 真机回报 | 自定义构建停止；**不得产出旧 R62 假冒新版本** |
| 新 OTA 已验证，但源码/补丁/工具链/ABI 不兼容 | 构建失败，保留真实报错；不能宣称成功 |
| 新 OTA 源码编译和静态门禁全通过 | 新版未验证 IMG + 未验证 AnyKernel3，一次提供 |
| 纯 GKI 临时启动失败 | 提交 fail；建立故障 Issue，不创建已验证 fixture/开发指针 |
| 将新 OTA 自定义 Run 输入旧 R62 LKG 晋升 | 不支持、必须拒绝；不可修改旧 Gen 3 身份 |

## 四、功能矩阵：源版本与检查边界

| 功能 | 自定义编译选择与上游策略 | 实际保护/限制 |
|---|---|---|
| BakaSU（Built-in） | 默认 `bakasu-susfs`，跟进 `Baka-SU/BakaSU` main；可选 BakaSU-only 或 none | 编译时需 `CONFIG_KSU` 符合所选模式；内置 Root 与旧 LKM 并存有冲突风险，打包器会尝试 `module_blacklist=kernelsu` |
| SUSFS | `gki-android16-6.12` 分支新提交；Core + 可选扩展（SPOOF/HIDE/OPEN_REDIRECT/SUS_MAP） | 补丁 dry-run、源文件完整性与 Kconfig 检查；新的补丁冲突应失败，不强行覆盖 |
| NoMount | 默认开启，取 NoMount 最新非 prerelease 发布 | VFS 内核注入，**不等于 Magic Mount**；模块/管理工具及实际功能仍需真机确认 |
| DroidSpaces | 默认完整支持，来源最新稳定 Release | 包含 namespace、Macvlan、IPv6 NAT 与 PIDs 方案；R62 定制的 SYSVIPC、cgroup KMI 改写对未来 6.12.x 不保证兼容 |
| NTSync | 用户可选，跟进补丁仓库 main | 需校验当前内核原生 NTSync 布局及兼容补丁，不盲套旧补丁 |
| Baseband Guard（BBG） | 取最新稳定 Release | 仅有 CONFIG 或已编译符号不代表 active LSM；需检查实际 LSM 列表及计数 |
| Re-Kernel | 取最新稳定 Release，Generic Netlink 路线 | 内置转换与 Android Binder 等兼容性需编译/真机验证 |
| 网络增强 | 选项包含 BBR、IPSet、FQ/FQ_CODEL/CAKE、WireGuard、CIFS 等 | 主要是当前 GKI 内核树的 Kconfig/组件，不是独立“最新版网络仓库” |
| CVE 审计回补 | 当前源码中审计 CVE-2026-43499 / 53163 修复链 | 仅当缺失且回补安全时处理，不应将“补丁检查过”当作通用安全认证 |
| BakaSU Manager | 单独 Job 读取同一轮解析的 BakaSU main 提交，从其成功 Manager Actions 产物取匹配版本 APK | 精确提交匹配检查；若上游官方 APK 尚未生成，会提示失败；内核构建成功不保证 Manager 同时取得 |

**最新稳定上游**是按来源定义的：BakaSU/SUSFS/NTSync 跟踪相应分支，NoMount/DroidSpaces/BBG/Re-Kernel 跟踪最新非预发行 Release；每次构建锁定本次 SHA，而非沿用 LKG 的旧提交。**LKG 复现**则必须使用已晋升的固定 SHA，不被上游更新扰动。

## 五、已核实的风险、缺陷及本次处理

| 优先级 | 项目 | 审计结论 |
|---|---|---|
| P0 已修复，待 Windows 实机复验 | Windows 采集器中 PowerShell 命令截断、双套 ZIP 打包逻辑冲突 | 修复为单套 root 只读 TAR 流采集 + OEM 数量/大小/完整文件清单 + SHA + 最终 ZIP；新增静态完整性回归 |
| P1 已修复 | 无法启动 Android 时，反馈表单却要求实际 uname/build | fail 允许空值，使用候选来源 build 登记 Issue；pass 仍要求真值 |
| P1 已修复 | 新 OTA 的 ccache 与 R62 共用缓存目录 | 新 OTA 缓存目录按官方 GKI commit 隔离；旧 R62 LKG 缓存不变 |
| P1 尚未实现 | 新 OTA 自定义功能包 → 新 LKG 晋升 → 复现 → 永久归档 | 旧版 workflow 写死 R62 Artifact、ABI、版本、LKG fixture；需新版本化升级方案 |
| P1 技术限制 | OEM vendor module 静态 CRC/vermagic / KMI | 只能验证采集到的模块、vmlinux 导出符号与特定版本；不能证明驱动运行、跨模块依赖、早期启动时序和设备树兼容 |
| P2 待新 OTA 验证 | R62 时代的 SYSVIPC/PIDs、Re-Kernel、SUSFS 等源码修改 | 新版本可能改变代码锚点/布局，编译门禁会阻断，但“自动解决兼容问题”尚不存在 |
| P2 文档已更新 | OTA 文档残留“只生成 IMG”“仅两份验证文件”“新版本无法自定义构建”等旧描述 | 统一为三份开发基线记录、新版自动路由与 IMG + 未验证 AnyKernel3 双产物 |
| P2 可用性边界 | AnyKernel3 安装器的安卓版本识别、Root/LKM 黑名单 | 需要在首次新 OTA 真机操作中核对管理器运行时 getprop/slot/设备检查；仅 CI 无法模拟 Recovery/安装器行为 |

## 六、旧 LKG 和回退：不得混淆

- 当前真实稳定 LKG（Gen 3）为 `pandora-os4-lkg-gen3`，绑定 **OS4.0.5.0.XBLCNXM**。当前 `.github/config/pandora-os4-full-parity-lkg.env` 与 `.github/config/pandora-os4-r62-tested-boot-v4-fixture.json` 不应被本审计更改。
- Gen 3 在原系统上作为恢复参考，**不可在新 OTA 上盲刷旧版本 boot**。回退必须以同一当前系统版本、同 slot 的已知可启动备份为准；恢复操作需谨慎识别当前分区。
- 历史 OS3/6.12.23/ACK-R51/Gold 调试记录在 `docs/xiaomi-sm8850.md` 保留作研究，但不是当前 OS4 编译/刷机指引。
- 本次没有真的从 Windows 手机采集新 OTA，也没有对另一个新内核进行完整功能编译、开机测试或 LKG 晋升。测试结论必须遵守这个边界。

## 七、下一次 OTA 的最小验收清单

- [ ] Windows 采集脚本实机运行成功，ZIP 包含四张分区镜像、README、SHA256、OEM 模块 ZIP 与计数清单。
- [ ] Release 中只有当前 OTA 的一个 `*xm.zip`；自动候选从官方记录锁定正确源码/工具链。
- [ ] OEM ABI 检查全绿并产出唯一待测 IMG；版本、Run ID、SHA 可核对。
- [ ] 人工 `fastboot boot`，设备为 `pandora`，实际 build/uname 匹配，Android/厂商模块/基本功能正常。
- [ ] 回报工作流通过，PR 合并且形成该版本 3 份开发记录；失败回报不创建 fixture。
- [ ] 直接运行原自定义工作流，输出 build 和 GKI commit 均为新 OTA；指定功能的补丁/配置/ABI 全部通过。
- [ ] 同次 Artifact 有 IMG 与未验证 AnyKernel3，ZIP 内 Image SHA 与编译 Image 一致。
- [ ] 用户用 IMG 单独测试本次功能版，再决定是否人工持久安装 ZIP。**无须第二次反馈才能拿到 ZIP**。
- [ ] 新 OTA LKG 晋升在新版版本化逻辑尚未实现前不得操作旧 R62 晋升工作流。

## 八、关联文档

- [新 OTA 采集与上报操作指南](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)
- [新 OTA 工作流、来源和安全门禁](xiaomi-17-pro-os4-ota-auto-baseline.md)
- [当前 R62 / Gen 3 LKG 功能及上游策略](xiaomi-17-pro-os4-full-parity-lkg.md)
- [Gen 3 长期恢复、严格复现与归档](xiaomi-17-pro-os4-lkg-release-archive.md)
- [OS3/6.12.23 历史研究资料（已过时）](xiaomi-sm8850.md)
