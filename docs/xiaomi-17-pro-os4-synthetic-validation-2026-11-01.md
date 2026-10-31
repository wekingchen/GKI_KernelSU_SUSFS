# 小米 17 Pro OS4｜全链路合成验证与仓库清理（2026-11-01）

> 适用仓库：`wekingchen/GKI_KernelSU_SUSFS`，`dev`。**这里的 Android boot、厂商 ELF .ko、GitHub Run ID、人工真机确认全部是合成测试数据；没有模拟出真实手机已开机的证据。** 正式 LKG 仍必须由设备拥有者实际验证并确认。

## 一、两层测试，不把单元测试误当集成测试

- 原有 62 项 Python 回归：OTA 基线 boot v4 字节重现、开发指针、ABI、AnyKernel3、Windows 收集器静态检查、工作流合约、跨 OTA LKG 记录、归档完整性。
- 新增 `test_os4_full_chain.py`（13 项）：生成符合关键结构的合成 `xm.zip`、Android boot v4、ARM64 ELF64 内核模块（包含 `.modinfo` 和 `__versions`），让**上一阶段脚本生成的文件**直接传给下一阶段真实生产脚本，而不是互不相关地硬编码每步结果。
- 新增 `test_os4_transaction_invariants.py`（12 项）：检查上传、真机回报、LKG 交易顺序、原始 Git SHA 重建、发布前整包 SHA 验证、三项人工确认、旧 R62/Gen3 保护、失败恢复不越权及不会执行手机分区写入。
- 合计 **87 项**。这些测试已纳入 `.github/workflows/xiaomi-upstream-isolation-guard.yml`，后续 Xiaomi PR 自动执行，不是一次性测试后删除。

## 二、合成端到端成功路径

`xm.zip`（四张活动分区镜像、README、OEM 模块 ZIP + 数量清单） → `inspect-ota-stock-input.py` 身份解析 → `check-ota-oem-abi.py` 解析真实格式合成 ARM64 ELF 的 vermagic / vmlinux CRC → `package-ota-testboot-v4.py` → `finalize-ota-baseline.py` → schema2 fixture / 用户验证记录 → `ota-development-pointer.py create/select/prepare` → `check-ota-feature-abi.py` → `check-ota-anykernel-evidence.py` → `repack-fastboot-boot-v4-from-fixture.py` → 实验性 ZIP Image 相同 → `cross-ota-lkg.py capture/verify/compare/promote` → `verify-ota-lkg-release.py` 完整资产集合与哈希。

成功路径下仍明确区分：

1. 纯 GKI 基线仅标记为人工报告；**合成测试中的“人工报告”只是模拟输入**；
2. 自定义 IMG 和 AnyKernel3 始终是功能版 `UNVERIFIED`，获得安装包不需要再次提交报告；
3. 只有人工确认稳定后才可主动执行正式晋升；
4. 新 OTA LKG 的原始用户确认包与 CI 重编包标识不同；
5. 缺少真实证书/可归一化 Image 规则的未来内核，**不会为测试通过而放宽严格复现门禁**。

## 三、已覆盖的负面/对抗场景

| 阶段 | 注入故障 | 预期结果 |
|---|---|---|
| OTA 输入 | README 内核版本与 boot 镜像 marker 不一致；新 OTA 尚未验证 | 拒绝选择开发基线 |
| OEM 模块 | .ko vermagic 错、CRC 错、模块 ZIP 缺失或计数不一致 | OEM 门禁 `BLOCKED`，不能进入安全待测 IMG 流程 |
| 纯 GKI fixture | 测试 IMG SHA 错、源码 Image 和 Module.symvers 被改、重打包不一致 | 禁止固化已验证记录 |
| 开发指针 | Release asset ID 变动、源码 GKI commit 变动、未验证新 OTA 尝试回退 R62 | 禁止构建或来源准备 |
| 自定义 | 基线 core CRC 漂移、功能版元数据或 Image 哈希不一致 | 不可标记为兼容 |
| 上游版本 | ref/tag、commit 或用户选项变更 | 禁止把不同构建冒充原 Run |
| LKG 复现 | final.config、Module.symvers 或归一化 Image 不一致 | 禁止晋升 |
| 代次 | 重复晋升同一 Run、Gen 序号/Release 标签错误 | 禁止替换稳定指针 |
| 归档 | SHA 不一致、关键源包/复现包缺失、附加未登记资产、Manager 证据缺失 | 不可公开合格 Release |
| GitHub 交易 | PR 合并前尝试公开稳定 Release，原始源码 SHA 被当前 dev 覆盖，旧 R62 与新 OTA 代次冲突 | 受静态交易次序和运行时身份门禁保护 |

## 四、明确没有被本次测试证明的事

- 未获取任何真实新 OTA：没有实际编译下一个新版本 GKI/应用全部功能补丁；无法证明将来的 Android toolchain、驱动和 OEM ABI 必然兼容。
- 未控制 Android 真机：没有验证实际 fastboot 临时启动、蓝牙/无线/蜂窝、Root、SUSFS、NoMount、DroidSpaces PIDs、BBG LSM、Re-Kernel/网络增强的运行结果。
- 未真的执行 LKG 晋升：为防模拟数据污染正式仓库，集成测试不会创建所谓 `ota-lkg-current.json`、Gen4 Release 或向 `dev` 伪造真机已验证标记。
- GitHub API 写权限、仓库保护规则、上游源码消失等外部状态不能仅由本地合成样本证明。运行时失败时停止而非静默略过。

**验收原则：测试覆盖可重复验证的生产脚本间协议和失败阻断，不对不存在的真实新 OTA 作“100%可开机”的保证。**

## 五、清理规则

- **保留**：与上游 `zzh20188/GKI_KernelSU_SUSFS` 对应的通用分支和工作流；当前 `dev`、LKG Release/配置、历史已验证成功运行、仍在进行的构建与 PR 核心检查。
- **清除**：已合并或被现行方案取代的单次 OS4 临时开发分支、临时清理工作流；不存在对应 YAML 的过时 Actions Run；不属于正式用户编译的分支上重复失败/中间门禁日志。
- 动作前重新读取 GitHub 最新状态并生成审计清单。只清理已完成、符合明确白名单规则的 Run，保留关键运行 ID；删除 Actions Run 无法恢复，且可能连带删除该 Run 的 Artifact，故不能清理任何有稳定包依赖的 Run。

## 六、2026-11-01 实际清理验收

本次清理工作流运行记录：[Run #41237464361](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41237464361)，实际结论 **success**。GitHub 清理前盘点为 **213** 条 Run；按不可逆删除白名单成功删除 **135** 条，最终再次通过 API 核实剩余 **78** 条（包括本次清理作业本身）。删除分类：

| 类别 | 删除 |
|---|---:|
| 合并开发分支上的重复中间隔离门禁 Run | 105 |
| 无效自定义工作流测试分支 push | 10 |
| 已废弃 OTA 反馈测试分支 push | 16 |
| 已删除 YAML 的临时/一次性维护 Run | 4 |
| **合计** | **135** |

- 删除了两个明确确认失效、SHA 未变化、无未关闭 PR 的 OS4 开发分支：`audit/os4-full-chain-synthetic-cleanup-20261101`（已合并 PR #41）和 `feat/os4-ota-device-test-verification-20261101`（已由正式 OTA 反馈流程取代）。
- 清理结束后删除了一次性维护 YAML；仓库当前有 **18** 个实际存在的 workflow 文件、**20** 个与上游分支体系一致的分支，未发现本轮产生的悬空开发分支。
- 明确保留 LKG Gen 3 Release：`pandora-os4-lkg-gen3`，公开状态、**11 个资产**；关键来源构建、严格复现、归档及 PR #36–#41 的成功检查 Run 仍存在。
- `.github/config/pandora-os4-full-parity-lkg.env` Git blob `44df3c9ed64271154c1d56ed7b7b62d8a18eb820`；R62 fixture Git blob `0886face66d64b2124527f6936d12cf961008976`，两者均与清理前相同。
- 没有创建 `ota-lkg-current.json`、任何虚构的新 OTA LKG 或新的 Gen 4 Release；没有手机/分区写入。

**注意：**删除 Actions Run 及其旧 Artifact 是不可逆的历史清理操作。本清理专门保留了正式稳定证据所引用的 Run，而不是对所有 78 条现存日志一概删除。
