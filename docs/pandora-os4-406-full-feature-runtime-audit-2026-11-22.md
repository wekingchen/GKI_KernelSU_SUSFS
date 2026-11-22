# Xiaomi 17 Pro / pandora OS4.0.6 全功能候选运行时审计（2026-11-22）

## 证据来源

- 用户上传文件：`pandora-406-full-feature-runtime-v2-32272.txt`
- SHA-256：`4e7b74c6ab4919033c9ad5a96f041a524b8f8d4f7d03f4a27ac22b905276c12a`
- 采集方式：Windows CMD -> ADB stdin -> Android Root POSIX shell
- 采集完整性：出现 `REMOTE_COLLECTOR_FINISHED=YES`
- Root：`uid=0(root)`，SELinux context `u:r:ksu:s0`
- 设备身份：`pandora / OS4.0.6.0.XBLCNXM / slot _b`
- 运行内核：`6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`
- `sys.boot_completed=1`

## Binder / Root

| 项目 | 直接观察 | 判定 |
|---|---|---|
| Binder requested impl | `c` | PASS |
| Binder active impl | `c` | PASS |
| rust_binder sysfs | ABSENT | PASS |
| rust_binder /proc/modules | ABSENT | PASS |
| Activity Binder service | found | PASS |
| Package Binder service | found | PASS |
| KernelSU LKM blacklist | `module_blacklist=kernelsu` | PRESENT |
| EEXIST experiment parameter | `pandora_rust_binder_eexist=1` | PRESENT |
| `modules_disabled` | 0 | PASS |

本次证明运行时 C Binder active，rust_binder 不存在，Android 核心 Binder 服务可用。专属 shim kernel-log marker 未观察到，故不把 marker 写成 PASS；本采集包也没有 host 端启动前 Image SHA 输出，不能对当前运行内核与某个 Image 文件做密码学绑定。

## 已观察到的功能接口

- Active LSM：`capability,landlock,safesetid,selinux,bpf,baseband_guard`。这证明 BBG 名称在活动 LSM 列表中，不等价于 BBG 所有策略/阻断行为已做破坏性实测。
- NTSync：`CONFIG_NTSYNC=y`，`/dev/ntsync` 与 `/sys/class/misc/ntsync` 均存在；未执行 ioctl 测试。
- BakaSU：`ksud 4.2.0-rc3-91-g7b65bde0`；SUSFS `v2.4.0`，GKI variant；9 项 enabled feature 查询成功。这是用户态版本/接口查询，不替代每项隐藏、挂载行为测试。
- NoMount：CLI `23 (1)`，模块 `v2.3.1 (785)`；仅确认版本与模块元数据。
- Re-Kernel：`rekernel_genl_family`、`rekernel_genl_get_version`、`rekernel_netlink_start`、`start_rekernel` 四个符号存在；未发起 Generic Netlink 请求。
- Networking config：MACVLAN、BBR、CAKE、WireGuard、IP_SET、CIFS 均为 `y`；这属于配置证据。

## DroidSpaces / PIDs 的边界

- Android 包 `com.droidspaces.app` 已安装。
- `/sys/fs/cgroup/cgroup.controllers` 返回 `pids`。
- `/sys/fs/cgroup/cgroup.subtree_control` 为空。
- 当前没有 `/sys/fs/cgroup/droidspaces/*` live container。
- 因此本轮确认 PIDs controller 在当前 cgroup 根控制器列表中可见；**尚未确认 DroidSpaces 实际容器的 `pids.max`、`pids.current`、PID/IPC namespace 隔离**。这项必须等真实容器运行时再验收。
- `CONFIG_CGROUP_PIDS=n` 与当前采用的 net_prio KMI slot 复用设计一致，不能单凭这一项判失败。

## Vendor memory stack

当前 `/proc/modules` 可见：

- node_cache
- zram
- zsmalloc

三项已加载模块 sysfs GNU Note SHA-256 与此前锁定的 vendor stock Note 完全匹配（3/3）。这是模块 GNU Note 身份指纹，不是完整内存 ELF SHA、加载路径或 AVB 信任链证明。vendor/system 两套 zsmalloc 来源仍严格区分。

## 综合判定

- 全功能候选 fastboot-boot 会话：**BOOT_COMPLETED**
- C Binder active + rust_binder absent：**DIRECT RUNTIME PASS**
- BBG active LSM 名称：**PRESENT**
- NTSync 设备节点：**PRESENT**
- BakaSU/SUSFS、NoMount 版本接口：**QUERY PASS**
- Re-Kernel 符号：**PRESENT**
- PIDs controller：**ROOT CONTROLLER PRESENT；DROIDSPACES LIVE CONTAINER NOT EXERCISED**
- Vendor memory stack Note：**3/3 vendor match**
- Full feature behavior audit：**PARTIAL；仍有动态功能项未测**
- Formal OEM ABI gate：**BLOCKED**
- Flash / persistent install / AnyKernel3 / LKG promotion：**FORBIDDEN**

## 对标准自定义编译工作流的恢复

本轮全功能构建与临时启动已成功，但不能把它等同于正式 OEM ABI 门禁通过。

本分支将实验路线接回标准 `Xiaomi 17 Pro OS4 / 自定义内核` 工作流时，必须继续保留以下约束：

1. EEXIST shim 只允许 OS4.0.6.0.XBLCNXM + exact GKI r74 commit + 固定 patch SHA。
2. 只接受同版本、已验证的 compatibility record/fixture 和当前 stock Release asset ID。
3. 新 OTA 构建仍执行 baseline Module.symvers 与 feature Module.symvers core-export CRC 对比。
4. 兼容模式仅产出 `FASTBOOT-BOOT-ONLY`；镜像增长只在 nonflash boot-v4 repack 中显式允许。
5. 兼容模式不生成 AnyKernel3，不执行持久刷写，不进入 cross-OTA LKG source capture，也不能晋升 LKG。
6. 原 OS4.0.5 R62 LKG、其 fixture 和 legacy 构建路径不被覆盖。

本次目的只是恢复 OS4.0.6 版本化、受门禁保护的自定义**编译**路线；不是宣布 OEM ABI 问题已经解决。


## Windows / ADB 操作约定（长期）

- 用户侧执行入口统一使用 Windows 原生 CMD + `adb.exe`。
- 不再要求用户运行 PowerShell 脚本，也不再把复杂 Android shell 语句层层拼接进 `adb shell su -c` 参数。
- 需要执行多条 Android shell 检查时，由 CMD 将完整 POSIX shell 脚本通过 ADB stdin 传给单次 Root shell；用户只需运行一个 `.cmd`。
- 交付前必须先检查 CMD 编码/换行、远端 Shell 语法（dash / BusyBox ash）、文件完整性和只读边界；静态检查不得冒称真机端到端通过。
- 任何会修改设备状态的操作必须单独标明，不能混入只读采集器。
