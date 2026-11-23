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


## 2026-11-23：标准自定义工作流 #37 真机临时启动通过

本次不再使用一次性实验 workflow，而是直接验证已经恢复到 `dev` 的标准：

`小米17 Pro OS4 / 自定义内核`

Run：

- run number：`#37`
- run id：`45047763911`
- artifact id：`14764239826`
- artifact：`pandora-OTA-COMPAT-NONFLASH-OS4.0.6.0.XBLCNXM-run-45047763911`
- Image SHA-256：`3daba0524738ab872ebf75653f25754433c36a624eb8002198440a4cb1cb1dc0`
- Module.symvers SHA-256：`e1058b486b6ecc26b0f7a0df49845868843fd63941153726a9d2d2f7d4650b2e`
- FASTBOOT-BOOT-ONLY SHA-256：`230a16fa271c3ccbaa14309adbd2905ae04430032a9f7b9d0853478aa7751d27`
- boot size：`44,404,736` bytes
- boot-v4 audit：`PASS`
- ABI preservation：18,798 baseline exports preserved，86 new exports，0 missing / CRC-changed

用户通过 `fastboot boot` 进入 Android 后，手工 CMD 直接观察到：

- `sys.boot_completed=1`
- `uname -r=6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`
- `su -c id` 返回 `uid=0(root)`，SELinux context `u:r:ksu:s0`
- Binder `impl=c`
- Binder `active_impl=c`
- active LSM 含 `baseband_guard`
- `/proc/modules` 中无 `rust_binder`
- `/proc/modules` 中无 `kernelsu` LKM
- `node_cache` / `zram` / `zsmalloc` 均正常加载

因此，**标准 OS4 自定义编译 -> nonflash boot-v4 打包 -> 真机 fastboot boot -> Android 完整启动** 这条路线已闭环验证。

### 与上一轮全功能候选的组件差异

#37 解析的组件：

- BakaSU：`2734e0bc155759955880f5fb99be640fc5b92156`
- SUSFS：`9b0b13f069673b9b07b713a5c66977de4d62b175`
- NoMount：`dcd77d03e9912f397a586d7da81694d1628f170e`
- DroidSpaces：`cdadb9eb5d0f86aacffff60776333e6f6b73a30a`
- NTSync：`dc0f76bedd790b7738e5695509297ee71ca4a2c2`
- BBG：`d4f7302190b83246266598eb5d59c6b36fa22bdc`
- Re-Kernel：`e67cd94c524c27503cb340f8bbab594eca95dbef`

相较此前真机全功能审计，主要变化是 BakaSU 提交更新；SUSFS、NoMount、DroidSpaces、NTSync、BBG、Re-Kernel 均保持相同锁定提交。此次 `uid=0` 结果因此也为新 BakaSU 集成提供了基本真机运行证据。

### 仍然没有解除的边界

- formal OEM ABI gate：`BLOCKED`
- 71 个 OEM Rust Binder unresolved imports：仍未解决
- 27 个 zsmalloc provider ambiguity：仍未解决
- AnyKernel3：不生成
- 持久刷写：禁止
- LKG 晋升：禁止

本轮结论是：**标准 OS4 自定义编译和临时启动路线已经恢复并经真机验证；不是正式持久安装路线已经恢复。**


## 2026-11-23：exact run37 AnyKernel3 首次持久重启通过

用户安装 `Xiaomi17Pro-pandora-OS4.0.6.0-run37-PERSISTENT-CANDIDATE-AnyKernel3.zip` 后直接重启，不再使用 `fastboot boot`。首次持久启动的手工 CMD 证据：

- `sys.boot_completed=1`
- active slot：`_b`
- `uname -r=6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`
- Root：`uid=0(root)`，SELinux context `u:r:ksu:s0`
- `/proc/cmdline` 含 `module_blacklist=kernelsu`
- `/proc/cmdline` 含 `pandora_rust_binder_eexist=1`
- Binder `impl=c`
- Binder `active_impl=c`
- active LSM 含 `baseband_guard`
- `rust_binder` 未加载
- KernelSU LKM 未加载
- `node_cache` / `zram` / `zsmalloc` 正常加载

判定：**FIRST_TRUE_DEVICE_PERSISTENT_REBOOT=PASS**。

此时仍不晋升 LKG；还需要一次普通重启，在不重新刷入、不运行 `fastboot boot` 的前提下重复确认持久性。第二次重启通过后，才把 `actual_persistent_install_verified` 设为 true。
