# 小米 17 Pro · OTA V2 兼容性阻断后的排查与重建说明

适用范围：只针对 pandora（小米 17 Pro）和同一次真实 OTA 的原始采集包。这里的“自动诊断”是**自动帮忙找线索、减少重复输入和误操作**，不是自动绕过不兼容问题。

## 为什么这样改

两轮真机适配说明，单次构建失败不等于一个通用补丁就能解决。

- **OS4.0.5：** 先使内核及 Root、SUSFS、NoMount 等功能正常，再逐一验证 BBG 是否真的进入 active LSM、KernelSU LKM 是否彻底退出，以及 DroidSpaces 的 `pids`、网络组件和其他运行时能力。编译成功不等于功能生效。
- **OS4.0.6：** 原始 OEM 模块检查最初有 923 次未解析导入。读取本 OTA 的 `vendor_boot` 早期模块后，852 次找到具有精确导出 CRC 的提供者；剩余 71 次集中于 Rust Binder。另有 27 次同名模块提供者歧义，涉及 vendor 与 system 不同来源的 zsmalloc，不能混在一起。
- **OS4.0.6 最终可用：** 通过精确的模块选择、Binder 实际运行方式、同 OTA 真机测试和持久重启验证才完成适配。这些结果只适用于被验证的固件、源码提交和资产哈希，不会变成下一次 OTA 的通用豁免。

## 正常会发生什么

1. **手机正常 OTA、取得 Root 并采集原始包。** 助手将原始采集包交给固定的 stock-input 接收流程，保持原始 `init_boot.img` 离线备份；不在这一步修改内核。
2. **自动编出隔离的 GKI 基线并运行 OEM ABI/KMI 检查。** 静态检查若是 `BLOCKED`，不生成可临时启动的 boot。
3. **可诊断的阻断才创建手机补采任务。** 如果只是 stock 输入不完整、来源不可信或者静态审计自身出错，会停在服务端排查，不让手机重复采集无关信息。
4. **手机工作台出现「查看补采建议」时再操作。** 从同一 Run 获取不可执行的只读任务；采集到 Binder 运行模式、已加载模块与 GNU Note 指纹，用户预览并确认后，上传单独的 GitHub Draft。没有入口即无须补采。
5. **安全审核与处理建议。** `pandora-os4-ota-diagnostic-intake.yml` 核对 Run、源码 SHA、stock Build、原始 ZIP SHA、附件 ID 与字节 SHA，返回 `REVIEW_REQUIRED`，并另存 `diagnostic-recovery-plan.json` 和中文说明。根据实际错误提示“补齐 vendor_boot 模块图”“区分 vendor/system CRC”“复核 Binder 与 Rust ABI”等，不会直接写补丁、触发编译或发布可刷包。
6. **开发者真正解决问题后，重新产生新的候选。** 如果只是采集器漏掉了早期模块，应修正来源/解析并使用新的完整输入重跑门禁；如果是内核 ABI 不兼容，应在 pandora 隔离代码中改正后，重新编出绑定同 OTA 的 Image、Module.symvers 并重新进行 OEM 静态校验。**不允许只对同一未修改候选重复运行一次，就声称问题已经解决。**
7. **新候选全部静态通过后仍需真机操作。** 用户电脑执行临时 `fastboot boot`、检查 Root/SUSFS/NoMount、BBG LSM、Re-Kernel、DroidSpaces、zram/zsmalloc 来源；持久化验证后，由用户明确确认是否晋升新版 LKG。

## 审计的强制边界

- 任一阶段 `BLOCKED` 都不生成可测 boot、不会自动 `fastboot flash`、不会自动晋升 LKG。
- 工作流成功、诊断 Draft 保存、`REVIEW_REQUIRED`、历史 OS4.0.6 回放成功，都**不是** ABI PASS。
- 从手机读到“某模块已加载”或某个 GNU Note 摘要，仅是运行时线索；它不是与 OEM 模块文件 SHA 或提供者 CRC 完全相同的兼容性证明。
- 新 OTA 的 stock Build/原始 ZIP SHA/候选 commit 不同时必须重新核验。不能借用 OS4.0.5 或 OS4.0.6 的已通过门禁结果。
- 上游共用文件保持原样；本次变更位于 pandora 独立工作流、诊断脚本、Android 助手、测试和文档。

## 验收怎么判定

在没有下一次真实 ABI 阻断时，自动验收包括：Python 诊断及负例测试、GitHub Actions 内嵌 Bash 命令语法检查、原始 OS4.0.6 OEM ABI 的冻结回放（应始终是 BLOCKED）、Android 模拟器行为测试，以及上游隔离门禁。下一次真正出现新 OTA 阻断时再验证手机采集、Draft、后端审核与重建候选的实物链路，不人为制造危险的刷机故障。
