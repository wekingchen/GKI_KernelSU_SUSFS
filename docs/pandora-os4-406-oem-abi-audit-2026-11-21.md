# Xiaomi 17 Pro · OS4.0.6.0 OEM ABI 实机审计（2026-11-21）

## 设备与来源

- 设备 pandora，系统 `OS4.0.6.0.XBLCNXM`、Android 17、Slot B。
- 官方启动 `boot_b` 的 SHA-256：`a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b`；它与 LKM Root 后的手机采集 boot 一致。
- OTA 输入 Release：`pandora-os4-stock-input`，资产 ID `775019680`，xm.zip SHA-256 `bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8`。
- GKI 固定候选：`android16-6.12-2026-03_r74`，构建 [#44888223032](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44888223032)，只提供未验证的 Image、Module.symvers、final.config，**不具备刷机资格**。
- 新版解析与只读运行证据：[ABI 验证 Run #44891447936](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44891447936)，关联 Artifact `14702022405`。

## 修复了什么

此前版本将 Linux 扩展 modversions 名称尾部对齐 NUL 误当 CRC 符号，也把合法的 basic/extended 同 CRC 重叠判为冲突。PR #99 修复并加入反例测试后，所有 505 个模块都能解析出实际导入的 CRC。

本次进一步加入：

1. 分析 ELF 模块的 `__ksymtab_*` / `__crc_*`，从实际 `__kcrctab` 字节读取 OEM 提供者 CRC，不采用消费模块的预期 CRC 伪造提供者。
2. 建立全量提供者索引，再按导入者与导出者逐项匹配；重复、未找到或 CRC 不一致均保留 BLOCKED。
3. 仅当当前 stock boot 的完整 uname 符合明确的 `6.12.x-androidN-KMI-g<hash>-abogki<bid>-4k` 格式时，接受其唯一确定的短版 `6.12.x-androidN-KMI-4k` vermagic；其他前缀、KMI 或页大小变化均拒绝。
4. 正反测试加入已有 `test_audit_*.py` 门禁，未保留一次性诊断工作流。

## 同一 OTA 原始模块的实测汇总

| 项目 | 结果 |
| --- | ---: |
| 实际读取 OEM 模块 | 505 |
| 全部导入符号 | 30,925 |
| 与候选 GKI vmlinux CRC 匹配 | 26,123 |
| 与唯一 OEM 模块提供者 CRC 匹配 | 3,852 |
| 已找到提供者但 CRC 不匹配 | 0 |
| 找不到受信提供者的导入 | 923 |
| 导出提供者不唯一的导入 | 27 |
| 按 stock boot 严格确认的短版 vermagic 模块 | 402 |
| 完整 vermagic 模块 | 103 |
| OEM 提供的导出符号数量 | 3,671 |

剩余未找到的代表符号包括 `qcom_smem_get`、`ipc_log_string`、`qcom_scm_assign_mem` 等。它们**不能仅凭符号名断言已由原厂内核实现并兼容新 GKI**；需要进一步明确 OEM 私有核心导出或额外厂商模块及对应 CRC。

27 个多提供者问题集中在 zsmalloc 相关符号，不同分区的 OEM/GKI 模块可能重复提供导出；不能未经设备实际模块加载、版本选择及 CRC 审核就基于目录位置自动选取其中之一。

## 当前门禁结论与后续

**BLOCKED，不生成 fastboot boot，不生成 AnyKernel3，不持久刷入，不晋升 LKG。**

已经验证的只有静态解析器和可追溯的部分内核 ABI 映射，不代表整机硬件兼容、新 GKI 可启动或已经恢复 Built-in Root。原 `OS4.0.5.0` LKG 不变，手机保持 `OS4.0.6.0` + LKM Root 使用。

要继续推进必须核对缺失的 923 条符号由原厂内核或未采集的模块提供的证据，以及重复导出的可用模块选择。**不能通过静默忽略这些符号、豁免 CRC 或关闭检查来制造可刷镜像。**
