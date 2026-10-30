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

正在执行：**OS4 / R62 DroidSpaces PIDs 专项 ABI 分析**。

只有 `CONFIG_CGROUP_PIDS=y` 的 ABI 风险被量化并通过门禁后，才进入下一张临时启动镜像。


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
