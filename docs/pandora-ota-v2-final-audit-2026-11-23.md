# Pandora OTA 自动化 V2 · 全链路最终审计（2026-11-23）

> 适用设备：小米 17 Pro / `pandora` / HyperOS `OS4.0.6.0.XBLCNXM`。本页以 GitHub 上的真实配置、发布、运行结果及用户提供的手机反馈为依据。**不会把模拟器、CI 成功或用户单次声明等同于新 OTA 的硬件兼容证书。**

## 总体结论

- **当前已交付：** OS4.0.6 实际 OTA 适配、同版本真机确认、自定义 Gen7 LKG 正式晋升、长期归档及对应 CI 复现；V2 的真实历史 ABI 阻断回放、生产诊断桥接、只读手机补采页面/协议和异常重试测试已经开发并通过相应自动化验收。
- **自动化能做：** 从可信手机 OTA 采集包接收入库、归档候选 GKI、对同 OTA 执行独立 OEM CRC/KMI 门禁、自动生成安全诊断建议或未验证临时启动包、提供人工真机反馈与版本化 LKG 交易归档。
- **不能声称：** 任意未知新 OTA 可无人工参与自动修好 OEM 私有 ABI、直接刷写、自动通过 DroidSpaces/Root 等运行时验证或自动晋升 LKG。
- **尚待真实场景：** 下一次真实 OTA 发生 `ABI_BLOCKED` 时，首次手机端补采→独立 Draft→只读接收→`REVIEW_REQUIRED` 的全链路实机验收。现在没有这一事件，不应为测试而人为制造危险的内核失败。

## 证据等级矩阵

| 路段 | 当前能力和硬证据 | 审计判定 |
| --- | --- | --- |
| OTA 准备 / Root | 新 OTA 先离线保留原始 `init_boot.img`，Root 后再采集；App 不会改写系统分区 | **需用户先行动**，不能自动 Root/备份 |
| App / 原功能 | 固定签名 0.14.1-dev；用户已在 pandora 实机确认工作台、记录、设置、Root 和 GitHub 连接正常；没有新 ABI 阻断时补采入口正确隐藏 | **实机基础回归通过**；旧采集记录提前主动删除，迁移未测试 |
| 手机上传接收 | 独立 Draft 和文件 ID/SHA/大小校验、固定 stock-input 的先验证后替换事务、接收状态/失败保护；已在 OS4.0.6 的实际 OTA 适配中使用 | **实际已使用 + 契约回归**，新版本需重绑真实 stock |
| GKI 基线 | 原输入和 GKI commit/Module.symvers 绑定、归档前二次校验；不能编出 OEM 私有源码 | **实际 OS4.0.6 经历过**；构建成功不等于 ABI PASS |
| OEM ABI | 真实 OS4.0.6 原始静态失败（Rust Binder 71、同名模块来源 27），生产 checker 与 V2 历史只读回放复现 BLOCKED | **阻断链路有真实证据**，不允许凭诊断器直接放行 |
| V2 引导补采 | 固定白名单，无远程 Shell，身份绑定 stock SHA/build/run，用户预览确认，脱敏 JSON、SHA 绑定 Draft、异常重试、防错配；只读审核返回 `REVIEW_REQUIRED` | **代码/模拟器/契约验证**；真实新 OTA 阻断补采仍待实机 |
| 临时启动、真机反馈、功能版 | `fastboot boot` 必须用户实测，反馈来源/镜像哈希/运行环境/基线三文件门禁；功能版仍需实机验证 | **OS4.0.6 已走通；未来 OTA 不能继承本轮放行** |
| LKG 与归档 | Gen7 `ota-lkg-current.json`，自定义来源 Run 45124613997，原始晋升 Run 45128727756 完成严格复现但并发 `dev` 保护中断；恢复 Run 45135431152 成功；公开 Release 10 项资产 | **Gen7 正式生效**；原始真机确认包与 CI-only 重新构建分开 |

**可核对的固定参照：**

- [Gen7 当前机器可读指针](../.github/config/ota-lkg-current.json)；当前 generation = 7、archive_tag = `pandora-os4-lkg-gen7`。
- [Gen7 公开 Release](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen7)；非 Draft、非 prerelease，10 项资产并带 SHA-256。
- [LKG 恢复/发布成功 Run #9](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45135431152)；首次长编译保护失败 Run [#7](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45128727756) 的日志是并发 dev 漂移，不是复现比对失败。
- [固定签名 APK #220](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45134959638)、[模拟器 #149](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45134959659) 成功；[真实 ABI BLOCKED 回放 #36](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45128473727) 成功。

## 本轮发现和修复的连接缺口

### A. LKG 晋升后可信阶段可能不及时更新

`pandora-os4-stage-status.yml` 原来仅监听旧名 `小米17 Pro OS4 / 将自定义构建晋升为 LKG`，而真正的统一晋升入口现名为 `小米17 Pro OS4 / 晋升真机稳定内核为 LKG`。这会令晋升完成后手机工作台仍读到旧阶段快照，直到定时检查或其他事件触发。

**修复：** 明确监听当前真实 workflow 名称，并把新 OTA 的当前 LKG 指针和已验证开发记录纳入 push 触发范围。仍由只读 collector 严格核验当前固定 stock SHA、来源与归档资产；若新发布尚未完成，失败关闭，不能显示虚假的 LKG。

### B. 诊断 Draft 按 Tag 下载存在 404 风险

`pandora-os4-ota-diagnostic-intake.yml` 原来对 Draft 使用 `gh release download "$TAG"`。GitHub 未发布 Draft 可能不能通过 Tag 端点稳定解析；本仓 Gen7 草稿恢复期间已确认这类故障，原写法缺少真正的端到端实物覆盖。

**修复：** 服务端先核验 Draft Release ID、唯一诊断 Asset ID、文件名、`uploaded`、大小与 GitHub SHA-256，再使用带授权的数字 Asset ID 下载 JSON，落盘后再核对大小/原始字节 SHA，最后由 `verify-ota-v2-diagnostic-evidence.py` 核验 schema、设备、来源及 `BLOCKED` 原始门禁。无法核对时直接拒绝；不会返回 ABI PASS。

### C. 历史真实 ABI 回放在合并后缺少自动回归

此前 V2 历史回放 workflow 的 push 分支仅限 `feat/pandora-ota-v2-*`，无法覆盖后续已合入 `dev` 的生产改动。**修复：** 让命中相关文件的 dev push 也执行只读回放；PR 仍执行相同回归，同时把阶段状态工作流加入路径匹配。回放不会生成启动包。

### D. 真实阶段快照曾错误停在 ABI_BLOCKED（验收发现，追加修复）

首轮审计 PR #136 合并后，可信阶段 Run [#87](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45138306822) `success`，但日志中的 `os4-stage.json` 实际仍显示 `ABI_BLOCKED`，来源 Run 44888223032，而非 Gen7。原因不是 Gen7 发布失败：`collect-os4-stage.py` 仅在有标准 GKI 开发基线 `verification.json` 时才查看版本化 LKG 指针；本次 OS4.0.6 COMPAT-CUSTOM 路线从原始 OEM 静态 ABI 阻断经精确运行时兼容验证晋升，不使用那条标准开发基线记录；并且旧状态代码错误地期望 Gen7 Release 存在直接裸 `Image` 资产。

**追加修复：** 在原始静态 ABI 结果解释之前，独立核验当前固定 OTA 的 Build、source Asset ID、stock SHA 与 GenN 指针完全一致、同一已成功的自定义来源 Run/head、已公开稳定 Release、两份精确原始用户确认 boot/AnyKernel SHA 和独立归档的 `ota-lkg-promotion-record.json` 的 SHA/原始字节；全部匹配才展示 `LKG_ARCHIVED` 并保留 `safe_to_flash=false`。若下一 OTA 的 Build/stock SHA/Asset 不同，**不会继承 Gen7**，必须重新运行新 OTA 的 ABI 门禁。原始静态 OEM checker 及其 `BLOCKED` 历史证据完全不变。

相应负例覆盖旧 LKG 错配新 OTA、用户确认包哈希篡改、缺少标准 `verification.json` 的真实 Gen7 路线。**该项须以追加修复合并后的真实 dev 快照输出 `LKG_ARCHIVED` 才算闭环**，不以工作流绿色代替正确状态。

### E. 历史 ABI 归档回放仍依赖可变的当前 stock-input

当前真实回放参考 `scripts/xiaomi-os4/ota-v2-references/pandora-os4-406-raw-oem-abi.json` 的 `source.stock_tag` 为 `pandora-os4-stock-input`。这是**会被下次 OTA 替换的唯一固定输入 Release**，而历史候选归档只保留 GKI Image、Module.symvers 和报告，没有将原始 OS4.0.6 `xm.zip` 一并锁进独立永久归档。因此下次真正替换固定 stock-input 后，继续对旧 OS4.0.6 执行同一真实回放可能正确地因 SHA 不符而失败；不能把这种失败误判为 OEM ABI 被改变，也不能为了变绿跳过 SHA 校验。

**后续发布门槛：** 在下次接受新的 stock-input 前，先把当前已核对的 OS4.0.6 `xm.zip`（stock SHA `bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8`）固化到独立不可覆盖的、只读可验证来源归档，并把历史回放改为读取该精确归档。当前代码尚未完成这项独立归档事务，列为下次 OTA 前的 P1，不允许静默忽略。

### F. 文档版本漂移

原主入口、LKG 恢复文档和部分应用说明仍把 Gen4/Gen6 或 0.14.0-dev 描述为当前能力，且有文字转义换行残留。**修复：** 主入口以 Gen7 和 0.14.1-dev 为准，R62/Gen4 和 Gen6 的历史验证结论保留，不覆盖老证据；补充本页与真机阶段四验收链接。

## 安全门禁审计结论

1. 输入必须绑定 `pandora`、固件 Build、活动 slot、stock-release Asset ID、stock ZIP SHA 与来源工作流。混用新旧 OTA、固定包中途变化、缺失模块来源必须拒绝或进入明确审核状态。
2. 生产 OEM ABI checker 仍是裁决者。V2 从同份 JSON 解释错误；`ABI_BLOCKED_DIAGNOSABLE` 与 `AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW` 都不能产出可测 boot。`STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST` 也只是未验证临时启动候选。
3. 只读诊断任务 `commands=[]`，App 的本机采集动作固定、有限、不可被服务器下发指令改变；不发送完整 cmdline、日志、模块地址或原始镜像。部分证据标记 `PARTIAL_READ_ONLY`，不能伪造为完整证明。
4. GitHub Draft 审核无论成功还是部分证据，最终只能标记 `REVIEW_REQUIRED`；不能设置 `safe_to_flash`、解除原始 OEM gate、自动刷机或晋升 LKG。老版本 OS4.0.6 的 runtime-selected 规则不能作为下一 OTA 的通用豁免。
5. 真机反馈必须显式用户确认；根权限、Android 完成启动和 uname 不等于真实证明指定 Image 已启动。LKG 仅对本次来源/配置/哈希/用户确认负责，CI-only 重编不冒充第二次真机测试。
6. 上游 zzh20188 共用文件继续受隔离门禁保护；本轮变更限 pandora 专属工作流、测试与文档。追加阶段修复只更改只读状态聚合和对应回归，不改原始 OEM checker / LKG 指针。

## 仍需保留的边界与后续首次触发条件

- 下一次真正新的 OTA 时才验证 Android 真机的 `ABI_BLOCKED`→诊断任务→只读补采→用户预览→独立 Draft→只读审核；**不主动注入有风险的错误或把 Gen7 成功当作新 OTA 通用证明**。
- 若没有新的 ABI 阻断，App 没有「兼容性补采」入口属于正常行为，不需要额外发送重复采集包。
- OTA 助手的本地旧采集记录迁移未测试（用户已清空记录），不应标记 PASS。
- 仍保留正常的用户 Root 准备、电脑临时启动、运行时验收和 LKG 确认，未来兼容补丁可能需要开发者根据诊断制定。
- 只读历史回放、契约测试和独立安全门禁可自动跑；不能把任一工作流绿色状态单独当作刷机许可。

**完成标准：** 相关 PR 的静态/负例回归、真实历史 ABI BLOCKED 回放和上游隔离门禁成功，且追加修复合并后 dev 的可信阶段快照能够核对 Gen7、始终 `safe_to_flash=false`。未来真正新 OTA 的实机补采仍未验证；上文 P1 历史参考 stock 永久归档是下次 OTA 替换前必须处理的独立剩余项。
