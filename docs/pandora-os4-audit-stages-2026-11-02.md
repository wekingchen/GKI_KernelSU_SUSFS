# OS4 全链路审计：第一至第三阶段整改

适用 `wekingchen/GKI_KernelSU_SUSFS` 的 `dev`，2026-11-02。App 版本 0.13.0-dev / versionCode 24；保留 0.12.2 的完整 JSON 读取修复和原固定签名。这里记录实现及恢复操作，不代表真实新 OTA 已完成真机验收。

## 第一阶段：隔离门禁与实际内核版本

所有指向 dev 的 PR 都运行独立 `isolation`，不再按 fix/docs/lkg 等分支前缀或 LKG 文件过滤。正反向测试在临时 Git 仓库实际执行隔离脚本，验证这些前缀下的专用文件通过、上游共享文件修改被阻断。

GitHub token 创建 PR 不会自动触发 pull_request 工作流。R62 晋升、新 OTA 晋升及基线反馈三条合并路径现在显式调度独立隔离工作流，固定 head SHA、等待真正的 isolation job 成功，再复查 dev 和 PR。失败或超时保留 PR；GitHub 的服务端保护仍有最终决定权。

**分支保护尚需管理员配置**：当前连接器没有 Administration 写接口，不能把“代码已有门禁”称为“dev 已启用保护”。建议将 `isolation` 设为必需检查并禁止绕过；其他必需检查需同时评估机器人 PR 的触发机制。禁止为绕过缺失的管理接口而给工作流提权。

CVE 调用参数来自内核 Makefile 的 VERSION/PATCHLEVEL/SUBLEVEL，并与锁定的 OS4_KERNEL_VERSION 严格一致；拒绝缺字段、重复定义、系列或版本不符。6.12.69/94 进入修补路径，95/96/120 使用上游已修复路径，继续调用原共享补丁脚本，不修改上游文件。

## 第二阶段：恢复过期候选附件

入口仍为 [OTA 自动候选](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml)，从 dev 手动运行，填写三个参数：

| 参数 | 内容 |
| --- | --- |
| recovery_build | 永久候选的精确系统 build |
| recovery_input_sha | 原始固定 stock-input ZIP SHA256 |
| recovery_manifest_sha | 事先下载永久候选中 RELEASE-SHA256SUMS.txt 后，对该清单文件本身计算的 SHA256 |

三项全部留空为正常检测；只填部分会阻断。恢复要求公开 prerelease `pandora-os4-ota-candidate-<build>`、当前固定输入的唯一资产 ID/SHA 与归档一致。逐项验证完整永久清单、锁定 commit、Image/symvers 哈希及报告。原始字节恢复到本次 Run 的 GKI Artifact，再下载当前输入重新验 SHA、执行 OEM CRC/vermagic 门禁，通过才生成 UNVERIFIED 待测 IMG 和手机表单 sidecar。

不查询最新 GKI 代替旧候选，不重新编译、不覆盖原 Release。新 Run 的来源 commit 和元数据绑定到同一个 checkout；Release 事件仅调度当前 dev，避免旧 tag commit 和实际代码不一致。恢复产生新的 Run ID，手机反馈选择新候选。资产 ID/SHA 变化时拒绝恢复，不能用另一个输入冒充原输入。

## 第二阶段：固定输入中断恢复

接收器先将旧输入完整备份至原手机 Draft，并下载回校验，再持久保存 `stock-transaction-<run>.json`。新输入使用 `pandora-mobile-pending-<run>.upload` 暂存并下载校验，另存固定新资产 ID 的 `stock-staged-<run>.json`，之后才重命名、删除旧 ID、更新固定 Release 和接收回执。

`MOBILE_TRANSACTION_SHA256` 在原 Draft 回执及日志中标识事务。进入事务后遇到异常保持待核验，不在 EXIT trap 中把可能已经提交的切换误报 REJECTED。原手机采集 ZIP、旧输入备份、事务记录均保留，不自动清理。

恢复入口：[固定输入事务审计与中断恢复](../.github/workflows/pandora-os4-stock-input-recovery.yml)，与接收器使用同一个串行锁。指定原 Draft ID、接收 Run ID、事务 SHA 和决策：

| 决策 | 行为 |
| --- | --- |
| audit（默认） | 只读下载、校验并报告 old/new ID 与当前状态 |
| complete | 新包已暂存时继续切换；旧 ID 已删时只补齐提交状态/回执；完成后触发候选检查 |
| rollback | 仅旧 ID 仍存在且哈希一致时删除本事务的新 ID，保留旧输入并回报 REJECTED |

重命名后出现两个 xm.zip 时，其他消费者继续 fail closed；恢复入口只操作本事务绑定 ID。发现无关资产、ID 被替换、备份或哈希损坏时停止。旧 ID 已删除后拒绝回退旧 OTA，应 complete 补回执。准备记录/备份时中断且尚未暂存新包，固定输入未改动，可重新接收；已有日志记录且处于 pending 时先审计。任何路径都不批量删除其他资产。

## 第三阶段：可信阶段快照与手机显示

[全链路可信阶段状态](../.github/workflows/pandora-os4-stage-status.yml)只读运行：首次代码合入 dev 或状态实现更新时触发、相关正式任务完成后触发、每六小时补查，也可从 dev 手动执行。它结合当前固定输入、已保存的身份审计、永久候选、未过期待测附件、dev 中人工基线记录、自定义包校验及稳定归档生成 `os4-stage.json`，存为 `pandora-OTA-STAGE-<producer-run>` Artifact。

| 状态 | 含义 / 下一步 |
| --- | --- |
| NO_NEW_OTA | 没有新 OTA；成功可能只是 NOOP |
| GKI_BUILT | 已归档不可直接刷写的 GKI；无有效待测附件时可显式恢复 |
| ABI_BLOCKED | OEM ABI 未通过，禁止生成待测 boot |
| TESTBOOT_READY | 静态门禁通过并有待测包这一里程碑 |
| WAITING_HUMAN | 当前有效待测包已就绪，等待电脑临时启动、手机测试及人工反馈 |
| BASELINE_VERIFIED | 已合入同版本人工确认的开发基线，不等于功能版稳定 |
| CUSTOM_UNVERIFIED | 同版本自定义包已完成字节/来源核验，仍待真机稳定确认 |
| LKG_ARCHIVED | 用户确认晋升且稳定归档已发布并匹配锁定哈希 |

快照在 WAITING_HUMAN 的 milestones 中保留 TESTBOOT_READY，不把同一已就绪候选伪装成两个独立审批。现有 R62 Gen 4 直接核验锁定配置、原始 boot/AnyKernel3 与公开归档；后续新 OTA 则核验对应版本记录和指针。

App 工作台增加同风格白色圆角状态卡，点击“刷新可信状态”在线查询。仅接受正式 dev 状态工作流的成功快照，并交叉核验仓库、producer Run/commit、源 Run/commit、当前 stock asset ID/SHA、永久候选/归档资产 SHA；待测阶段另核对原候选 sidecar，基线阶段核对来源提交内的记录 SHA。输入变更、双输入、附件过期、最新快照任务未成功或身份不符时清除展示结论，明确提示“状态未验证”。可查看状态来源 Run。

这是按需刷新的已核验阶段快照，不是逐秒编译进度，也不自动执行 fastboot/flash、重启、切 slot 或 LKG 晋升。手机帮助页同步解释八种阶段。

## 验证边界

单元/契约测试覆盖过期第 31 天恢复原字节、输入变更/错误 SHA 拒绝、事务各中断点及孤儿 ID 拒绝、不同前缀隔离正反例和状态来源拒绝。APK 固定签名和 Android 模拟器测试由 PR CI 执行，最终运行编号记录于 PR；只有全绿才合入。以上均不能替代另一版真实 OTA 和真实设备的完整验收。
