# OS4 自定义编译 #28 · SUSFS 优先 UID 过滤器条件编译修复

## 触发原因

- 失败运行：[OS4 自定义 #28 / 42672470251](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/42672470251)，源码基线 `ef0169001a3b981a976fe79c0a8660cde91657a5`。
- 自定义 R62（与 Gen 4 相同的功能选择，但按约定追踪最新版稳定上游）取到 SUSFS `gki-android16-6.12 @ 395a8c0c88d348e9fe7c14f66a456fde4653287c`，旧 LKG 为 `15890c612d4a2ff37557a0aafe4189451859771b`。
- 新 SUSFS 已将优先 UID 过滤器实现放入 `#ifdef CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER`，但 `susfs_switch_to_ksu_domain()`、`susfs_restore_creds()` 仍无条件定义。该可选功能未选中，调用点被编译掉，却留下两个未使用的静态函数；Clang `-Werror,-Wunused-function` 使 `fs/susfs.o` 编译失败。
- **不是**工具链、缓存、OEM ABI/KMI 或 fastboot boot 失败：#28 尚未走到 ABI/打包阶段；Manager 分支独立成功。

## 修复策略

仅在 Pandora OS4 的隔离源码构建中，`scripts/xiaomi-os4/susfs-priority-uid-compat.py` 检测新版 SUSFS 的确切条件编译/函数调用结构后，将这两个私有辅助函数定义用 **相同的** `CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER` 包裹。没有启用新功能时不生成这两个静态函数；启用时函数与原调用代码完全保留。不删除函数、不改动 SELinux 凭据逻辑、不改 Kconfig 功能选择、不关闭 `-Werror`。

旧版本没有此条件块时原样跳过；如果上游未来改变函数、调用位置或条件编译结构则**拒绝静默打补丁**，应重新审查。仍按每次 Run 锁定的最新稳定来源构建，**不把 SUSFS 回退或锁死为旧提交**。

## 已取得的证据

- [锁定上游源码诊断](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/42866434854)：确认旧版无过滤器条件编译、新版在第 1378 行引入条件块且两个调用处位于其内。
- [同一真实源码的兼容验证](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/42867690188)：6 个兼容单元测试通过；旧版返回 `UNCHANGED_OLD_LAYOUT`；新版返回 `WRAPPED_OPTIONAL_PRIORITY_UID_HELPERS`；重复执行为 `ALREADY_GUARDED`。
- 新的 #29 自定义全量验证：[Run 42867992873](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/42867992873)。结果以运行记录为准；编译通过前不标记为可刷机。

## 安全边界

- 只影响新一次构建的独立源码目录，不修改上游 Google GKI、SUSFS / BakaSU 仓库、已有 Gen 4 LKG 指针、既有 Release 或固定 OTA 输入。
- 完整 Image、Module.symvers、ABI/KMI、打包和真机开机各自需要独立证据；编译成功并不等于真机安全，未经验证的新组合仍须标记 `CUSTOM-UNVERIFIED`。
