# 小米 17 Pro OS4：OS3 功能/优化恢复清单

> device: `pandora`  
> OS4 baseline: `OS4.0.5.0.XBLCNXM` / Linux `6.12.69` / KMI `android16-6`  
> 原则：先保住当前已真机验证的 OS4 基线，再逐项恢复 OS3 已采用功能；每项单独做编译、ABI、临时启动与运行时验证。禁止为了“跟上游”直接把未审核 HEAD 混入日用内核。

## 目标

最终 OS4 日用内核应达到或超过 OS3 阶段的实际功能集，同时继续跟进相关上游项目的新版本、修复和接口变化。

## 当前 OS4 已确认

- [x] Google GKI R62 / 6.12.69 基线可在 pandora 真机 `fastboot boot`
- [x] BakaSU / ReSukiSU Built-in 真机工作
- [x] SUSFS v2.3.0 Manager 识别
- [x] SUSFS SUS_MAP
- [x] NoMount Built-in API v22
- [x] NoMount redirect / whiteout 真机闭环
- [x] NoMount 官方 v2.2.0 Metamodule / userspace v22
- [x] 旧 `kernelsu.ko` LKM 通过 `module_blacklist=kernelsu` 阻止
- [x] 功能版硬件基础回归暂未发现异常
- [x] DroidSpaces 当前除 Process limit / PIDs controller 外，其余已知需求可用

## OS3 已采用、OS4 必须逐项恢复/复核

OS3 full 九项增强曾完成组合编译，#76 真机可启动；其中部分功能有运行时验证。OS4 不直接照搬旧补丁，而是按 6.12.69/R62 和当前上游重新移植。

| 功能 | OS3 状态 | OS4 当前 | OS4 要求 |
|---|---|---|---|
| SUSFS Extra | full 组合通过 | 部分已恢复 | 对照当前 SUSFS 上游重新审核全部 extra 开关 |
| ZRAM 优化 | 真机运行时确认 | 待恢复 | 复核 ZRAM + LZ4K/LZ4KD 等 OS3 采用项，先做 ABI/性能审计 |
| BBG | 真机运行时确认 | 待恢复 | 按当前上游/当前 6.12 接口移植并独立验证 |
| Re-Kernel | OS3 built-in，曾进入真机验证 | 待恢复 | 跟进当前上游接口，先确认 Generic Netlink / hook 路径 |
| NoMount | OS3 后期采用；Magic Mount 被放弃 | **已恢复并 PASS** | 保持 NoMount 默认路线，继续跟进协议/Metamodule 上游 |
| Networking / BBR | OS3 真机运行时确认 | 待恢复/复核 | 恢复 OS3 网络增强并对照 R62 默认配置避免重复开启 |
| DroidSpaces | OS3 主体可用 | **正在恢复** | 当前专项解决 PIDs；Macvlan/CPU 等保持已通过状态 |
| NTSync | OS3 真机运行时确认 | 待恢复 | 作为 DroidSpaces/Windows 兼容增强重新启用并验证 |
| CVE / 安全修复 | OS3 代码/编译验证 | 待重新审计 | 仅保留仍适用于 6.12.69/R62 且上游未已合入的修复 |

## DroidSpaces 专项

### 已知运行需求

- [x] Macvlan support / `CONFIG_MACVLAN`
- [x] CPU limit / `CONFIG_CFS_BANDWIDTH`，且 cmdline 无 `cgroup_disable=cpu`
- [ ] Process limit / `CONFIG_CGROUP_PIDS`，且 cmdline 无 `cgroup_disable=pids`

### 历史教训

OS3 曾出现：

- 不启用 PIDs 的已知可启动配置；
- Macvlan 单独路线真机可用；
- 打开 PIDs 的组合出现过 bootloop；
- DroidSpaces 上游当前仍明确警告：GKI 上 `CONFIG_CGROUP_PIDS` / `CONFIG_CFS_BANDWIDTH` 可能改变核心结构和导出符号 CRC，stock vendor modules 可能因此拒绝加载。

因此 OS4 不允许直接把 PIDs 写入日用配置。必须按以下顺序：

1. 只相对已真机验证的 #12 功能基线增加 `CONFIG_CGROUP_PIDS=y`；
2. 比较 Kconfig 连锁变化；
3. 比较 `Module.symvers` / exported CRC；
4. 若 ABI 有冲突，禁止生成真机测试镜像；
5. 若 ABI 门禁通过，再检查 vendor module imports / vermagic；
6. 只生成 `fastboot boot` 临时镜像；
7. 真机验证 DroidSpaces `Process limit support`；
8. 最后再考虑纳入日用配置。

## 明确不恢复/已放弃

- [x] Magic Mount：已明确放弃，NoMount 为默认路线
- [x] ACK-R51：历史真机不稳定/失败路线，不作为 OS4 目标
- [x] KPM：OS3 full 最终保持 disabled；除非上游和实际需求发生明确变化，不主动恢复
- [x] OS3 6.12.23 作为日用目标：已废止，仅保留历史/恢复参考

## 上游跟踪原则

持续跟踪：

- BakaSU / ReSukiSU
- SUSFS
- NoMount
- DroidSpaces
- Re-Kernel
- 其他 OS3 增强对应上游

但遵守：

1. **跟进上游 ≠ 自动追 HEAD**；
2. 新提交先做 source diff / Kconfig / ABI 审核；
3. 与本机已验证版本相比，确认收益和风险；
4. 每个重要上游升级都必须有可回退的固定 commit；
5. 真机通过后才能提升为默认版本；
6. 不因上游更新破坏当前已验证 Gold/OS4 LKG。

## 当前下一步

正在执行：**OS4 / R62 DroidSpaces PIDs KMI 身份保留方案真机临时启动验证**。

直接 `CONFIG_CGROUP_PIDS=y` 与简单槽位互换均已判定失败；当前仅推进第三轮 ZERO_DIFF 的 net_prio KMI 身份保留方案。


## DroidSpaces PIDs / R62 实测 ABI 结论

2026-10-30 已完成只相对 #12 已验证功能基线增加 `CONFIG_CGROUP_PIDS=y` 的专项编译。

Kconfig 差异严格只有：

```text
ONLY_BASE:
# CONFIG_CGROUP_PIDS is not set

ONLY_PIDS:
CONFIG_CGROUP_PIDS=y
```

导出 ABI：

```text
BASE_VMLINUX_EXPORTS=18725
MATCHED_SYMBOL_NAMES=18725
NEW_EXPORTS=2
MISSING_EXPORTS=0
CRC_CONFLICTS=7005
SAFE_TO_FASTBOOT_BOOT=NO
```

新增导出：
- `pids_cgrp_subsys_enabled_key`
- `pids_cgrp_subsys_on_dfl_key`

结论：

- 直接启用 `CONFIG_CGROUP_PIDS=y` **禁止进入真机测试**；
- 7005 个 CRC 冲突足以造成大面积 stock vendor module KMI 拒绝加载；
- 结果与 OS3 阶段开启 PIDs 后出现 bootloop 的历史现象一致；
- DroidSpaces 上游 v7.1.0 对 GKI 的警告在 pandora / R62 上得到实测验证；
- 当前 #12 继续作为 LKG，不修改、不生成带 PIDs 的 boot 镜像。

后续如果继续攻克 Process limit，必须研究 **保持 `CGROUP_SUBSYS_COUNT` 和核心 cgroup 结构尺寸不变** 的 6.12 专项方案；任何实验先做 ABI-only，不直接进入手机。


### PIDs ABI 实验 2：用 PIDs 替换 net_prio 配置槽位

为避免 `CONFIG_CGROUP_PIDS=y` 直接增加 `CGROUP_SUBSYS_COUNT`，第二轮只做：

```text
BASE:
# CONFIG_CGROUP_PIDS is not set
CONFIG_CGROUP_NET_PRIO=y

CANDIDATE:
CONFIG_CGROUP_PIDS=y
# CONFIG_CGROUP_NET_PRIO is not set
```

`CONFIG_CGROUP_NET_CLASSID=y` 与 `CONFIG_SOCK_CGROUP_DATA=y` 保持不变。

结果：

```text
BASE_VMLINUX_EXPORTS=18725
MATCHED_SYMBOL_NAMES=18723
NEW_EXPORTS=2
MISSING_EXPORTS=2
CRC_CONFLICTS=2571
ABI_LAYOUT_RESULT=FAILED
SAFE_TO_FASTBOOT_BOOT=NO
```

相较直接增加 PIDs 的 7005 个 CRC 冲突显著下降，但仍无法进入真机。

新增：
- `pids_cgrp_subsys_enabled_key`
- `pids_cgrp_subsys_on_dfl_key`

缺失：
- `net_prio_cgrp_subsys_enabled_key`
- `net_prio_cgrp_subsys_on_dfl_key`

说明保持 controller 数量不变仍不足以保持 GKI/KMI：controller 的 ABI 身份与相关类型语义变化仍传播到 2571 个导出 CRC。

第三轮继续采用 ABI-only 方法：保留 `CONFIG_CGROUP_NET_PRIO=y`、`net_prio_cgrp_id` 与原有导出符号身份不变，仅把该槽位内部实现替换为 PIDs，并将 userspace 可见 controller 名称映射为 `pids`。该实验在 ABI 与 OEM 依赖审计通过前仍禁止生成真机 boot。


### PIDs ABI 实验 3：保留 net_prio KMI 身份，仅替换内部实现

第三轮保持以下对外 KMI/Kconfig 身份不变：

```text
# CONFIG_CGROUP_PIDS is not set
CONFIG_CGROUP_NET_PRIO=y
CONFIG_CGROUP_NET_CLASSID=y
CONFIG_SOCK_CGROUP_DATA=y
```

内部仅将原 `net_prio` controller 槽位的实现替换为 `pids.c`，继续使用
`net_prio_cgrp_id` / `net_prio_cgrp_subsys` 的 KMI 身份，并把 userspace 可见
controller 名称映射为 `pids`。

2026-10-30 实验 run `41008768353` 结果：

```text
BASE_VMLINUX_EXPORTS=18725
MATCHED_SYMBOL_NAMES=18725
NEW_EXPORTS=0
MISSING_EXPORTS=0
CRC_CONFLICTS=0
ABI_LAYOUT_RESULT=ZERO_DIFF
SAFE_TO_FASTBOOT_BOOT=NO
```

Kconfig 除实验 `LOCALVERSION` 外也为零差异。

结论：

- 第三轮已经解决前两轮的 **GKI/KMI 导出 CRC 变化**；
- ABI 层不再是当前阻塞项；
- 仍不能直接进入真机，因为替换了原 `net_prio` 的运行语义；
- 下一门禁改为检查 HyperOS 4 用户态配置与 OEM 组件是否显式依赖 `net_prio`；
- 现有 OEM 模块 ABI 报告未发现 `net_prio` / `cgroup` 相关导入记录，但这不能替代用户态运行语义审计。

### PIDs 实验 3A：HyperOS 4 net_prio 用户态依赖采集

新增只读脚本：

```text
scripts/xiaomi-os4/collect-cgroup-netprio-audit.sh
```

约束：

- 强制目标为 `OS4.0.5.0.XBLCNXM`；
- 强制在已记录原厂内核
  `6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k` 上运行；
- 不访问 `/data`；
- 不修改 cgroup、不挂载/卸载、不改系统设置、不刷机；
- 采集 `/proc/cgroups`、cgroup v2 根节点、`cgroups.json`、
  `task_profiles*.json`，并扫描 system/vendor/product/system_ext/odm 文本配置里的
  `net_prio` / `net_cls` / PIDs 显式引用。

手机端执行：

```sh
su -c 'sh /sdcard/Download/collect-cgroup-netprio-audit.sh'
```

输出：

```text
/sdcard/Download/pandora-OS4.0.5.0-cgroup-netprio-audit.txt
```

在这份真实 OS4 报告完成审计前，第三轮仍保持
`SAFE_TO_FASTBOOT_BOOT=NO`；如果未发现阻断性 net_prio 依赖，再生成仅供
`fastboot boot` 的实验镜像，并在真机验证 `pids.max` / `pids.current` /
`pids.events` 与 DroidSpaces Process limit。


### PIDs 实验 3A 真机原厂用户态审计结果（2026-10-30）

在原厂 OS4.0.5.0.XBLCNXM / 原厂 6.12.69 内核上完成只读采集。

关键结果：

```text
android_release=17
/proc/cgroups:
net_cls   hierarchy=0 enabled=1
net_prio  hierarchy=0 enabled=1

实际 cgroup v1 mounts:
blkio -> /dev/blkio
cpu -> /dev/cpuctl
cpuset -> /dev/cpuset
memory -> /dev/memcg

NET_PRIO_V1_MOUNT_COUNT=0

cgroup2 root:
pids.current = ABSENT
pids.events  = ABSENT
pids.max     = ABSENT
pids.peak    = ABSENT
```

`/system/etc/cgroups.json` 只显式配置 `blkio`、`cpu`、`cpuset`、`memory`；
cgroup2 只配置 `freezer`。`/vendor/etc/cgroups.json` 同样只配置 cgroup2/freezer。
`task_profiles.json` 与扫描到的 system/vendor/product/system_ext/odm 文本配置中没有
`net_prio` controller 或 `pids.max` 的实际依赖。

因此：

- 原厂内核虽然编译了 `CONFIG_CGROUP_NET_PRIO=y`，但 HyperOS 4 当前没有挂载/使用 net_prio hierarchy；
- 没有发现 `net_prio.ifpriomap` 的运行时挂载点，故原 net_prio 数据包优先级路径没有用户态配置来源；
- 结合现有 505 个 OEM 模块审计未发现 net_prio/cgroup 相关直接导入，当前没有发现阻断第三轮临时启动的依赖；
- DroidSpaces 实际能力检查依赖运行中的 `cgroup.controllers` 是否出现 `pids`，并在容器 cgroup 写入 `pids.max`，第三轮方案正是针对这一运行接口；
- OS4 userspace 为 Android 17，而 GKI/KMI 仍是 `android16-6`，后续文档需继续区分 userspace 版本与 kernel KMI 分支。

门禁状态更新：

```text
ABI_LAYOUT_RESULT=ZERO_DIFF
OEM_NET_PRIO_DIRECT_IMPORT=NOT_FOUND
OS4_NET_PRIO_V1_MOUNT_COUNT=0
OS4_NET_PRIO_USERSPACE_CONFIG=NOT_FOUND
SAFE_TO_FASTBOOT_BOOT=YES_EXPERIMENTAL
SAFE_TO_FLASH=NO
```

下一步批准生成**仅供 `fastboot boot`** 的第三轮实验 boot-v4。真机通过前不得写入任何分区，
也不得作为日用包或 AnyKernel3 发布。

首轮真机重点：

1. Android 是否正常进入桌面、`sys.boot_completed=1`；
2. `uname -r` 必须为 `6.12.69-android16-6-os4r62-dspids-kmi-4k`；
3. Root / BakaSU / SUSFS / NoMount 基本功能；
4. cgroup2 `cgroup.controllers` 是否出现 `pids`；
5. DroidSpaces `Process limit support` 是否变为 PASS；
6. 实际创建带 process limit 的容器并验证 `pids.max`；
7. Wi-Fi、蜂窝数据、IMS/VoLTE、通话、蓝牙、相机等基础回归，尤其关注网络路径是否出现异常。


### PIDs 实验 3B：ZERO_DIFF 临时 boot 真机启动结果（2026-10-30）

使用 `FASTBOOT-BOOT-ONLY-pandora-OS4-R62-DroidSpaces-PIDs-KMI` 进行
`fastboot boot` 临时启动，真机第一阶段通过：

```text
uname -r:
6.12.69-android16-6-os4r62-dspids-kmi-4k

sys.boot_completed:
1

su -c id:
uid=0(root) ... context=u:r:ksu:s0

/sys/fs/cgroup/cgroup.controllers:
pids

/proc/cgroups:
pids  0  <num_cgroups>  1

/proc/modules:
kernelsu LKM = absent
node_cache / zram / zsmalloc = loaded
```

这说明第三轮方案已经同时通过：

- pandora OS4 真机临时启动；
- Built-in Root；
- stock vendor memory modules 基础加载；
- cgroup controller 用户态名称从 `net_prio` 成功变为 `pids`；
- cgroup v2 根节点明确把 `pids` 暴露为可用 controller；
- `/proc/cgroups` 同样显示 `pids` 已启用；
- 没有加载旧 `kernelsu.ko` LKM。

运行时采集脚本在根层级没有直接发现 `pids.max/pids.current/pids.events` 不构成失败：
cgroup v2 的资源控制文件由父 cgroup 启用 controller 后出现在非根子 cgroup 中。
因此下一门禁不是根目录文件，而是 DroidSpaces 是否能在自己的子层级启用 `pids`
并实际创建/写入 `pids.max`。

当前状态：

```text
FASTBOOT_BOOT=PASS
BOOT_COMPLETED=PASS
BUILTIN_ROOT=PASS
PIDS_CONTROLLER_REGISTERED=PASS
OLD_KERNELSU_LKM_BLOCKED=PASS
VENDOR_MEMORY_MODULES=PASS

DROIDSPACES_PROCESS_LIMIT=UNVERIFIED
PIDS_MAX_RUNTIME_LIMIT=UNVERIFIED
SAFE_TO_FLASH=NO
```

下一步必须先运行 DroidSpaces capability check。只有
`Process limit support` 变为 PASS，并成功创建一个带 PIDs 限制的测试容器后，
才能把 PIDs controller 标记为运行时闭环通过。


### PIDs 实验 3C：DroidSpaces v7.1.0 Requirements 真机结果（2026-10-30）

在第三轮 ZERO_DIFF PIDs 临时内核上运行 DroidSpaces v7.1.0 requirements check：

```text
[MUST HAVE]
[✓] Root privileges
[✓] Linux version
[✗] PID namespace
[✓] Mount namespace
[✓] UTS namespace
[✗] IPC namespace
[✓] pivot_root syscall
[✓] /proc filesystem
[✓] /sys filesystem
[✓] Seccomp support

[OPTIONAL / cgroup]
[✓] Memory limit support
[✓] Swap limit support
[✓] CPU limit support
[✓] CPU usage accounting
[✓] Process limit support
```

关键结论：

- DroidSpaces v7.1.0 已正式把当前 PIDs controller 判定为 **Process limit support = PASS**；
- 因此 net_prio KMI 身份保留的 PIDs 实现不再是当前阻塞项；
- 当前两个致命阻塞项变为 `PID namespace` 与 `IPC namespace`；
- 当前实验最终 config 确认 `CONFIG_PID_NS`、`CONFIG_SYSVIPC`、
  `CONFIG_POSIX_MQUEUE` 均未启用，`CONFIG_IPC_NS` 依赖链尚未展开；
- 当前 `CONFIG_MACVLAN`、`CONFIG_DEVTMPFS`、`CONFIG_USER_NS`、
  `CONFIG_IP6_NF_NAT` 也未启用，但它们不是本轮 MUST HAVE 阻塞项。

下一阶段不修改已经真机通过的 PIDs 实现，只在该基线上：

1. 应用固定 DroidSpaces 6.12
   `001.GKI-6.12-or-above-fix_sysvipc_kabi.patch`；
2. 启用 `CONFIG_SYSVIPC=y`、`CONFIG_POSIX_MQUEUE=y`、
   `CONFIG_IPC_NS=y`、`CONFIG_PID_NS=y`；
3. 先做编译和 Module.symvers/CRC 门禁；
4. ABI 通过后才生成下一份 fastboot-boot-only 镜像；
5. Macvlan、devtmpfs、IPv6 NAT、USER_NS 后续独立恢复，避免把多个 ABI 风险一次混在一起。

当前状态：

```text
PIDS_CONTROLLER=PASS
DROIDSPACES_PROCESS_LIMIT=PASS
PID_NAMESPACE=BLOCKED
IPC_NAMESPACE=BLOCKED
DROIDSPACES_USABLE=NO
SAFE_TO_FLASH=NO
```


### DroidSpaces CoreNS ABI 实验 #1：Image 成功、rust_binder MODPOST 阻塞（2026-10-30）

Run `41014864432` 第一轮结果：

- `Image` 编译成功，耗时 999 秒；
- Image SHA256:
  `aeadac79a3650ce2be0c6f0133efb030c426cbe2ed2ff844ac5939e1053649cc`；
- 最终配置已确认：
  `CONFIG_SYSVIPC=y`、`CONFIG_POSIX_MQUEUE=y`、
  `CONFIG_IPC_NS=y`、`CONFIG_PID_NS=y`；
- 已验证 PIDs KMI 方案仍保持
  `CONFIG_CGROUP_PIDS=n` + `CONFIG_CGROUP_NET_PRIO=y`；
- modules 阶段在 MODPOST 失败：
  `rust_binder.ko` 缺 `init_ipc_ns` 与 `put_ipc_ns` 两个模块可见导出；
- 因 Module.symvers 未完成，本轮没有进入 ABI 对比，不能判定设备安全。

修复策略不是跳过 rust_binder：

1. 真实 `EXPORT_SYMBOL(init_ipc_ns)` 与 `EXPORT_SYMBOL(put_ipc_ns)`；
2. 保持真实 C SYSVIPC/task_struct 布局；
3. 仅对 bindgen 隐藏新增 SYSVIPC 布局，保护 stock rust_binder 的 Rust binding / mangled KMI；
4. 严格 ABI 门禁只允许新增上述 2 个导出，要求所有旧 vmlinux export：
   `MISSING_EXPORTS=0`、`CRC_CONFLICTS=0`；
5. 任意其他新增/缺失/CRC 变化均 `SAFE_TO_FASTBOOT_BOOT=NO`。

对应修复提交：

- `e80b6d6f871866311c22410cb964ef21c00f6c95`
  — preserve Rust KMI + export IPC namespace symbols；
- `250257b0508b209c2e0d31ad85c31685033ef0f2`
  — ABI workflow 只接受精确两符号增量。

新的严格复测：Run `41017403112`。


### DroidSpaces CoreNS ABI 实验 #3：完整构建通过，门禁误判已纠正（2026-10-30）

Run `41017403112` 已完整生成 Image 与 Module.symvers；workflow 最终显示 failure
不是编译失败，而是旧门禁错误地只允许 2 个新增 IPC export。

实际结果：

```text
KERNEL_RELEASE=6.12.69-android16-6-os4r62-dspids-dscore-kmi-4k
IMAGE_SHA256=f42f187538c3ec9026ca26824403f3c963fed6783fc6dc00287db9ffe72b9b8b
SYMVERS_SHA256=f99c78ff1951657743df23f03566812ed6ca5a5f7ffbc6dff67ae34048a20603

BASE_VMLINUX_EXPORTS=18725
MATCHED_SYMBOL_NAMES=18725
NEW_EXPORTS=3
MISSING_EXPORTS=0
CRC_CONFLICTS=0

NEW:
init_ipc_ns  0x59e1383f
put_ipc_ns   0x7c5bd82c
put_pid_ns   0xc6e3bdd7
```

`put_pid_ns` 不是本地补丁意外引入；Google R62 的
`kernel/pid_namespace.c` 原本就有 `EXPORT_SYMBOL_GPL(put_pid_ns)`，
只是基线 `CONFIG_PID_NS=n` 时对应对象/导出不出现。启用 `CONFIG_PID_NS=y`
后该导出自然出现。

因此正确门禁应为：

```text
OLD_EXPORTS_MATCHED=18725/18725
MISSING_EXPORTS=0
CRC_CONFLICTS=0
NEW_EXPORTS_EXACT={
  init_ipc_ns,
  put_ipc_ns,
  put_pid_ns
}
```

满足以上条件时可标记：

```text
ABI_LAYOUT_RESULT=OLD_EXPORTS_ZERO_DIFF_PLUS_3_EXPECTED_NAMESPACE_EXPORTS
SAFE_TO_FASTBOOT_BOOT=YES_EXPERIMENTAL
SAFE_TO_FLASH=NO
```

门禁已在提交 `317490d68b741d393c83ff3da8591d51c47bcefd` 修正。

同时，已退休的两条 PIDs ABI 失败路线仍保持原结论：

- direct `CONFIG_CGROUP_PIDS=y`: 7005 CRC conflicts；
- PIDs/net_prio config slot swap: 2571 CRC conflicts。

它们以及已验证完成的 PIDs-KMI 实验都改为仅手动触发，避免共享构建脚本修改时
重复产生预期失败/重复成功的 Actions 噪音。


### DroidSpaces CoreNS 临时启动包：正式生成（2026-10-30）

CoreNS ABI Run `41020166839` 正式 PASS 后，专用 fastboot-only 工作流
Run `41023562661` 已全部通过。

固定源：

```text
CORE_RUN_ID=41020166839
CORE_RUN_HEAD_SHA=317490d68b741d393c83ff3da8591d51c47bcefd
CORE_IMAGE_SHA256=f31f6702313a1bc7942af4873c005af1072fc6cef192d4d61c4e77cd4fe7018c
CORE_SYMVERS_SHA256=f99c78ff1951657743df23f03566812ed6ca5a5f7ffbc6dff67ae34048a20603
KERNEL_RELEASE=6.12.69-android16-6-os4r62-dspids-dscore-kmi-4k
```

ABI 门禁：

```text
BASE_VMLINUX_EXPORTS=18725
MATCHED_SYMBOL_NAMES=18725
NEW_EXPORTS=3
MISSING_EXPORTS=0
CRC_CONFLICTS=0

NEW_EXPORTS:
init_ipc_ns
put_ipc_ns
put_pid_ns
```

fastboot-only 输出：

```text
Artifact:
FASTBOOT-BOOT-ONLY-pandora-OS4-R62-DroidSpaces-CoreNS
Artifact ID: 12962358606

IMG:
pandora-OS4-R62-DroidSpaces-CoreNS-PIDs-KMI-FASTBOOT-BOOT-ONLY.img

IMG SHA256:
6ec5dd3212c40e0743274b828a5990fadd73fe81a4f20297412e11e3ff6bc153

Embedded CoreNS Image SHA256:
f31f6702313a1bc7942af4873c005af1072fc6cef192d4d61c4e77cd4fe7018c

CMDLINE:
module_blacklist=kernelsu

FINAL_BOOT_V4_AUDIT=PASS
SAFE_TO_FASTBOOT_BOOT=YES_EXPERIMENTAL
SAFE_TO_FLASH=NO
```

下一步只允许真机 `fastboot boot` 临时启动。启动后优先检查：

1. Android 是否完整启动；
2. Built-in root；
3. stock `rust_binder` 是否正常加载，dmesg 无 version/Unknown symbol 错误；
4. DroidSpaces v7.1.0 Requirements 中 PID namespace、IPC namespace 由 FAIL 变 PASS；
5. Process limit support 保持 PASS；
6. 基础 Wi-Fi/蜂窝/IMS/蓝牙/相机回归。

在以上闭环前禁止持久 flash / AnyKernel3。


### DroidSpaces CoreNS 真机 Requirements：MUST HAVE 全部通过（2026-10-30）

CoreNS fastboot-only 候选已在 Xiaomi 17 Pro / pandora / OS4.0.5.0.XBLCNXM
真机临时启动成功。

运行状态：

```text
uname:
6.12.69-android16-6-os4r62-dspids-dscore-kmi-4k

sys.boot_completed=1
Built-in root=PASS
SELinux context=u:r:ksu:s0
old kernelsu LKM=BLOCKED
node_cache/zram/zsmalloc=LOADED
cgroup v2 controllers=pids
/proc/cgroups runtime name=pids
```

DroidSpaces v7.1.0 Requirements 真机结果：

```text
[MUST HAVE]
Root privileges           PASS
Linux version             PASS
PID namespace             PASS
Mount namespace           PASS
UTS namespace             PASS
IPC namespace             PASS
pivot_root                PASS
/proc                     PASS
/sys                      PASS
Seccomp                   PASS

Summary:
All required features found
exit code=0
```

之前阻塞的三项已经形成连续闭环：

```text
Process limit support = PASS
PID namespace         = PASS
IPC namespace         = PASS
DROIDSPACES_REQUIREMENTS=PASS
```

当前仍缺少但不阻塞启动：

```text
RECOMMENDED:
devtmpfs = FAIL

OPTIONAL:
Macvlan = FAIL
IPv6 NAT = FAIL
USER_NS / sandboxing = FAIL
```

CoreNS 运行时日志未见 `Unknown symbol`、`disagrees about version`、
kernel BUG/Oops/Call trace 等 KMI/崩溃标志。

注意：CoreNS 配置为 C Binder built-in + Rust Binder module。
本次 /proc/modules 未显示 rust_binder；这一现象在此前成功启动的 R62 #7
自定义内核路线同样存在，因此不作为本次 CoreNS 回归判定。Android Binder
用户态和系统启动均正常。

当前状态：

```text
FASTBOOT_BOOT=PASS
BOOT_COMPLETED=PASS
BUILTIN_ROOT=PASS
PIDS_CONTROLLER=PASS
DROIDSPACES_PROCESS_LIMIT=PASS
PID_NAMESPACE=PASS
IPC_NAMESPACE=PASS
DROIDSPACES_REQUIREMENTS=PASS
SAFE_TO_FASTBOOT_BOOT=YES
SAFE_TO_FLASH=NO
```

下一步不是立即扩展可选功能，而是创建一个最小 DroidSpaces 测试容器，
完成实际生命周期闭环：

1. 容器可创建并进入；
2. 容器进程确实处于独立 PID/IPC namespace；
3. /sys/fs/cgroup/droidspaces/<container>/pids.max 存在且不是 max；
4. pids.current 正常；
5. 容器停止/删除后 cgroup 清理；
6. 不发生 Android / Binder / 网络 / 存储回归。

完成此闭环后，再按 Macvlan -> devtmpfs -> IPv6 NAT -> USER_NS 的顺序
逐项评估，每项单独做依赖/ABI/真机验证，避免一次性扩大变更面。


### DroidSpaces 容器闭环第一次检查：PIDs 生效，PID namespace 判定脚本需修正（2026-10-30）

真机容器 `test` 已创建并运行，实际 cgroup 结果：

```text
/sys/fs/cgroup/droidspaces/test
pids.max=512
pids.current=9
pids.events:
max 0
```

这证明 DroidSpaces 对实际容器写入的 PIDs limit 已经真正生效，而不只是
Requirements 检查通过。

第一次检查脚本错误地取了 cgroup 中第一个进程并将其作为 container init。
DroidSpaces 的真实启动模型是：

1. monitor 先 unshare UTS/IPC；
2. intermediate 加入容器 cgroup；
3. intermediate 调用 unshare(CLONE_NEWPID)；
4. CLONE_NEWPID 只影响后续 fork 的子进程，intermediate 自身仍在 host PID namespace；
5. fork 出来的 container init 才真正进入新的 PID namespace。

因此第一次输出中：

```text
HOST_PID_NS=pid:[4026531836]
PROCESS_PID=25162
CONTAINER_PID_NS=pid:[4026531836]
CONTAINER_IPC_NS=ipc:[4026536295]
```

说明脚本选中了 intermediate，而不是 container init；PID inode 相同不能据此判定
容器 PID namespace 失败。IPC inode 已经不同则符合 monitor 提前 unshare IPC 的设计。

旧 CMD 还有双层 shell 引号/变量展开问题，导致 inode 相等时仍错误打印
`[PASS] PID namespace isolated`。

修复：

- 新增 `scripts/xiaomi-os4/check-droidspaces-container-runtime.sh`；
- CMD 只负责 push + root 执行该 shell，避免双层变量展开；
- v2 会遍历容器 cgroup 内所有 live task，寻找 PID namespace 与 host 不同的真实子进程；
- 同时打印 NSpid、comm、cgroup 路径，明确识别 container init/child；
- 同时抓取 kernel `Call trace` / BUG / Oops / version disagreement 的上下文。

当前可确认：

```text
DROIDSPACES_REQUIREMENTS=PASS
PIDS_LIMIT_RUNTIME=PASS (512, current=9, max events=0)
IPC_NAMESPACE_RUNTIME=PASS_FOR_INTERMEDIATE
PID_NAMESPACE_RUNTIME=RETEST_REQUIRED_WITH_V2_CHECKER
KERNEL_CALL_TRACE=NEEDS_CONTEXT
SAFE_TO_FLASH=NO
```

第一次日志在约 309.639 秒出现 `Call trace:`，但旧 checker 只 grep 到 marker，
没有保留前后堆栈，暂不能判定来源。v2 checker 会自动输出上下文；在确认该 trace
不是 CoreNS 回归前，不推进持久刷写。


### DroidSpaces CoreNS + PIDs 实际容器闭环：PASS（2026-10-30）

v2 checker 在运行中的 `test` 容器上确认：

```text
HOST_PID_NS=pid:[4026531836]
HOST_IPC_NS=ipc:[4026531839]

CONTAINER_CGROUP=/sys/fs/cgroup/droidspaces/test
pids.max=512
pids.current=9
pids.events.max=0

intermediate / monitor:
pid=25162
comm=[ds-monitor]
pidns=pid:[4026531836]
ipcns=ipc:[4026536295]
NSpid=25162

actual container init:
pid=25163
comm=init
pidns=pid:[4026536297]
ipcns=ipc:[4026536295]
NSpid=25163/1

PID_NAMESPACE_RUNTIME=PASS
IPC_NAMESPACE_RUNTIME=PASS
PIDS_LIMIT_RUNTIME=PASS
```

这验证了 DroidSpaces 的真实生命周期：

- monitor 先进入独立 IPC/UTS namespace；
- intermediate 加入容器 cgroup 并调用 `unshare(CLONE_NEWPID)`；
- intermediate 自身仍显示 host PID namespace，这是 Linux CLONE_NEWPID 语义；
- 后续 fork 的 container init 真正进入新 PID namespace，namespace 内 PID=1；
- 子进程 dhcpcd/getty/sshd 同样位于该新 PID/IPC namespace；
- `pids.max=512` 实际约束运行中的容器，而不只是 Requirements 探测成功。

因此 CoreNS + PIDs 第一阶段正式闭环：

```text
DROIDSPACES_REQUIREMENTS=PASS
PID_NAMESPACE_RUNTIME=PASS
IPC_NAMESPACE_RUNTIME=PASS
PIDS_CONTROLLER_RUNTIME=PASS
PIDS_LIMIT_RUNTIME=PASS
CORENS_CONTAINER_LIFECYCLE=PASS
```

#### iorap2 Call trace 归类

在 DroidSpaces App 启动时出现：

```text
memcpy: detected field-spanning write (size 104)
../soc-repo/drivers/misc/iorap2/launch_boost_preread.c:58
mi_lb_dealwith_preread_info_cmd
 -> mi_lb_ioctl
 -> __arm64_sys_ioctl
```

触发进程是 Xiaomi `iorapd`，模块为 stock OEM `iorap2(OE)`，
调用源来自 Xiaomi launch-boost 对 `com.droidspaces.app` 的 preread 数据。
堆栈不经过 PID namespace、IPC namespace、cgroup PIDs、BakaSU、SUSFS 或
NoMount 路径；warning 后 Android、DroidSpaces 容器均继续正常运行。

该项记录为：

```text
IORAP2_FORTIFY_WARNING=KNOWN_OEM_WARNING
CORENS_REGRESSION_EVIDENCE=NO
BLOCK_MACVLAN_STAGE=NO
```

它仍值得后续用 stock kernel 做一次对照复现，但不阻止继续单项 Macvlan ABI 实验。

下一阶段：仅启用 `CONFIG_MACVLAN=y`，以已真机闭环的 CoreNS 为基线，
要求所有旧 vmlinux CRC 保持、0 missing，并只允许 R62 macvlan.c 的四个
上游导出新增。


### DroidSpaces Full Extras 真机验收：PASS（2026-10-30）

Full Extras Run `41027979653` / head
`87dff623f5f89eb1779e746209b2c172340463ca` 完整编译、ABI/KMI 门禁和
fastboot-only boot-v4 打包均通过。

最终候选：

```text
KERNEL_RELEASE=6.12.69-android16-6-os4r62-dspids-dscore-full-kmi-4k
IMAGE_SHA256=9b47f40a172ebe2ff0d7c5f6d2834db3fce2535379ea11277fcf010042f2db24
BOOT_IMG_SHA256=6298fb802d543f1ff2a9f82ccb953b95e44ce6cf6e91d4469735c6bb892b3086
```

一次性恢复的 DroidSpaces 剩余能力：

```text
CONFIG_DEVTMPFS=y
CONFIG_MACVLAN=y
CONFIG_IP6_NF_NAT=y
CONFIG_IP6_NF_TARGET_MASQUERADE=y
CONFIG_USER_NS=y
```

ABI/KMI：

```text
BASE_ALL_EXPORTS=19326
MATCHED_EXISTING_EXPORTS=19326
NEW_EXPORTS=15
MISSING_EXPORTS=0
CRC_CONFLICTS=0
ABI_LAYOUT_RESULT=ALL_EXISTING_EXPORTS_ZERO_DIFF_NEW_EXPORTS_ALLOWED
```

真机 `fastboot boot` 后 DroidSpaces v7.1.0 Requirements 已全部变绿，
包括此前缺失的：

```text
devtmpfs        PASS
Macvlan         PASS
IPv6 NAT        PASS
USER_NS         PASS
```

此前已验证的 PID namespace、IPC namespace、Process limit/PIDs controller
等均继续保持 PASS。

基础硬件回归：

```text
Wi-Fi          PASS
移动数据        PASS
双 SIM         PASS
VoLTE / IMS    PASS
蓝牙            PASS
相机            PASS
```

因此当前 Full Extras 已从“静态实验候选”提升为
**真机功能与基础硬件回归通过候选**。

#### NoMount v2.2.0 状态

当前 Full Extras 内核的 Built-in NoMount API 已真机确认：

```text
nm version = 22 (1)
exit code  = 0
```

即内核 NoMount v22 API 正常。

官方 NoMount v2.2.0 release-605 metamodule 在本机 HyperOS 4 userspace 下
存在脚本锁兼容问题：

```text
flock: Bad file descriptor
```

其 release-605 `common.sh` / 当前 dev 都使用 FD-based flock。
失败后会留下：

```text
/data/adb/nomount/disable
```

并显示：

```text
Kernel not patched or module failed to load
```

这不是当前内核 NoMount 驱动失败。用户当前没有任何模块需要 NoMount
system/vendor/product 文件注入，`nm rule list` 为空符合当前使用状态，
因此该 metamodule 兼容问题当前无实际功能影响，暂不维护私有修正版，
等待 NoMount 上游修复。

当前阶段结论：

```text
DROIDSPACES_FULL_REQUIREMENTS=PASS
DROIDSPACES_CONTAINER_RUNTIME=PASS
FULL_EXTRAS_HARDWARE_REGRESSION=PASS
BUILTIN_NOMOUNT_API=PASS
NOMOUNT_METAMODULE_HYPEROS4_FLOCK=KNOWN_NONBLOCKING_ISSUE
```

持久化前只保留最后一个低风险检查：
停止并删除 DroidSpaces 测试容器后，确认
`/sys/fs/cgroup/droidspaces/test` 已清理。该检查不需要重新编译内核。


### 持久化候选准备（2026-10-30）

Full Extras 已通过 DroidSpaces Requirements、实际容器 namespace/PIDs、以及
Wi-Fi/蜂窝/双卡/VoLTE-IMS/蓝牙/相机真机回归后，开始准备持久化候选。

为避免再次完整编译，持久化包固定复用已验证的 Full Extras：

```text
SOURCE_RUN_ID=41027979653
KERNEL_RELEASE=6.12.69-android16-6-os4r62-dspids-dscore-full-kmi-4k
IMAGE_SHA256=9b47f40a172ebe2ff0d7c5f6d2834db3fce2535379ea11277fcf010042f2db24
FASTBOOT_BOOT_SHA256=6298fb802d543f1ff2a9f82ccb953b95e44ce6cf6e91d4469735c6bb892b3086
```

新增：

```text
scripts/xiaomi-os4/check-droidspaces-container-cleanup.cmd
scripts/xiaomi-os4/package-validated-anykernel3.sh
.github/workflows/xiaomi-sm8850-os4-validated-full-anykernel3.yml
```

日用打包工作流只做：

1. 下载固定 Run #3 artifact；
2. 校验 boot.img / ABI safety / build metadata；
3. 从已真机验证 boot-v4 精确提取同一个 Image；
4. 再次验证 Image SHA 与 kernel release；
5. 用固定 AnyKernel3 commit 打包，不重新编译；
6. 只替换 active boot 的 kernel payload，保留当前 ramdisk；
7. 确保 cmdline 的 `module_blacklist` 包含 `kernelsu`，防止旧 KernelSU LKM
   与 Built-in BakaSU 同时加载；
8. 不携带 boot/init_boot/vendor_boot/dtbo/vbmeta 等分区镜像；
9. 不自动刷机。

当前最后门禁：

```text
DROIDSPACES_CGROUP_CLEANUP=PENDING
SAFE_TO_FLASH=PENDING_CGROUP_CLEANUP
```

停止并删除测试容器 `test` 后，若
`/sys/fs/cgroup/droidspaces/test` 不再存在，则 Full Extras 运行时生命周期
完成最终闭环，可生成持久化 AnyKernel3 候选。


### DroidSpaces 容器删除清理：PASS（2026-10-30）

在停止并删除测试容器 `test` 后，真机检查：

```text
CLEANUP_RESULT=PASS
/sys/fs/cgroup/droidspaces/test = absent
```

同时 DroidSpaces cgroup 树中不再残留 `test` 目录。

至此实际容器生命周期完整闭环：

```text
CREATE_CONTAINER=PASS
START_CONTAINER=PASS
PID_NAMESPACE_RUNTIME=PASS
IPC_NAMESPACE_RUNTIME=PASS
PIDS_LIMIT_RUNTIME=PASS
STOP_CONTAINER=PASS
DELETE_CONTAINER=PASS
CGROUP_CLEANUP=PASS

DROIDSPACES_CONTAINER_LIFECYCLE=PASS
FULL_EXTRAS_TRUE_DEVICE_VALIDATION=PASS
HARDWARE_REGRESSION=PASS
SAFE_TO_PERSISTENT_CANDIDATE=YES
```

说明：`SAFE_TO_PERSISTENT_CANDIDATE=YES` 表示允许生成已验证 Image 的
持久化 AnyKernel3 候选包，不代表自动刷机。实际持久刷写仍由用户手动执行。


### OS4 Full 持久化 AnyKernel3 候选生成：PASS（2026-10-30）

专用打包 Run：

```text
RUN_ID=41045942378
HEAD_SHA=5dc96f99d2c9cca73c83fead579bcf897d36026d
CONCLUSION=success
```

该工作流没有重新编译内核，而是从已经真机验证的 Full Extras
fastboot artifact 中精确提取同一个 Image，并重新校验：

```text
EXTRACTED_IMAGE_SHA256=9b47f40a172ebe2ff0d7c5f6d2834db3fce2535379ea11277fcf010042f2db24
EXTRACTED_IMAGE_SIZE=42498560
KERNEL_RELEASE=6.12.69-android16-6-os4r62-dspids-dscore-full-kmi-4k
TARGET_BUILD=OS4.0.5.0.XBLCNXM
```

最终 AnyKernel3：

```text
Xiaomi17Pro-pandora-OS4.0.5.0-R62-FULL-AnyKernel3.zip
SHA256=ab38fda26bc4a6023e75ddb00409a5c6d298fc43d318ab15d69766642db2461f
```

GitHub Artifact：

```text
name=PERSISTENT-CANDIDATE-pandora-OS4.0.5.0-R62-FULL-AnyKernel3
artifact_id=12971633767
artifact_zip_digest=sha256:d3e283215f0fdbec4efd7860777417a1567db0d645d53b192dd4af7f1383f0e3
```

最终内容审计通过：

- ZIP 完整性测试 PASS；
- 内部 `Image` SHA 与已真机验证 Image 完全一致；
- 不包含 boot/init_boot/vendor_boot/vendor_kernel_boot/dtbo/vbmeta 分区镜像；
- AnyKernel3 只替换 active boot 的 kernel payload；
- 保留现有 ramdisk；
- 安装脚本会确保 `module_blacklist` 包含 `kernelsu`；
- 自动刷机为 NO，持久化只允许用户手动执行。

生成后已将专用工作流恢复为 `workflow_dispatch` 手动触发，避免后续仓库修改时误打包。

当前状态：

```text
DROIDSPACES_CONTAINER_LIFECYCLE=PASS
FULL_EXTRAS_TRUE_DEVICE_VALIDATION=PASS
HARDWARE_REGRESSION=PASS
PERSISTENT_PACKAGE_AUDIT=PASS
SAFE_TO_PERSISTENT_CANDIDATE=YES
AUTO_FLASH=NO
```
