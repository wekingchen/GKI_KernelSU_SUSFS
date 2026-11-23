# 本仓库工作流怎么用（2026-11-23）

> 先说结论：**日常主要点两个按钮——「小米 17 Pro OS4 / 自定义内核」和「晋升真机稳定内核为 LKG」**。新系统升级先用手机上的 OTA 助手；其他大多数流程由 GitHub 自动运行，平时不用手动点。当前稳定版是 **OS4.0.6.0.XBLCNXM / Gen7**。

这里列的是本仓库自己新增的工作流。上游 `zzh20188/GKI_KernelSU_SUSFS` 原有工作流保持原样，以便持续同步；别因为它们名字相近就删掉。

## 你平时需要用的入口

| 什么情况 | 用哪个入口 | 做完会怎样 |
| --- | --- | --- |
| 系统没升级，只想换 Root/SUSFS/NoMount 等功能 | [自定义内核](../.github/workflows/xiaomi-sm8850-os4-custom.yml) | 编出可供验证的新包；**成功编译不等于已验证可刷** |
| 已经在手机上测试并长期使用某一次自定义构建，功能都正常 | [晋升为稳定版 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) | 填原构建 Run ID，勾选启动、持久安装、功能正常三项；后台严格复现并归档 |
| 手机系统真正更新了 | 手机上打开 **OTA 助手**（[使用说明](../tools/pandora-ota-companion/README.md)） | 保留原版 `init_boot.img` → 同版本取得 Root → 只读采集上传；后续工作流自动接棒 |
| 自动处理停在 OEM ABI 阻断 | 在 OTA 助手的状态卡点**「查看补采建议」** | 按页面提示做有限的只读补采，人工预览确认后上传；**不会自动解除阻断** |
| 自动接入、候选或归档异常 | 先看 [故障恢复说明](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md) | 核对来源和 SHA，再决定是否手动触发恢复 |

## OTA 助手背后自动运行的流程（通常不用点）

| 工作流 | 它负责什么 |
| --- | --- |
| [手机 OTA 安全接收入库](../.github/workflows/pandora-os4-ota-mobile-intake.yml) | 收到 App 上传通知后，核验手机 ZIP 的文件身份和 SHA，安全接收；不把 Root 后的活动镜像说成原厂未修改文件 |
| [OTA 自动候选](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml) | 新输入入库后构建 GKI 候选，做 OEM ABI 检查；不通过就阻断，绝不自动刷机 |
| [OTA 真机测试反馈](../.github/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml) | App 里人工确认后调用，验证 Run/镜像 SHA 和启动信息，保存可复现的开发基线；不是晋升 LKG |
| [OTA 诊断补采审核](../.github/workflows/pandora-os4-ota-diagnostic-intake.yml) | 仅接收用户确认的独立诊断草稿，核对证据后标记**待人工分析**；不改 OEM ABI 结果 |
| [可信阶段状态](../.github/workflows/pandora-os4-stage-status.yml) | 生成手机工作台看到的 GKI / ABI / 待测 / 稳定状态；已核实能正确显示 Gen7 |
| [LKG 复现（历史 R62）](../.github/workflows/xiaomi-sm8850-os4-lkg.yml) | 仅旧 R62 晋升路线可能用到的后台接力，**不是现在让你手动运行的构建入口** |
| [LKG 长期归档（历史 R62）](../.github/workflows/xiaomi-sm8850-os4-archive-lkg-release.yml) | 旧 R62 复现成功后归档；OS4.0.6 Gen7 的归档由统一晋升入口完成 |

## 只有出问题时才用的维修入口

| 工作流 | 什么时候才用 |
| --- | --- |
| [固定输入事务恢复](../.github/workflows/pandora-os4-stock-input-recovery.yml) | 手机 OTA 上传过程中断，且已经找到来源 Draft、运行编号和事务 SHA；默认先选 **audit（只检查）**，确认后再决定恢复 |
| [OTA 自动候选](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml) | 固定输入已接收但自动候选没有接上，或过期候选需要按已归档 SHA 恢复；不要用它绕过检查 |
| [晋升 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) | 已成功晋升但最后公布 Release 失败，才使用草稿修复模式；**正常晋升不勾选修复** |
| [LKG 旧归档](../.github/workflows/xiaomi-sm8850-os4-archive-lkg-release.yml) | 只在核对历史 R62 复现来源时使用，不作为新版 Gen7 发布入口 |

## 自动检查：保留，不是没用的工作流

| 工作流 | 为什么留着 |
| --- | --- |
| [OTA 助手 APK / 固定签名](../.github/workflows/pandora-os4-ota-companion-apk.yml) | 确保升级安装不换签名、原来数据还能保留 |
| [OTA 助手模拟器](../.github/workflows/pandora-os4-ota-companion-emulator.yml) | 检查按钮、页面、诊断草稿恢复与异常处理；**不等于已经真机验证** |
| [手机 OTA 接收契约](../.github/workflows/pandora-os4-ota-mobile-intake-contract-tests.yml) | 防止文件/来源/SHA 校验被后续修改弄坏 |
| [OS4.0.6 兼容构建回归](../.github/workflows/pandora-os4-compat-custom-build-route-tests.yml) | 防止 EEXIST、运行时模块选择、构建和 LKG 晋升误放行 |
| [历史 OEM ABI 真实阻断回放](../.github/workflows/pandora-os4-ota-v2-evidence-replay.yml) | 用独立冻结的 OS4.0.6 原始采集包重跑旧案例，必须仍是 `BLOCKED` |
| [SUSFS 源码兼容验证](../.github/workflows/pandora-os4-susfs-priority-upstream-check.yml) | 核对已知 SUSFS 源码布局及辅助函数兼容修补，防止上游改变后编译出错；属专项回归，不是新 OTA 工作流 |
| [上游文件隔离门禁](../.github/workflows/xiaomi-upstream-isolation-guard.yml) | 保护上游共有文件不被本仓的 pandora 改动覆盖 |

## 红米 K50 Pro 与上游同步：另一套系统，不要与小米 17 Pro 混用

| 工作流 | 用途 |
| --- | --- |
| [K50 Pro 自定义隔离修复版](../.github/workflows/kernel-custom-fork.yml) | K50 Pro 日常编译，保留自己验证有效的兼容补丁 |
| [隔离版构建组件](../.github/workflows/build-fork-custom.yml)、[管理器组件](../.github/workflows/get-manager-fork.yml) | 被 K50 Pro 入口调用，**不是单独操作入口** |
| [K50 Pro 自动跟进上游](../.github/workflows/generic-custom-auto-sync.yml) | 上游代码有变化时才验证并同步隔离版，不强制切回上游原版 |
| [K50 Pro 隔离守卫](../.github/workflows/generic-custom-fork-guard.yml) | 保证补丁和构建入口不会在同步中被覆盖 |
| [上游原件完整同步](../.github/workflows/upstream-exact-auto-sync.yml) | 将上游文件原样同步，任何不兼容先拦住；不会碰你已确认的 Gen7 稳定包 |

## 哪些东西不该再当成现行操作方法

- **OS3 / Gold / 6.12.23 的实验路线**：已经退出当前系统；旧结论只作为历史证据，不能刷到 OS4.0.6。
- **R62 的 Gen4 及 OS4.0.6 的 Gen5、Gen6**：属于历史稳定快照，不能替代当前 Gen7。保留旧 Release 是为了核对与恢复，不表示要重新跑旧实验。
- **历史 ABI 回放**：测试“当初应该阻断的输入仍被阻断”，**不是**为新 OTA 申请兼容放行。
- **上游原版 `emergency-cleanup.yml` 和 `susfs-probe.yml`**：属于必须原样同步的上游文件，并不是本仓新建的日常入口。尤其不要对 Gen7 LKG 使用上游的 Emergency Cleanup，它的 Critical 选项会删除 Release 附件！

当前状态和真机证据以 [项目首页](pandora-os4-guide.md)、[Gen7 当前指针](../.github/config/ota-lkg-current.json) 和 [正式归档](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen7) 为准。**未来新的系统 OTA 仍需独立采集、ABI 门禁和真机确认。**
