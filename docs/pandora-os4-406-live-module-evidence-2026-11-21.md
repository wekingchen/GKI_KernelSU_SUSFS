# pandora OS4.0.6.0 真机模块来源只读证据

记录日期：2026-11-21。此文档记录用户实际 Xiaomi 17 Pro（pandora）
在 OS4.0.6.0.XBLCNXM / slot B / 原厂 6.12.69 内核下的**只读运行时证据**。
不包含任何刷机、模块主动加载、分区写入或 LKG 晋升。

## 输入证据

- 用户真机采集包：`pandora-live-module-delivery-30667.zip`
- ZIP SHA-256：
  `7ec1ba2638d32687ba1bf3ce216232fcd98a99e92e841662420d000d1880871f`
- device：`pandora`
- build：`OS4.0.6.0.XBLCNXM`
- slot：`_b`
- uname：
  `6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`
- `sys.boot_completed=1`
- boot properties：`ro.boot.verifiedbootstate=green`、
  `ro.boot.vbmeta.device_state=locked`
- `/proc/sys/kernel/modules_disabled=0`

上述 boot 属性只是设备当前报告的启动状态，**不是单独的 system_dlkm AVB
信任链证明**。

## 实际已加载模块

采集的地址脱敏 `/proc/modules`：

```text
node_cache size=36864 users=0
zram size=159744 users=1
zsmalloc size=45056 users=2
rust_binder size=462848 users=0
```

`/sys/module/rust_binder/initstate=live`。

因此本轮已经直接确认上述四个模块当前存在于内核模块命名空间；
此事实仍不等于仅凭模块名知道其完整加载 ELF SHA。

## GNU Build-ID Note：当前运行时来源已经可以区分

PR #109 已从相同 SHA 锁定的原厂 OTA 505 个 .ko 中固定六份
`.note.gnu.build-id` Note SHA。本次真机从
`/sys/module/<name>/notes/.note.gnu.build-id` **只读计算 SHA**：

| 已加载模块 | 真机 Note SHA-256 | 唯一匹配的原厂来源 | 结论 |
| --- | --- | --- | --- |
| rust_binder | `f495767e894fcfed7e9d05b9f04d847bcbe95b9ad79b40193e5795554bc62aa6` | system_dlkm rust_binder | 当前已加载 Rust Binder Note 唯一对应原厂 system 模块 |
| zsmalloc | `531fad7a1fd7fa95976ea97c2cd9c402e63f578d6b0d19266b1545f547a62035` | vendor zsmalloc | **当前运行时 zsmalloc 来源确定为 vendor** |
| zram | `e6c5c0c4c3cfa4ad9f5ea4828391459b3c556dc80a77fd9bd005df2699dc0280` | vendor zram | 当前已加载 zram 来源确定为 vendor |
| node_cache | `24755a08ebe111a8c8b0bbf30e25a6b32c2a0527654efb68109265bd36ef2b02` | vendor node_cache | 当前已加载 node_cache 来源确定为 vendor |

四个真机 Note 都与锁定原厂库存中的**唯一来源**一致，没有出现
unknown / ambiguous / cross-source 匹配。

证据边界：GNU Note 来自当前已加载模块的 sysfs Note 属性，
比单纯磁盘文件 SHA 更接近运行时身份；但它只证明这段 ELF Note，
不等于证明完整内存 ELF 每个字节，也不证明模块加载信任链或 AVB。

## 当前磁盘文件同样与原厂库存一致

本轮真机读取的只读分区文件 SHA 与此前锁定 OTA 原厂库存完全一致：

| 来源 | 真机文件 SHA-256 | 原厂库存 | 状态 |
| --- | --- | --- | --- |
| system rust_binder | `ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c` | 相同 | MATCH |
| system zsmalloc | `b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465` | 相同 | MATCH |
| vendor zsmalloc | `350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e` | 相同 | MATCH |
| vendor zram | `6737e77c46b0a5a998adf552c42191e97068c393c506d83679d24c320f13d166` | 相同 | MATCH |
| vendor node_cache | `bc78bab29b624743419e5a3d7f7f8586dc9f30d682cf3a65608c79601b7ddefd` | 相同 | MATCH |

`vendor_dlkm` 与 `system_dlkm` 都由 dm 设备以 EROFS 只读挂载。

## zsmalloc 24/3 双提供者歧义：当前真机运行时已解决

真机 `vendor-modules.dep` 明确包含：

```text
/vendor/lib/modules/node_cache.ko: /vendor/lib/modules/zsmalloc.ko
/vendor/lib/modules/zram.ko: /vendor/lib/modules/zsmalloc.ko
```

而 `vendor-modules.load` 中：
- `zram.ko`：第 1 项；
- `node_cache.ko`：第 2 项；
- `zsmalloc.ko`：后续显式列出；
- depmod 依赖使 zram / node_cache 加载时会先取得 vendor zsmalloc。

同时当前 `/proc/modules` 的 `zsmalloc users=2`，
且 zram / node_cache 两个已加载模块的 Note 都唯一匹配 vendor 原厂模块。

因此可以给出新的、严格限定于**当前这次原厂启动**的结论：

```text
CURRENT_BOOT_RUNTIME_ZSMALLOC_PROVIDER=vendor
CURRENT_BOOT_ZSMALLOC_SOURCE_AMBIGUITY=RESOLVED
VENDOR_ZRAM_NODE_CACHE_ZSMALLOC_STACK=CONSISTENT
```

这意味着先前静态 OEM 图里的 24 个“同 CRC 双提供者”与
3 个“不同 CRC 双提供者”，在**当前真机实际运行时选源**层面已经
不再是未知：实际选的是 vendor zsmalloc，system zsmalloc 未作为当前
`zsmalloc` 模块的 Note 来源。

但是这**不会自动修改正式候选 gate**：
替换 boot / GKI 后仍需要证明模块加载路径没有改变、候选内核可满足
vendor 模块 KMI，并且 Rust Binder 71 条 OEM 导入问题得到正确处理。
因此 `check-ota-oem-abi.py` 保持原有 fail-closed 逻辑。

## Rust Binder：模块来源已确定，但实际 Binder 实现还需最后一层证据

本轮真机已经确认：

- `rust_binder` 出现在 `/proc/modules`；
- `initstate=live`；
- 已加载模块 GNU Note 唯一匹配原厂 system_dlkm rust_binder；
- 当前 system_dlkm 上的 rust_binder 文件 SHA 也与原厂库存完全相同。

因此：

```text
CURRENT_BOOT_RUST_BINDER_MODULE_LOADED=yes
CURRENT_BOOT_RUST_BINDER_NOTE_SOURCE=system
CURRENT_BOOT_RUST_BINDER_STOCK_FILE_ON_DISK=MATCH
```

但本次 `binder-impl-cmdline.txt` 与
`binder-impl-bootconfig.txt` 都为空，**不能据此判定实际使用 C Binder**。

Android common 在 2025 年已经允许在加载 `rust_binder.ko` 之前通过
Binder sysfs 参数改变 `binder.impl`，因此只搜索 cmdline 不再足够。
后续 Android common 又加入只读
`/sys/module/binder/parameters/active_impl` 来直接报告当前 active
实现。下一次采集将同时读取：
- `/sys/module/binder/parameters/impl`
- `/sys/module/binder/parameters/active_impl`

若 OEM 树存在 `active_impl` 且返回 `rust`，再与当前
system rust_binder Note + `initstate=live` 联合，可把
“Rust Binder 模块已加载”提升为“Rust Binder 当前实际 active”
的更强证据。若该节点不存在，则维持 UNKNOWN，不做反向推断。

## 本次发现的采集器缺口及修复

本轮 `system-modules.load` / `system-modules.dep` 为空，
原因不是已经证明 system_dlkm 没有加载清单，而是旧采集器读取了：

```text
/system_dlkm/lib/modules/modules.load
/system_dlkm/lib/modules/modules.dep
```

而本机 system 模块实际位于：

```text
/system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/
```

Android GKI 非 flatten system_dlkm 的模块元数据也位于
`lib/modules/<uname -r>/`。采集器已修正为优先读取版本号目录，
root-level 路径只保留为次要布局证据。

## 当前门禁状态

- 当前真机 vendor zsmalloc 运行时来源：**已确定**
- 当前真机 system Rust Binder 模块加载来源：**已确定**
- 当前 Binder active 实现：**待补一层 sysfs 证据**
- system_dlkm 版本目录 modules.load / modules.dep：**待重新采集**
- Rust Binder 原厂 71 个 GKI r74 无法解析导入：**仍然存在**
- OEM 精确 `g43b5ab7e247d` 源码：**仍未找到**
- fastboot boot / AnyKernel3 / 持久刷机 / LKG 晋升：**仍然 BLOCKED**

本轮只收窄真实运行时来源，不通过删模块、合并两套 zsmalloc、
伪造 CRC 或修改正式 ABI gate 来消除阻断。

## 第二次补采：system_dlkm 真实加载清单与 Binder impl 已取得

第二次用户真机只读采集包：
`pandora-live-module-delivery-7599.zip`

SHA-256：
`75242f56b2d01372026bb6cf52144cc951aeb847c3396a22ce526772c9794917`

身份、slot、uname、boot complete、verified boot state 与第一份一致。

### system_dlkm 的真实版本目录 metadata

修正路径后，真实文件为：

```text
/system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/modules.load
/system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/modules.dep
```

`modules.load` 共 82 行，其中：

```text
3   kernel/mm/zsmalloc.ko
13  kernel/drivers/block/zram/zram.ko
47  kernel/drivers/android/binder/rust_binder.ko
```

`modules.dep` 共 103 行，相关条目：

```text
kernel/mm/zsmalloc.ko:
kernel/drivers/block/zram/zram.ko: kernel/mm/zsmalloc.ko
kernel/drivers/android/binder/rust_binder.ko:
```

因此已经确认 **system_dlkm 的正式加载清单明确包含 rust_binder.ko**，
且该模块没有硬依赖记录。

root-level：

```text
/system_dlkm/lib/modules/modules.load
/system_dlkm/lib/modules/modules.dep
```

在本机为空；之前第一版采集器确实读取错层级。

### system zram 文件也与原厂库存一致

第二份补采新增：

```text
7a440b89b62385d1affc0dca25af32c75f6e03af1a884e3d2ae8e4e75402b3c3
/system_dlkm/.../kernel/drivers/block/zram/zram.ko
```

与锁定 OTA 原厂 system zram SHA 完全一致。

但当前运行时 zram 的 GNU Note 仍唯一匹配 vendor zram，
进一步说明“位于 system modules.load”与“当前实际加载的是该 system ELF”
不能画等号。

### Binder impl：当前请求状态明确为 C

第二份补采：

```text
/sys/module/binder/parameters/impl = c
/sys/module/binder/parameters/active_impl = <不存在/空>
binder.impl cmdline = <无>
binder.impl bootconfig = <无>
```

同时此前事实继续成立：

```text
rust_binder in /proc/modules = yes
rust_binder initstate = live
rust_binder loaded GNU Note = stock system rust_binder unique match
system modules.load includes rust_binder.ko = yes
```

Android common 2025 年的 Binder 实现选择逻辑中，
`binder.impl` 的 sysfs getter 返回 `binder_use_rust ? "rust" : "c"`；
而 Rust Binder 模块初始化时，如果 `binder_use_rust == 0`，
会直接成功返回而不执行 `unload_binder()`，因此模块完全可以处于
`Live` 状态但不接管 C Binder。

2026-09 才新增的只读 `active_impl` 节点专门用于直接报告当前 active
实现；本机没有该节点，说明不能得到这种更高等级的直接证据。

据此，本机应记录为：

```text
CURRENT_BOOT_BINDER_IMPL_REQUESTED=c
CURRENT_BOOT_RUST_BINDER_MODULE_LOADED=yes
CURRENT_BOOT_RUST_BINDER_MODULE_SOURCE=system
CURRENT_BOOT_BINDER_ACTIVE_IMPL_DIRECT=UNAVAILABLE
CURRENT_BOOT_BINDER_ROLE=C_STRONGLY_SUPPORTED
CURRENT_BOOT_RUST_BINDER_ROLE=LOADED_BUT_INERT_STRONGLY_SUPPORTED
```

这里刻意使用 **STRONGLY_SUPPORTED**，而不是
`DIRECTLY_VERIFIED`：因为 Xiaomi 对应的精确 OEM Binder 源码 commit
仍未取得，不能把 Android common 的行为无条件冒充为 OEM 二进制的逐行源码证明。

### 对“71 个 Rust Binder 未解析导入”的重新分层

这一轮的新证据改变的是**问题分类**，不是取消问题：

1. 当前原厂系统的 Binder 主实现强证据指向 **C Binder**；
2. `rust_binder.ko` 仍被 system `modules.load` 明确要求加载；
3. 因此 OEM rust_binder 的 71 个 Rust 导入缺口属于
   **候选 GKI 的 system_dlkm 模块装载兼容性阻断**；
4. 它不再应被描述成“当前原厂 Binder 主链一定依赖这 71 个 Rust 符号”；
5. 但是内核加载 .ko 时会先完成符号解析，即使模块逻辑最终保持 inert，
   缺失导入仍可能使该 .ko 在候选 GKI 上无法插入。

AOSP 对 system_dlkm 的定义也明确要求 GKI 与其 system_dlkm 模块配套；
system_dlkm 挂载后，由 vendor 进程按 `modules.load` 加载模块。
Android libmodprobe 在处理 modules.load 时，如果模块加载失败会返回失败；
具体到 Xiaomi 的 vendor loader，这个失败是否直接阻断整机启动仍未取得
OEM .rc / loader 行为证据。因此这里继续 fail-closed：

```text
OEM_RUST_BINDER_71_IMPORTS=MODULE_LOAD_COMPATIBILITY_BLOCKER
CURRENT_BINDER_MAINLINE_RUST_DEPENDENCY=NOT_SUPPORTED_BY_LIVE_EVIDENCE
CANDIDATE_BOOT_FATALITY_OF_RUST_BINDER_LOAD_FAILURE=UNKNOWN
OEM_ABI_GATE=BLOCKED
```

后续应优先研究“如何在不修改 system_dlkm 的前提下，让候选 GKI 对
system rust_binder 的加载请求安全处理”，而不是继续把精力放在
“如何让 Rust Binder 成为当前 active 实现”这个已经与真机事实不符的方向。
