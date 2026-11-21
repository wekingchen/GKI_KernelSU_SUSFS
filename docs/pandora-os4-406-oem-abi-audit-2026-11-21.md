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


## 第二轮缺口溯源（2026-11-21）

[只读证据 Run #44892287725](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44892287725)，产物 pandora-406-abi-gap-evidence，只使用与本 OTA 一致的 stock ZIP、已归档 GKI Module.symvers 和前次 BLOCKED 报告。所有输入分别验证其 SHA-256；没有重新编译、没有触碰手机或修改放行门禁。

### 缺失符号分布

- 923 次无法解析的导入，对应 **387 个不同符号、165 个消费模块**（vendor_dlkm 852 次；system_dlkm 71 次）。
- 高频：ipc_log_string 44、ipc_log_context_create 43、ipc_log_context_destroy 32、qcom_smem_get 18、qcom_scm_assign_mem 13。这里的次数是不同导入者引用次数，不能当作不同缺失实现的数量。
- system_dlkm 中 rust_binder.ko 单独有 71 次缺失导入，其中多为 Rust mangled kernel/core 符号。它们必须和候选 Rust 构建配置、工具链、ABI 一起核查，不能只用 C 符号表匹配推论兼容性。
- 候选 Module.symvers 中有 598 个非 vmlinux 提供者的导出符号，但 **没有一个** 能补齐上述 923 条导入。因此，放宽当前 checker 的 vmlinux 提供者限制无法修复本轮阻断。
- 这些符号可能属于原厂内核专有导出，或来自本次采集范围以外的模块。分类需要对应原厂的源码/模块导出及 CRC 证据；仅找到源码中的同名函数并不等于 ABI 对应。

### 27 条 zsmalloc 重复提供者

同一份输入中同时存在 vendor_dlkm 下的 zsmalloc.ko 和 system_dlkm 下的 kernel/mm/zsmalloc.ko：

- 24 条重复导入对应的两份提供者 CRC 相同，**仍需确认运行时实际加载路径，不自动放行**。
- 3 条涉及 zs_malloc。vendor CRC 为 0x1804f5bc；system CRC 为 0x36f39fe1。vendor node_cache 和 vendor zram 期望前者，system zram 期望后者。
- 这些不是可随意合并的冗余文件，而是有实际 CRC 差异的模块组合。禁止选择方便的一份强行替代另一份。
- 未验证真实 modules.load / 已加载模块来源之前，继续 BLOCKED。

### 下一步：只读手机证据

新增加的 Windows CMD 工具：scripts/xiaomi-os4/collect-pandora-live-abi-evidence.cmd（已安装 adb、手机为 pandora、需 Root），只读取：

- 当前 Build、Slot、uname -r 与 boot_completed；
- /proc/modules 已加载模块；
- 能找到的 modules.load 中 zram/zsmalloc/node_cache/rust_binder 条目；
- /proc/kallsyms 中部分核心符号的**名称**，在 Android 端用 awk 去掉地址后才传回电脑。

本地只产生 pandora-live-abi-* 文件夹；不执行 adb push、fastboot、分区写入或自动上传。符号存在性只是进一步定位线索，**不是原厂导出 CRC 的充分证明**，不能自行解除 OEM ABI 门禁。

后续应优先取得确实对应 OS4.0.6.0.XBLCNXM 的 OEM vmlinux / Module.symvers 或完整可重现的源码及配置；已知 Xiaomi 的 popsicle-w-oss 公开源码树 Makefile 为 Linux 6.11，不能直接称为当前 6.12.69 原厂内核的精确源码。

**当前状态：BLOCKED；禁止输出 fastboot boot / AnyKernel3。OS4.0.6.0 + LKM Root 保持可用。**


## 第三轮：实机加载清单与 vendor_boot 早期模块证据（2026-11-21）

真实设备上，OS4.0.6.0.XBLCNXM / Android 17 / Slot B / 原厂 6.12.69-android16-6 内核的 Root 只读采集正常。用户在 Windows CMD 运行了 PR #102 修复后的采集脚本，上传的 pandora-live-abi-29286.zip 由本次排查直接读取：

- 已加载 665 个内核模块，包括 rust_binder、zram、zsmalloc、node_cache、smem、qcom_scm 和 qcom_ipc_logging。
- vendor_dlkm 和 vendor 两份 modules.load 内容相同；均有 665 行，但仅包含 402 个不同文件名。它们不是 665 个不同模块。
- system_dlkm、odm_dlkm、ramdisk 在先前脚本探测的 modules.load 路径上为空；这 **不等于** 这些来源没有实际模块。
- 原厂 /proc/kallsyms 已可读取到 qcom_smem_get、ipc_log_string、qcom_scm_assign_mem、cdev_tevent_alloc 等符号的名称和相应的 __ksymtab_ / __crc_ 标识；只上传名称，没有内核地址。
- vendor modules.load 明确列有 zram.ko、zsmalloc.ko 和 node_cache.ko；但没有硬证据证明当前 zsmalloc 实例的文件哈希。跨分区重复提供者仍应 fail-closed。

只读 GitHub 数据复核：

1. [Run #44894244089](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44894244089)：本次 stock-input 中共有 505 个 DLKM 模块（vendor_dlkm 402 + system_dlkm 103）；原厂 vendor_boot SHA-256 为 e5c72defa27afa9f2e41af85880976784865406d4c785754d5b9c462ca630137，匹配升级前 Windows 离线备份，Boot v4、LZ4 Legacy、单个压缩 ramdisk。
2. 解压 vendor_boot 成功，CPIO 共 471 个条目、461 个 .ko。该库存含额外的 smem.ko、qcom_ipc_logging.ko、qcom-scm.ko、qcom_aoss.ko 等启动模块。以文件名去重后，至少有 168 个不在原 DLKM 库存内。
3. [Run #44894376465](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44894376465)：从这批真实早期 .ko 读取了 3,013 个导出 CRC，对之前 923 条缺失导入逐项对照，**852 条找到了唯一且 CRC 完全一致的早期模块提供者**；没有新的 CRC 不匹配和多提供者记录；剩余 71 条全部由 system_dlkm 的 rust_binder.ko 消费。
4. 样例已核对：qcom_smem_get 由 smem.ko 导出；ipc_log_string 由 qcom_ipc_logging.ko 导出；qcom_scm_assign_mem 则由连字符名称的 qcom-scm.ko 导出。这并不意味着所有早期模块的自身导入对候选 GKI 已通过：最终必须将它们自身依赖也纳入正式静态门禁。

### 生产门禁集成前必须完成的修复

本轮尝试直接将 vendor_boot 早期模块全量接入现有 check-ota-oem-abi.py 后，现有 test_os4_full_chain.py 的若干正向测试变红，因为这些合成夹具把 vendor_boot.img 写成单纯的 b"vendor" 占位内容，无法通过真实 Boot v4 校验。**已撤回该生产门禁实验性改动**；不允许为使 CI 变绿而绕过真实 Boot v4/CPIO 校验。

保留可复用的严格 vendor_boot 解析器及正反测试，正式接线前先将合成夹具升级为有效的 Boot v4 + 真实 LZ4 Legacy/CPIO 样本，确保负向测试仍能发现篡改和缺失。

下一步：

- 正式门禁应从与本 OTA 同 SHA 的 vendor_boot 中读取其实际早期模块，将新增模块的自身 imported_versions / module_export_crcs 也纳入图验证，不仅对已有消费端查 CRC。
- 进一步分析 rust_binder 的 71 条 Rust mangled exports：需要核对 OEM Rust 编译配置、内核 Rust 导出、候选 CONFIG_RUST / 工具链与源构建；不匹配时应重新编译兼容模块，而不是删除或忽略它。
- 对 vendor/system zsmalloc 双份 ABI 进行可验证的来源选择，不能只靠 /proc/modules 的名称或 modules.load 推断已加载文件的精确字节。
- 当前 gate 仍为 BLOCKED，绝不生成 fastboot boot、AnyKernel3 或晋升 LKG。手机继续使用 4.0.6.0 + LKM Root。已归档固件输入包含 vendor_boot，不需要用户重新上传手机 OTA 采集包。

原始实机采集 ZIP 是本地证据，不作为公用代码仓库发布内容；本文件只记录经过核对的统计、原厂哈希和诊断结论。
