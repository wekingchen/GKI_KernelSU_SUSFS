# pandora OS4.0.6.0：路线 A 原厂源码 / 路线 B Rust Binder 非刷机验证

记录日期：2026-11-21。唯一目标：将 4.0.6.0 的 ABI 根因逐项收敛，**不把未验证构建标记为可刷机**。承接
[pandora 4.0.6.0 OEM ABI 审计](pandora-os4-406-oem-abi-audit-2026-11-21.md)。

## 固定原始事实

- 设备 pandora，Android 17，OS4.0.6.0.XBLCNXM，slot B；现用原厂 6.12.69 + LKM Root。
- stock-input xm.zip SHA256：`bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8`。
- 未验证 GKI 来源：`android16-6.12-2026-03_r74`，归档
  [pandora-os4-ota-candidate-OS4.0.6.0.XBLCNXM](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-ota-candidate-OS4.0.6.0.XBLCNXM)，仅 Image / Module.symvers / config。
- 原厂 rust_binder.ko：`scmversion=g43b5ab7e247d`，SHA256：
  `ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c`。
  它的 240 次导入中，71 次 Rust mangled 导入无法在 r74 候选 GKI 的 vmlinux 导出中解析。
- 原厂 Binder 的 Rust core crate 标识与 r74 GKI 不一致。已验证旧 R62 vmlinux 也没有这 71 个导出；旧 R62 AnyKernel3 并未打包 rust_binder.ko。
- 严格 OEM 模块图共检查 38,998 次导入，可比较出的不匹配 CRC 为 0，但剩余 71 个 Rust Binder 未解析与 27 个 zsmalloc 来源歧义。仍为 `BLOCKED`。

## 路线 B：同一次 GKI 构建产物的 Rust Binder 只读配对

新增 `scripts/xiaomi-os4/verify-rust-binder-gki-pair-readonly.py` 与
`test_audit_rust_binder_pair_readonly.py`。设计性质：**单独的诊断工具**，不写入
`check-ota-oem-abi.py` 的放行逻辑，绝不覆盖该工具现有 `BLOCKED` 报告。

1. 固定官方 r74 版本/commit、stock ZIP SHA、GKI Release 的 Module.symvers 与 final.config 的 SHA。
2. 对同一锁定源码运行原有 `build-ota-gki-baseline-candidate.sh` 的纯 GKI Image/modules 构建。
   不改内核配置/上游代码，不打包 boot、AnyKernel3，不上传可供刷写的 .ko 或 Image。
3. 从该构建输出提取 `drivers/android/binder/rust_binder.ko`，比对它的实际 ELF
   `__versions` / `__version_ext_names` / `__version_ext_crcs` 与同构建 GKI 的 vmlinux 导出 CRC。
   要求模块 vermagic 及 SHA 锁定的 Module.symvers 与存档一致。若配置未生成模块，明确 `BLOCKED`。
4. 再以原始 stock ZIP 完整重跑 OEM 依赖图，要求 71 / 24 / 3 的真实阻断仍在，不得借“候选 Binder 自身匹配”伪造 OEM 兼容。
5. 结果只可能是 `PASS_GKI_PAIR_ONLY` 或 `BLOCKED`。前者仅证明**候选新 Binder 与候选新 GKI 配对**；
   它完全不证明 Xiaomi 原厂 Binder 已可加载，也不证明系统会从哪一个分区供给和加载此模块。
   整机 OEM ABI gate 始终 `BLOCKED`。

一次性 GitHub Action 作为隔离诊断使用；验证结束应删除临时 workflow、保留测试和报告结论。
正式 OTA 构建的安全门禁不因这项实验改动。

### 若 GKI 配对通过，下一道仍需单独证明的门槛

- Android 17 的 Binder 运行时究竟使用哪一种实现，不能只看 boot.img 中没有 `binder.impl=rust`；
  必须确认**有效** cmdline/bootconfig、原厂模块加载和实际 Binder 服务行为。
- 若需要替换 system_dlkm 的 Rust Binder，需明确受信任的源码、签名、模块依赖、装载阶段、
  分区更新/恢复机制。单独替换 boot.img 的 AnyKernel3 无法自动提供所需系统模块。
- OEM 其余模块和设备功能的跨 OTA ABI/KMI、启动和恢复仍需独立验收。

## 路线 A：真正的 6.12.69 原厂源码，不能拿相似树代替

公开官方资料（2026-11-21 核对）：

- [MiCode/Xiaomi_Kernel_OpenSource `popsicle-w-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/popsicle-w-oss)
  确实标记支持 Xiaomi 17 / 17 Pro / 17 Pro Max；commit
  `45705be1220b4cfa8100516ad86711656c0b634e`（2026-03-09）。
  **但该分支 Makefile 为 6.11.0**，`android/ACK_SHA` 指向
  `android16-6.12-2025-06_r8` / 6.12.23。
  因此不能声称这套分支就是本 OTA 的 `6.12.69 g43b5ab7e247d` 精确原厂源码。
- [MiCode/kernel_devicetree `popsicle-w-oss`](https://github.com/MiCode/kernel_devicetree/tree/popsicle-w-oss)
  可为厂商 DTS/板级关系提供线索，但单独并非与 OEM Rust core 完全对应的可重建 GKI 源码。
- 社区项目即使基于 6.12.69、相同 SM8850/KMI 或能启动，也不能替代 OEM 源码身份和
  `rust_binder` 导入 CRC 的逐符号验证。

后续查找的**验收标准**：官方可追溯的内核源码 commit / Rust 构建参数 / Rust core 与 Binder crate
构建参数、相同的源码身份；可以重现原厂 Rust 导出及 Binder 71 个真实符号/CRC，
并能核对配置、工具链来源、vmlinux/Module.symvers。单有 `scmversion` 或 Clang/rustc 版本号不是充分证据。

## zsmalloc：vendor 与 system 两个独立来源，任何时候都不合并

| 来源 | 实际 zsmalloc.ko SHA256 | `zs_malloc` CRC | 匹配的消费者 |
| --- | --- | --- | --- |
| vendor_boot / vendor_dlkm（字节相同） | `350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e` | `0x1804f5bc` | vendor `node_cache`, vendor `zram` |
| system_dlkm | `b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465` | `0x36f39fe1` | system `zram` |

- **24 个同 CRC 多提供者**不自动去重，**3 个不同 CRC 多提供者**更不能自动选一份。
- 真机 `/proc/modules` 的 `node_cache / zram / zsmalloc` 和 vendor modules.load
  强烈支持当前 vendor 组合，但无法直接证明加载文件的 SHA/完整路径；未来版本不沿用无证据推断。
- 不将这两套模块的 SHA、CRC、导出和消费者依赖放入同一“可相互替换”的 ABI 池；只有
  从可信来源确认真实分区/装载选择后才能单独分析，各自报告、各自门禁。

**不可变安全边界：** 不解除 OTA OEM gate、不发布 fastboot boot/AnyKernel3、不持久刷机、不晋升
4.0.6 LKG、不改现用 4.0.6.0 + LKM Root，不覆盖原有 4.0.5.0 已验证 LKG。

## 路线 A 追加追踪：公开同源线索与真实性级别

- 公开案例中，pandora / pudding / nezha 使用过同一个 `g43b5ab7e247d` 前缀与
  `abogki561813157` 构建号；popsicle 的相关运行记录显示同一前缀，
  但构建号为 `abogki558343811`。这些是**固件运行标识**，不是独立下载可重建源码的证据。
- 检索 GitHub 的 Android Common Kernel 镜像、MiCode 已索引代码以及 MiCode commit 搜索，
  未取得该 12 位版本前缀所对应的公开可访问源码提交；不能因此假设源码不存在，也不能假定
  `g43b5ab7e247d` 是可在任意公开 Git 仓库解析的全 SHA。
- MiCode 上已有针对 Xiaomi 17 Pro Max 源码的泛化请求
  [#40786](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/issues/40786)，
  但它未提供本机 OS4.0.6.0 的精确内核/模块 SHA 证据，不能当作问题已解决。
- 同平台 Redmi K90 Pro Max 的
  [#41092](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/issues/41092)
  是**另一个内核来源** `gb1493ec68d4a` 的源码请求，不可借用。
- 后续若需要向原厂提交源码对应关系请求，应具体指明本机 `OS4.0.6.0.XBLCNXM`、
  `pandora`、完整 `uname -r`、`scmversion=g43b5ab7e247d`、
  模块 ELF SHA、Rust ABI 71 条无法匹配的事实，明确需要能匹配该版本的
  Linux common + OEM patch + Rust Binder / kernel crate 构建配置、工具链和模块源码。
  **本轮仅整理核验材料，未代表用户对外创建请求。**


## 路线 B 真正实测结果：通过 GKI 配对但 OEM 继续 BLOCKED（2026-11-21）

[SHA 锁定真实构建 Run #44901587883](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44901587883)
已完成全部 job，结论 `success`；仅归档 JSON 证据
`pandora-406-rust-binder-nonflash-evidence`（Artifact ID `14706691903`），不归档可刷包或 .ko。

- 源码：官方 `android16-6.12-2026-03_r74`，commit
  `b1d12d482d767c50cb792d988e4479d3f75c342a`。构建的是与该 GKI 同源的
  `drivers/android/binder/rust_binder.ko`，没有更改上游内核源码或跳过模块构建。
- 产物 `rust_binder.ko` SHA-256：
  `37f916a09c0af9efab84d5962f6344a231f47d365864c5b80de0ba466183aaf5`。
  240 个导入（其中 71 个 Rust mangled）全部与锁定的候选 GKI
  `Module.symvers` 中真实 vmlinux 导出相符：**缺失导入 0，CRC 不匹配 0**；
  `vermagic` 与固定候选 release 一致。
- 被替代的 OEM `rust_binder.ko` SHA：
  `ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c`，
  原来的 **71 个 Rust 导入缺口仍然存在**。新旧模块**绝不是相同的二进制**；
  当前只证明“新 GKI + 配套新 Binder 模块”的静态配对方案有可行性。
- 原始 stock 重新审计仍是 38,998 次导入、71 条 OEM Binder 缺失、
  24 条 zsmalloc 同 CRC 双来源与 3 条不同 CRC 双来源；已找到部分的 CRC 不匹配为 0。
  尤其 `zs_malloc`：vendor 的 `node_cache` / `zram` 要求
  `0x1804f5bc`，system 的 `zram` 要求 `0x36f39fe1`，
  不能把两份 `zsmalloc.ko` 混用。
- **发现非刷机独立注意事项**：这次重新编译的 `Image` SHA-256
  `a846571a053e36e998d64720914f19e107d09b101dd71874321c7ffd17132804`
  与先前固定候选 Release 的 `Image` SHA-256
  `af955281efe49ef22cac3efd4072cfd683ee6ab3f48a173932fbb4442b8a1287`
  **不相同**；但实际重新生成的 `final.config` 和 `Module.symvers`
  经 `cmp` 与锁定候选文件字节完全一致。它仅支持当前静态 ABI 配对结论，
  **不构成 Image 二进制复现通过**。如需进入真正启动测试，仍须追查非确定性来源，
  不可据此把任何一个 Image 当作 OEM 精确重建。
- 没有替换原厂 system_dlkm、没有修改手机、没有证明原厂实际 Binder 实现选择、
  没有解决模块装载/签名/系统分区供给路径，也未完成 zsmalloc 两套实际加载来源的
  文件级证明；因此 `gate=BLOCKED`、`flashable=false`、
  `eligible_for_fastboot_boot=false` 继续保持。**不会进入快启或 LKG 晋升**。

后续路线 B 进入“只读模块供给/签名/加载时序溯源”阶段；路线 A 继续追踪
`g43b5ab7e247d` 对应的准确 6.12.69 OEM Rust/内核源码。
任何替代模块方案必须显式保留完整 OTA 恢复和签名/AVB 约束，不允许通过
删掉 Rust Binder、禁用校验、伪造 CRC 或合并两套 zsmalloc 来消除阻断。

## 第八轮：OS4.0.6 原厂 system/vendor 模块供给静态审计（2026-11-21）

[只读 Run #44903615504](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44903615504)
已对与上一轮相同 SHA 的 stock ZIP 真正复验全部 505 个归档模块；证据工件
`pandora-406-stock-module-delivery-readonly`，Artifact ID `14707270880`。
首轮 #44903500899 失败仅因新解析器错误地将合法的重复 `.modinfo parmtype`
条目视为冲突；已改为**只对单值身份字段严格拒绝冲突**，增补反例测试后复测通过。
上述失败不能解释为 OEM 模块错误。

### 可证实的模块身份（库存，不等于运行时）

- `system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/kernel/drivers/android/binder/rust_binder.ko`
  SHA `ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c`，
  `.modinfo` 中 `vermagic` 对应原厂完整 release、
  `scmversion=g43b5ab7e247d`、`depends` 为空。
  未发现标准 Linux `~Module signature appended~.` 尾标，也未记录
  `.modinfo signer/sig_key/sig_hashalgo`；**仅证明文件中未见这些标记，
  不能据此推导原厂禁止/允许未签名模块、实际加载或 AVB 验证结果**。
- `vendor_dlkm/lib/modules/zsmalloc.ko` SHA
  `350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e`，
  `zs_malloc` 导出 CRC `0x1804f5bc`，与同来源 vendor `zram.ko`、
  `node_cache.ko` 的消费 CRC 完全一致。
- `system_dlkm/.../kernel/mm/zsmalloc.ko` SHA
  `b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465`，
  `zs_malloc` 导出 CRC `0x36f39fe1`，与 system `zram.ko` 的消费 CRC 相符。
  两个来源不能混用，重复提供者 24 同 CRC / 3 不同 CRC 继续阻断。

### 缺失的关键加载证据

- 此已采集的 `xm.zip` **不包含完整的 `system_dlkm.img`**，
  内嵌 `oem-modules.zip` 也没有 `modules.load` / `modules.dep`。
  因此无法从此证据独立证明 system_dlkm 的实际文件系统挂载配置、
  文件选择、`modprobe`/init 加载顺序、模块加载签名策略、AVB 链或
  `rust_binder` 与 C Binder 的实际实现选择。
- 来自已锁定的**候选 GKI final.config（非原厂配置）**：
  `CONFIG_MODULE_SIG=y`、`CONFIG_MODULE_SIG_FORCE=n`、
  `CONFIG_MODULE_SIG_ALL=y`、`CONFIG_ANDROID_BINDER_IPC_RUST=m`。
  不能把这些配置冒充现用 OEM 内核的运行时策略，也不能因
  `SIG_FORCE=n` 直接把 OEM Binder 替换视为安全。
- Android 官方文档：
  [GKI system_dlkm 分区](https://source.android.com/docs/core/architecture/partitions/gki-partitions)
  明确提醒 GKI 内核与其模块需要配套构建、更新，而且 `system_dlkm` 由
  first-stage init 以只读文件系统挂载。此事实支持继续保持原厂分区
  与 OTA 恢复路径不变，**不支持用单个 boot-only AnyKernel3 偷换系统模块**。

此轮证据等级：`PINNED_STOCK_INVENTORY_VERIFIED`，
不是 `RUNTIME_MODULE_DELIVERY_VERIFIED`。生产 gate 仍 `BLOCKED`，
手机不需要改动。

### 已准备下一次实机只读证据采集（尚未在手机执行）

新增 `scripts/xiaomi-os4/collect-pandora-live-module-delivery.cmd`，与现有早期
ABI 采集助手相互独立；只适用于 `pandora / OS4.0.6.0.XBLCNXM`、
需已配置 adb 和 Root。仅运行 getprop、cat、sha256sum；**不会 adb push、
insmod/modprobe、写分区、关闭校验、重启或刷机**。采集资料仅保存到 PC 本地：

- 经 Windows PowerShell 只保留 `binder.impl=...` 的有效 `/proc/cmdline`
  匹配，绝不写出完整 cmdline、序列号、原始 kallsyms 或模块地址；
- `/proc/bootconfig` 中匹配 Binder 的行、已加载模块名称（脱敏）、
  原厂系统/vendor DLKM 挂载和独立 `modules.load/dep`；
- 精确的原厂 system Rust Binder 文件路径及 vendor/system 两套 zsmalloc
  文件 SHA、模块禁用开关及 boot verifiedboot 状态；
- **这些文件路径和本地哈希仍不足以证明运行时加载的具体 ELF**，
  也不验证 AVB、内核签名信任或真实 Binder 选择。

[Windows 原生模拟 ADB 验收 Run #44904322851](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44904322851)
已通过：用原生 `cmd.exe` 运行脚本，实际 `adb.exe` mock 返回含伪造敏感参数、
内核装载地址和分区文件内容的样本，验证只保存过滤后结果；
额外的 4 项静态安全约束测试通过。早期测试失败系模拟 ADB 批处理进程
替换及 PowerShell Add-Type 不支持 Win32 控制台程序的模拟器问题，
最终改用 Windows 自带 .NET Framework C# 编译器生成真实 `adb.exe`，
**不是用户手机上的失败，也没有在用户手机上实测该脚本**。

需要实际运行才可以判断动态加载源；此处只完成备测工具的 Windows 原生
脱敏及只读流程验收，绝不以 mock PASS 代替手机证据。

### 第八轮补充：vermagic 与未来真机证据的解释边界

本轮从不可变原厂 ZIP 中解出的 ELF 还显示：
- system `rust_binder` / `zsmalloc` / `zram` 的完整 `vermagic` 为
  `6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`；
- vendor `node_cache` / `zram` / `zsmalloc` 的 `vermagic`
  是 `6.12.69-android16-6-4k`，不是可据此判定模块等价的同一 SHA 或 ABI。
  两套 `zsmalloc` 导出 CRC 仍然不同，不能因 Android KMI 前缀相同就互换。

未来从真机只读采集到的信息应按证据等级处理：
- `binder.impl=rust` 参数仅证明读取到该启动参数；还需模块加载与 Binder
  功能证据。**没有观察到该参数不能证明实际使用 C Binder**。
- `/proc/modules` 有模块名证明当前加载了同名模块，但不包含加载时原始
  ELF 文件 SHA、装载分区或代替模块的信任链证明。
- `modules.load` / `modules.dep` 是文件系统中提供的装载配置/依赖关系，
  不是任意时刻实际装载的不可伪造轨迹。
- `sha256sum /system_dlkm/...` 只对**当前挂载文件**取 SHA，
  不证明内存中的模块确实来自这个文件；vendor/system 两份 SHA 分开比较。
- `ro.boot.verifiedbootstate` / `vbmeta.device_state` 是设备启动状态证据，
  不能代替 system_dlkm AVB 链的核验，也不是解除签名规则的理由。

任何缺失/错误/冲突的输出标记为 **PARTIAL／UNKNOWN，维持 BLOCKED**；
此阶段不会改变现用分区，不会尝试 `insmod`/`modprobe` 等主动加载。

### 真机补证方法（只读，供后续验收使用）

在已连接 `pandora / OS4.0.6.0.XBLCNXM` 且 `adb shell su -c "id"`
能取得 root 的 **Windows `D:\\platform-tools`** 命令提示符执行：

```bat
cd /d D:\\platform-tools
curl.exe -fL -o collect-pandora-live-module-delivery.cmd "https://raw.githubusercontent.com/wekingchen/GKI_KernelSU_SUSFS/dev/scripts/xiaomi-os4/collect-pandora-live-module-delivery.cmd"
call collect-pandora-live-module-delivery.cmd
```

采集结束会打印本地 `pandora-live-module-delivery-数字` 文件夹名。
检查该文件夹的 `README.txt` 后可将整个**本地文件夹**压缩上传用于对照。
不会向 GitHub 或其它网络服务自动上传手机信息，不会写入手机。
当某个 `modules.load` 或模块文件 SHA 输出为空，按“不存在足够证据”处理，
**不能填充推测路径/假定 Binder 为 C 实现/自动提升到通过**。

此采集只用于下一轮 `RUNTIME_OBSERVATION_PARTIAL` 分析，绝非实机
`flash`、`fastboot boot`、`insmod` 或 `system_dlkm` 替换授权。

### 实机快照离线解释器（只评估磁盘文件，不推断内核模块内存镜像）

新增 `scripts/xiaomi-os4/review-live-module-delivery-readonly.py`：
接收上述 Windows CMD 采集目录作为 `--evidence-dir`，严格核实 pandora、
OS4.0.6.0、slot、完整 uname 与系统启动完成标记；
从 system Binder、system zsmalloc、vendor zsmalloc 各自的
`sha256sum` 文件中识别原始路径并逐个比较固定原厂 SHA。
任何缺项、路径不符、哈希差异，都单独输出 `UNKNOWN` 或
`DIFFERS_FROM_PINNED_STOCK`；**不会以 basename 合并分区**。

即便全部磁盘 SHA 与已归档 OTA 相符，输出也只是
`ON_DISK_PINNED_FILES_MATCH_NO_LOADER_PROOF`：
`module_delivery_verified=false`、
`runtime_loaded_binary_sha256=NOT_PROVEN`、
`binder_implementation_verified=false`、
`signing_trust_verified=false`、
`system_dlkm_avb_chain_verified=false`、
`gate=BLOCKED`、`flashable=false`。

[解释器只读正反例 Run #44904943896](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44904943896)
已通过 6 项测试（包括 system/vendor 互换、缺少哈希、错误 uname、
缺失启动参数和错误文件路径），不涉及设备或改写模块。

## 第九轮：锁定 GKI r74 Image 字节差异已复核定位（2026-11-21）

[真实重建与逐字节对比 Run #44903724196](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44903724196)
完整成功。使用同一锁定官方 r74 commit、SHA 核验后的 r536225 工具链、
相同的 `final.config` 与 `Module.symvers`（两者 `cmp` 全字节一致），
重新编译未验证的 GKI Image；仅归档 JSON，Artifact
`pandora-406-gki-image-drift-readonly`，ID `14707751852`。

| 项目 | 固定归档 Image | 本次重编 Image |
| --- | --- | --- |
| 原始 SHA-256 | `af955281efe49ef22cac3efd4072cfd683ee6ab3f48a173932fbb4442b8a1287` | `76c1eb49cfd910d3cdc66ca67271dd8df2d2d074a7d4d656baea5428be946f5f` |
| 字节长度 | 41,900,544 | 41,900,544 |
| GNU Build-ID | `7363742b1c8d3b4f17dc2f2cb63568837cb960a9` | `17628083a59960831448c3c38d075b3caada8a6c` |
| 模块自动生成证书 SHA-256 | `d5ced7e119ea37108945b39645cdf55364694ce2868c081cbdd5393d5a73b40c` | `708922ce54187696cae705c4f66cd934f0457d7a4c0e3aca1fbaa676ced98f9a` |

- 两份 Image 在原始字节上 **并不相同**，总计 **1,093 个不同字节**，分布在
  **2 个 4 KiB 块**，首次不同的字节位于 offset `27513188`。
- GNU Build-ID 有效载荷，以及 `Build time autogenerated kernel key` 的
  DER X.509 证书所在区间可被现有
  `scripts/xiaomi-os4/describe-image-reproducibility.py` 结构化识别：
  两份证书长度均为 `1324`，起始 offset `39148032`。
- 仅将**各自的** 20 字节 GNU Build-ID 有效载荷和 1324 字节证书范围置零
  后，两份 Image 的整个字节数组完全一致：
  共同的归一化 SHA-256
  `cbda5e08033fd03b88cab50bd6220232ebfb559e87ad790c8cbb66e340dc35b9`。
- 结论限于**相同官方 r74 GKI 构建本身**：确认此次 raw Image 哈希漂移
  可由自动证书与 Build-ID 的差异充分解释，未发现这些区间之外的额外变化。
  不可因此将归一化 Image 当作可刷输出、改写真实 Image、抹掉构建身份，
  也不可把它称为与 Xiaomi OEM 内核的完整源码、ABI 或二进制复现。
  原厂 71 项 Rust Binder 导入缺口与 27 项 zsmalloc 歧义仍然存在。

- 此前独立 Rust Binder 配对 Run #44901587883 的 `Image` SHA-256 为
  `a846571a053e36e998d64720914f19e107d09b101dd71874321c7ffd17132804`，
  **该第三份 Image 没有参加本轮归一化比较，不能将本轮两份一致结果外推到第三份**。
  也不应为追求原始 SHA 一致而关闭模块签名功能。

本轮工作流从隔离开发分支移除，仅永久保留这一证据及原有分析工具，
以免遗留会重复进行全量编译的实验工作流。

## 第十轮：从“磁盘文件”前进到“已加载模块的 GNU Note”（2026-11-21）

### 固定 OEM 原厂模块的 GNU Build-ID 指纹

[真实只读 Run #44907158941](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44907158941)
使用 SHA256 锁定的 `OS4.0.6.0.XBLCNXM` stock-input `xm.zip`，
从 505 个原厂 ELF 模块中分别提取六份 `.note.gnu.build-id`。
[复测 Run #44907393069](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44907393069)
通过全部失败关闭回归测试与相同 stock SHA 实物审计。
只读工件名 `pandora-406-module-notes-stock-readonly`，初次 Artifact ID
`14708556026`；不包含任何 .ko、Image 或刷机文件。

| 原始来源 | GNU Build-ID（20 字节） | 原始 ELF Note SHA256（36 字节） |
| --- | --- | --- |
| system rust_binder | `46a149b63b1e0840be67a2149bdc7d289ad8e4a4` | `f495767e894fcfed7e9d05b9f04d847bcbe95b9ad79b40193e5795554bc62aa6` |
| vendor zsmalloc | `480d7bfab5ee5d65f4031b0a4b4779d8e6dbe424` | `531fad7a1fd7fa95976ea97c2cd9c402e63f578d6b0d19266b1545f547a62035` |
| system zsmalloc | `8ffc2ff08b1473ac0c8a0950250276baa5536292` | `4d8f123bb80cc23169e27f29459957272f969f7e509495dc00639e514378d1fa` |
| vendor zram | `5266cbf45af6482e4c41b46fd5801e54cb81832c` | `e6c5c0c4c3cfa4ad9f5ea4828391459b3c556dc80a77fd9bd005df2699dc0280` |
| system zram | `aef2b1b17c49101f13e9890b1a813cb2b510dd5d` | `b381360dfde4835aca3ccca2a7c73576939bcea28478656281f636bc0092dfaf` |
| vendor node_cache | `98ebcaeec156ef757c59be2fe5f064888ca5e539` | `24755a08ebe111a8c8b0bbf30e25a6b32c2a0527654efb68109265bd36ef2b02` |

- six original GNU Note SHA are distinct; vendor/system `zsmalloc` 依旧
  分别消费 `0x1804f5bc` / `0x36f39fe1` 的 CRC，
  而不是按模块 basename 自动合并。
- Linux 内核源码 [kernel/module/sysfs.c](https://github.com/torvalds/linux/blob/master/kernel/module/sysfs.c)
  将已加载模块的 SHT_NOTE 暴露在 `/sys/module/<name>/notes/`，
  **当内核启用且该路径可访问时**，可以只读 `sha256sum` 该 Note，
  与原厂 ELF Note 哈希交叉比对。
- 在 `scripts/xiaomi-os4/collect-pandora-live-module-delivery.cmd`
  新增四项**可选只读** sysfs Note 哈希：rust_binder、zsmalloc、zram、
  node_cache；找不到 sysfs Note 视为 UNKNOWN 而不是未加载证明。
  Windows PC 本地自动生成 `pandora-live-module-delivery-*.zip`，
  不再需要手动压缩整个目录。
- `scripts/xiaomi-os4/review-live-module-delivery-readonly.py`
  仅在 `/proc/modules` 也观察到相同模块名，且 sysfs Note 路径合法时，
  对比固定 Note SHA。如果 `zsmalloc` **唯一**符合 vendor 或 system，
  分别记录 `runtime_zsmalloc_unique_note_source=vendor/system`，
  但保留 `runtime_loaded_binary_sha256=NOT_PROVEN`、
  `module_delivery_verified=false`、
  `system_dlkm_avb_chain_verified=false`、
  `gate=BLOCKED`、`flashable=false`。
- [Windows 原生 CMD 全链模拟 Run #44907479503](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/44907479503)
  验证了新的 sysfs Note 哈希探针、原始地址脱敏、隐私参数过滤、
  完整证据目录自动压缩为 ZIP，**属于 Windows mock，不是手机真机结果**。
  真机上 sysfs Note 是否实际存在、是否匹配，尚未采集。

**证据等级**：若真机 Note 唯一对应某个 stock ELF，可以将该已加载模块的
`GNU Note` 与原厂库存来源对应；它仍不能直接证明完整内存 ELF 字节、
实际加载文件路径、AVB、模块签名策略或 Binder 服务切换。
因此只收窄来源判断，不作为解锁 71 条 Rust ABI 或 27 条 zsmalloc 歧义
的通行证。路线 A 精确 OEM 源码仍未得到。


## 第十一轮：真机表明 C Binder 是当前主实现强证据（2026-11-21）

第二份补采已经取得 `/sys/module/binder/parameters/impl=c`，
而 system `modules.load` 又明确包含原厂 `rust_binder.ko`。
结合当前 Android common Rust Binder init 行为，`rust_binder.ko`
在 `binder_use_rust == 0` 时可以加载为 Live 但不接管 C Binder。

因此路线 B 的问题重新拆成两条：

1. **当前 Binder 实现选择**：C 为强证据；Rust active 不受真机证据支持。
2. **候选 GKI 模块兼容**：system 仍要求加载 OEM rust_binder；
   r74 对其 71 个 Rust 导入仍无法解析，因此装载兼容继续 BLOCKED。

这使“必须重现 OEM Rust Binder 作为 active Binder”不再是合理目标；
下一步应研究候选 GKI 如何在不修改 system_dlkm、不破坏 C Binder 主链的
前提下安全满足/处理该 `rust_binder.ko` 加载请求，以及 Xiaomi loader
对单个 system_dlkm 模块失败的实际容错边界。


### r74 精确源码复核：不能走官方 dummy，C 模式 inert 语义成立

锁定候选 commit `b1d12d482d767c50cb792d988e4479d3f75c342a`
在只读 Run #44912345351 中直接从 Gitiles 取源码并检查
`drivers/android` 整个子树：

```text
rust_dummy_tree=absent
active_impl=present
rust_module_inert_when_c=yes
```

具体：
- r74 的 `binder.c` 已包含只读 `active_impl` module parameter；
- r74 `rust_binder_main.rs` 在 `binder_use_rust == 0` 时直接返回成功，
  不调用 `unload_binder()`；
- r74 整个 `drivers/android` 子树不存在
  `ANDROID_BINDER_IPC_RUST_DUMMY`，因此不能依赖“官方 dummy rust_binder”
  消除 system_dlkm 的同名模块加载请求。

这与真机 `impl=c` 的证据吻合，也说明更合理的候选方向不是把 Rust
Binder 强制切为 active，而是研究：**是否能在 system loader 之前加载
与 r74 Image 同源、已验证 0 missing / 0 CRC mismatch 的
`rust_binder.ko`**。AOSP libmodprobe 对 `finit_module()` 返回
`EEXIST` 的情况明确按“模块已经加载”处理为成功，因此如果 Xiaomi
使用相同机制，后续 system_dlkm 再遇到 OEM 同名 rust_binder 时可能不需要
真正装入旧二进制。

该方案当前仅是待验证架构假设：
- 尚未确认 Xiaomi 实际 system_dlkm loader 命令及其错误策略；
- 尚未确认候选 r74 模块可在 system loader 之前从哪一受信任位置加载；
- 不修改 system_dlkm、不刷机、不解除 OEM gate。


### 原厂 vendor_boot 离线审计：system_dlkm loader 不在 vendor ramdisk

只读 Run #44912654297 从已锁定 stock-input
`pandora-stock-OS4.0.6.0.XBLCNXM-_b-xm.zip`（SHA 固定）提取并拆开
100663296-byte `vendor_boot.img`，没有再次读取手机。

vendor ramdisk：
- 单一 `vendor_ramdisk00`，LZ4，22173394 bytes；
- `first_stage_ramdisk/fstab.qcom` 明确把 `vendor_dlkm` 与
  `system_dlkm` 都以只读、`slotselect,avb=vbmeta,logical,first_stage_mount`
  挂载；
- ramdisk 自身有早期 `lib/modules/modules.load` / `modules.dep`；
- 但在该 ramdisk 的 .rc / fstab / shell / module metadata 中，没有找到
  负责 `/system_dlkm` 的 `modprobe` / `dlkm_loader` / `rust_binder`
  加载命令。

因此可确认 system_dlkm 分区的挂载信任链入口存在于 first-stage，
但**实际 system_dlkm 模块加载动作不在这份 vendor ramdisk 可见脚本中**；
它符合 AOSP 的设计：first-stage 挂载 system_dlkm，后续 vendor process
再按 `modules.load` 加载。

这也给“提前加载同源 r74 rust_binder”方案划定了现实边界：
- AOSP libmodprobe 对 `finit_module()` 返回 `EEXIST` 明确按
  “module already loaded”成功处理，因此“同名模块先加载”在通用 loader
  语义上是成立的；
- 但当前没有确认一个**不改 system_dlkm / vendor_boot、又早于 Xiaomi
  vendor loader** 的可信执行点；
- 当前 fastboot-boot-only 测试模型只替换 boot Image，stock vendor_boot /
  init_boot 继续生效，不能擅自假设它会提前提供候选 rust_binder；
- 所以该方向保留为 `PRELOAD_SAME_SOURCE_RUST_BINDER_HYPOTHESIS`，
  不生成刷包、不放开 fastboot boot gate。
