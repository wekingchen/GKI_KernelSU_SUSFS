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


## 第四轮：完整早期启动模块进入正式门禁（2026-11-21）

在独立分支 pandora-406-early-module-gate-v2 对原生产门禁进行 fail-closed 改造：

1. 原有 test_os4_full_chain.py 不再用简单的假内容代替 vendor_boot；新增真实格式的 Android vendor_boot v4 + LZ4 Legacy + newc CPIO 合成夹具，内含合法 ELF 的 .ko，实测全链路正反向回归通过。
2. 正式 check-ota-oem-abi.py 对同一 SHA 锁定的 OTA vendor_boot.img 完整解压，读取全部 461 个早期 .ko；只把 SHA256 **字节完全相同** 的模块视为别名，不按文件名或 CRC 推断相同。新增非字节相同的早期模块同时检查其自己的 vermagic、导入 CRC 和导出 CRC。
3. 工作流 OEM ABI 检查 job 安装 lz4；解析、负面篡改、早期模块错 CRC / 自身缺失导入均保持 BLOCKED。

实际只读审计：[Run #44897936109](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44897936109)，工件 pandora-406-full-vendorboot-gate-readonly。本次未重新编译 GKI，继续绑定既有 stock ZIP SHA 与锁定的候选 GKI Release。报告如下：

| 项目 | 数量 |
| --- | ---: |
| 原始 DLKM .ko | 505 |
| vendor_boot .ko | 461 |
| vendor_boot 与 DLKM 内容哈希完全一致的别名 | 293 |
| 新纳入的独立早期 .ko | 168 |
| 新增早期 .ko 的自身导入数 | 8,073 |
| 新检查总导入数 | 38,998 |
| 对候选 GKI vmlinux CRC 匹配 | 33,391 |
| 对模块提供者 CRC 匹配 | 5,509 |
| 已能比对出的 CRC 不匹配 | 0 |
| 未找到符号提供者 | 71 |
| 存在重复提供者的歧义导入 | 27 |
| 解析失败的模块 | 0 |

**关键结论：门禁仍然 BLOCKED（71 Rust Binder 缺失导入 + 27 zsmalloc 重复导出歧义）。** 通过的部分是可复核的真实 CRC 映射，不表示设备可启动。尤其 rust_binder 的 71 条 Rust mangled 符号未找到候选 Module.symvers 的真实提供者，不得通过删掉该模块、跳过导入或伪造 CRC 解除门禁。

另外 27 条 zsmalloc 歧义来自真实的两套 vendor/system 模块：需要模块来源、加载顺序和 CRC 相互匹配的独立证据，不能以“名字一样”将不同二进制合并。

此轮只读复测不生成 fastboot boot / AnyKernel3，不修改原始 OTA 输入 Release、不刷机，也不晋升 OS4.0.6.0 LKG。


## 第五轮：Rust Binder 符号身份与 zsmalloc 加载来源（2026-11-21）

[只读 Rust / zram 审计 Run #44898287199](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44898287199)，产物 pandora-406-rust-zram-evidence，复用了已固定原厂 OS4.0.6.0 ZIP、GKI 候选 final.config、Module.symvers 和上一步 38,998 条依赖报告。

### Rust Binder 问题并非简单没启用 Rust

- 候选完整配置确实为 CONFIG_RUST=y、CONFIG_RUST_IS_AVAILABLE=y、CONFIG_EXTENDED_MODVERSIONS=y、CONFIG_ANDROID_BINDER_IPC=y。
- 候选使用 Android Rust 工具链 rustc 1.82.0-dev (f6e511eec 2024-10-15)，产生 1,745 个以 _R 开头的 vmlinux Rust 导出符号。
- 原厂 system_dlkm 中 rust_binder.ko 实际有 240 个导入，其中 **71 个 Rust mangled 符号找不到候选的同名导出**；所有 71 个残留缺口都来自这一个 .ko。
- 原厂 Rust core crate 标识含 Cs3o2tGsuHyou；候选 GKI 的 core 标识含 CscKZuwGeZtqh。二者的 Rust crate 身份不同，而非没开 CONFIG_RUST。
- 在已有 build-r62-features.sh 中，OS4 R62 自定义编译会实际编译并校验 rust_binder.ko，还特别处理 bindgen 对 task_struct / SYSVIPC 的 ABI 影响；这些修复不是纯原版 GKI 基线自带的。下一步应结合真实 OEM Rust 工具链与源码，复核候选生成的 rust_binder 与原厂系统启动所用模块是否可兼容，**不得修改/伪造 Rust mangled 名或 CRC，不能静默移除 binder**。

### 两套 zsmalloc 的运行时证据

同一个 OTA 内存在两套二进制并且 CRC 不相同：

| 来源 | zsmalloc.ko SHA-256 | zs_malloc 导出 CRC |
| --- | --- | --- |
| vendor_boot / vendor_dlkm（字节完全相同） | 350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e | 0x1804f5bc |
| system_dlkm | b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465 | 0x36f39fe1 |

- vendor node_cache.ko 和 vendor zram.ko 的依赖字段都是 zsmalloc，消费 zs_malloc CRC 是 0x1804f5bc，匹配 vendor 提供者。其早期 ramdisk 文件与 vendor_dlkm 文件 SHA 一致。
- system_dlkm zram.ko 则消费 0x36f39fe1，匹配 system 的 zsmalloc。
- vendor_boot lib/modules/modules.dep 明确列有 zram、node_cache 依赖 zsmalloc，**普通启动**的 modules.load 共 172 行，不含 zram/zsmalloc；modules.load.recovery 则包含这些模块。真机另一个 vendor_dlkm 加载列表包含 zram/zsmalloc/node_cache。
- 真机 /proc/modules 已看到 node_cache、zram、zsmalloc 三者加载，结合依赖 CRC 强烈指向 vendor 版本；但 /proc/modules 无法单独证明模块原始 ELF 文件路径和 SHA，更不能断定 system_dlkm 替代版本在未来构建中永不使用。
- 因此正式门禁继续对 27 条重复提供者维持阻断，不根据 basename、单个相同 CRC 或缺少完整加载来源时自动选择模块。后续报告将分别展示同 CRC 与不同 CRC 重复提供者，帮助跨 OTA 维护人员调查，不暗改放行标准。

**安全结论**：未解决 Rust crate 符号身份、未证明替代模块加载选择之前，GKI 仍只允许只读构建与检查；禁止 fastboot flash、持久 AnyKernel3 或自动晋升 LKG。


## 第六轮：已验证 R62 vs 新 OTA 的 Rust Binder 源码身份检查（2026-11-21）

为避免重复盲目编译/复用旧版本，本轮只读复核了长期归档 Release pandora-os4-lkg-gen5 的 ORIGINAL-evidence.tar.zst（SHA-256 d53626c9258708f24d3de65fe7167a7f3ac8c2560359138a764a7b7f907d80b4）、真实已刷 R62 构建 #43551917368 的 Artifact、原始 AnyKernel3 zip、4.0.6.0 OEM rust_binder.ko 及已锁定 GKI 候选。

- [Run #44899135590](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44899135590)：R62 的 Module.symvers 有 1,745 个 Rust mangled vmlinux 导出，与新 GKI 候选的 1,745 个 Rust 导出**名称全部相同**；但 OEM 4.0.6.0 Rust Binder 所需、候选缺少的 71 个符号，在 R62 的导出表中也**一个都不存在**。已验证 R62 源码提交为 e2b8ca7c8d0551a6124b1a7322f5ae532845f1b5。
- [Run #44899227585](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44899227585)：原始 Gen5 AnyKernel3 只有 Image 等通用工具，不包含 rust_binder.ko 或任何系统/厂商分区模块替换。因此“旧 R62 成功启动”**不能证明**它可以驱动新 OTA 的原厂 Rust Binder。
- Android 官方 tag android16-6.12-2026-03_r74 中 CONFIG_ANDROID_BINDER_IPC_RUST 是 tristate：Rust Binder 是传统 C Binder 的另一实现，文档称默认 C，内核命令行设 binder.impl=rust 才选择 Rust。请注意这是源码定义，不等于已经证明当前真机运行时选择情况。
- [Run #44899319807](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44899319807)：原厂 rust_binder.ko SHA-256 ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c；ELF .modinfo 表示 scmversion=g43b5ab7e247d、vermagic 为原厂 6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k。
- 原厂模块 ELF .comment 表明 Clang 19.0.1（r536225）及 rustc 1.82.0-dev（f6e511eec，Android Rust Toolchain linux-glibc-15545352）。这与候选工具链的 **主版本和 Rust commit 名称**一致，但不能仅凭版本号证明二进制工具链、Rust crate 源码或编译参数完全一致。
- stock boot 与 vendor_boot 头部没有检测到 binder.impl=rust；bootloader 最终注入的 cmdline/bootconfig 未由这一离线检查证明。
- R62 原始长期 evidence 归档与原生原始构建 Artifact 均没有直接保存 rust_binder-R62.ko 作为独立可提取文件；虽然旧构建日志曾显示成功编译了该模块，不能声称已验证可以无损替换新 OEM 模块。
- [Run #44900070853](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44900070853)：正式 ABI 门禁现在从原厂 rust_binder.ko 的 .modinfo 中保留 scmversion 和模块字节 SHA 作为证据；对真实 4.0.6.0 原始 ZIP 实测：240 个 Rust Binder 导入、71 个未解析、24 个同 CRC 重复来源和 3 个不同 CRC 来源，**仍 BLOCKED**，没有生成 boot。

### 路线取舍

明确不采用：复用旧 R62 导出、重新编译同一份纯 GKI 并期待 Rust 名称自己变化、伪造 Rust mangled 名称/CRC、静默忽略 rust_binder、把未验证的系统模块替换写入真实设备。

需要真正完成的下一步是获取/复原与 g43b5ab7e247d 对应的 Rust kernel/core 源码及构建参数，或者在候选 GKI 内构建并验证匹配该候选内核 Rust exports 的 Binder 模块，再**单独设计可恢复的运行时模块供给和加载证明**。它不能靠只替换 boot.img 的旧式 AnyKernel3 自动实现。必须保留可回滚路径并继续隔离上游源码。若缺乏这些源和加载证据，ABI gate 保持 BLOCKED；不生成新 OTA fastboot boot，不晋升 LKG。

## 第七轮：路线 B 原生 GKI 配套 Rust Binder 已完成非刷机验证（2026-11-21）

详见 [路线 A/B 进展、完整来源和验证结果](pandora-os4-406-rust-binder-routes-2026-11-21.md)。
[只读验证 Run #44901587883](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44901587883)
证明同源 r74 GKI 构建的候选 `rust_binder.ko` 有 240 个导入（71 个 Rust mangled），
对该候选 GKI vmlinux 导出缺失 0、CRC 不匹配 0。原厂 Rust Binder 的 71 个缺口
仍在，zsmalloc 的 24 个同 CRC + 3 个异 CRC 双来源仍在。
`OEM_ABI_GATE=BLOCKED`，也没有验证模块实际加载、签名、AVB 或重建 Image 的字节一致性。

**下一阶段是定位原厂 6.12.69 Rust 源码与正确的 system_dlkm 模块供给/加载证据，
绝非跳过旧模块或混用 vendor/system zsmalloc。禁止刷机、禁止自动晋升 LKG。**

## 第八轮：模块文件来源与 GKI Image 字节复现分析（2026-11-21）

完整可追溯结果参见 [路线 A/B 记录](pandora-os4-406-rust-binder-routes-2026-11-21.md)。

- [真实原厂模块静态审计 Run #44903615504](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44903615504)
  以固定 SHA stock ZIP 读取 505 个 .ko，确认 system Rust Binder、
  system zsmalloc / system zram 与 vendor zsmalloc / vendor zram / node_cache
  的来源和 SHA/实际 CRC。ZIP 不含完整 system_dlkm.img 和对应
  `modules.load`，不能据此证明运行时实际加载文件或 AVB 信任链；
  vendor/system zsmalloc **继续严格分离**，27 个歧义不放行。
- [Windows 原生 CMD 模拟验收 Run #44904322851](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44904322851)
  证明只读实机数据采集脚本的 Windows 执行、地址脱敏和敏感参数过滤流程，
  不是在真机执行；后续文件 SHA 只能证明磁盘内容、不能证明内存装载字节。
  快照离线校验器另经
  [Run #44904943896](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44904943896)
  6 个正反例测试通过，任何结果都保持 OEM ABI BLOCKED。
- [GKI r74 Image 非刷机重建 Run #44903724196](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44903724196)
  对照此前锁定归档 Image：原始 SHA 不同，41,900,544 字节里有 1,093
  字节不同、位于 2 个 4096 字节块。仅屏蔽各自自动生成的 X509 证书与
  GNU Build-ID 后，归一化 SHA 一致
  `cbda5e08033fd03b88cab50bd6220232ebfb559e87ad790c8cbb66e340dc35b9`。
  此结果解释的是两次**纯 GKI** 构建的非确定性来源，
  不是小米原厂 Image 精确重建或新的刷机放行。

**结论仍为 OEM ABI BLOCKED；禁用 fastboot boot、AnyKernel3、持久刷机、
LKG 晋升。下一阶段必须取得独立的原厂 system_dlkm 加载链/模块来源证据，
路线 A 的准确 OEM Rust 源码也尚未找到。**

## 第九轮：已完成原厂 ELF Build-ID Note 的双来源固定（2026-11-21）

[实际 SHA 固定 stock 审计 Run #44907158941](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44907158941)
从 505 份原厂 .ko 中提取了 system rust_binder、两套 zsmalloc、
两套 zram 及 vendor node_cache 的**独立 GNU Build-ID Note SHA**，
与来源 CRC、文件 SHA 分开报告。vendor/system zsmalloc 的 Note
分别为 `531fad7a1fd7fa95976ea97c2cd9c402e63f578d6b0d19266b1545f547a62035`
和 `4d8f123bb80cc23169e27f29459957272f969f7e509495dc00639e514378d1fa`，
真实互不相同。详见
[路线 B 第十轮完整原厂 Note 表](pandora-os4-406-rust-binder-routes-2026-11-21.md)。

新增 Windows 只读采集器从
`/sys/module/{zsmalloc,zram,node_cache,rust_binder}/notes/.note.gnu.build-id`
**只计算 SHA，不复制原始 Note/内核地址**；采集后仅在本机压缩 ZIP。
离线解释器只有在该 sysfs Note SHA 与唯一原厂来源对应、
且 `/proc/modules` 确认模块名时才报告候选来源，明确不能据此证明
完整内存模块 SHA、装载文件路径/信任或 AVB。

**未有 OS4.0.6.0 真机的上述 Note 快照**，所有启动/刷机门禁继续
`BLOCKED`、71 Rust 导入缺口及 zsmalloc 24/3 来源歧义均不放行。

## 第十轮：OS4.0.6.0 真机运行时来源已收窄（2026-11-21）

用户实际只读采集包 `pandora-live-module-delivery-30667.zip`，
SHA-256 `7ec1ba2638d32687ba1bf3ce216232fcd98a99e92e841662420d000d1880871f`，
已形成独立记录：
[pandora OS4.0.6.0 真机模块来源只读证据](pandora-os4-406-live-module-evidence-2026-11-21.md)。

关键新事实：

- `rust_binder`、`zsmalloc`、`zram`、`node_cache` 均真实出现在
  当前 `/proc/modules`；`rust_binder initstate=live`。
- 真机已加载 `rust_binder` GNU Note 唯一对应锁定 OTA 的
  **system_dlkm rust_binder**。
- 真机已加载 `zsmalloc` / `zram` / `node_cache` GNU Note
  全部唯一对应 **vendor** 原厂模块；同时 vendor `modules.dep`
  明确 `zram -> zsmalloc`、`node_cache -> zsmalloc`，
  且 `/proc/modules` 显示 `zsmalloc users=2`。
- 因此静态图的 zsmalloc 24/3 多提供者歧义，在**本次当前原厂启动的
  实际运行时选源层面**已确定为 vendor，不再是 UNKNOWN。
- 该事实不自动解除候选内核 gate：任何替换 boot/GKI 后仍需验证
  相同模块装载选择、vendor KMI，以及 OEM Rust Binder 71 个导入缺口。
- 第一版采集器错误读取 root-level system_dlkm `modules.load`，
  已修正为 `/system_dlkm/lib/modules/<uname -r>/modules.load`；
  同时新增只读 Binder `impl` / `active_impl` sysfs 采集。
- 修正后 Linux 回归与 Windows 原生 CMD 端到端模拟均在
  [Run #44908512061](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44908512061)
  通过，且测试强制保持 `gate=BLOCKED` / `flashable=false`。

**当前正式状态：** current-boot vendor zsmalloc 来源已解决；
system Rust Binder 模块来源已解决；Binder 当前 active 实现与
system_dlkm 版本目录加载清单等待第二次只读补采。fastboot boot、
AnyKernel3、持久刷机和 LKG 晋升继续禁止。
