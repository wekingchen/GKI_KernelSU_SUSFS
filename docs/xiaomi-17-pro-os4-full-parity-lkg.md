# 小米 17 Pro OS4：当前 LKG、可选功能与上游策略

核对日期：2026-11-02。当前入口见 [文档索引](pandora-os4-guide.md)。LKG 由用户明确标记真实稳定版本；自定义构建追新与 LKG 固定复现是两种不同目标。

## 当前身份：Gen 4，而非 Gen 3

权威来源：[`.github/config/pandora-os4-full-parity-lkg.env`](../.github/config/pandora-os4-full-parity-lkg.env)。下表仅为核对日快照，后续晋升以指针为准。

| 字段 | 快照 |
| --- | --- |
| 设备 / 固件 | pandora / OS4.0.5.0.XBLCNXM |
| 代次 | `LKG_PROMOTION_GENERATION=4` |
| 内核 release / KMI | `6.12.69-android16-6-os4r62-custom-4k` / android16-6 |
| 用户确认的来源 Run | 41265596768 |
| 晋升 Run | 41266571030，2026-11-01 02:47:19 UTC |
| 后续复现 / 归档 Run | 41266617336 / 41266968764，均成功 |
| 长期归档 | [pandora-os4-lkg-gen4](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen4) |

用户空间版本应按手机或配置读取，不能从 `android16-6` KMI 名字反推。最早 Full Parity 的长内核名及 Gen 1/2/3 均是历史身份，不再代表当前指针。来源包文件名中的 `UNVERIFIED` 是初次构建时的原名，晋升身份以精确 SHA、用户确认和指针记录为准。

## 日常自定义入口与菜单

使用 [小米17 Pro OS4 / 自定义内核](../.github/workflows/xiaomi-sm8850-os4-custom.yml)，选择 `dev`。当前菜单：

| 选项 | 含义 |
| --- | --- |
| `root_mode` | bakasu-susfs（默认）、bakasu、none |
| `susfs_extra_features` | SUSFS 扩展 SPOOF / HIDE / OPEN_REDIRECT / SUS_MAP |
| `use_nomount` | NoMount VFS 注入 |
| `droidspaces` | on/off；完整 namespace、Macvlan、IPv6 NAT 及安全 PIDs 方案 |
| `droidspaces_ntsync` | NTSync，可独立于 DroidSpaces 开启 |
| `use_bbg` | Baseband Guard |
| `use_rekernel` | Re-Kernel Generic Netlink 集成 |
| `use_networking` | BBR、IPSet、FQ/FQ_CODEL/CAKE、WireGuard、CIFS 等 |
| `use_cve` | 已定义 CVE 修复链审计和必要回补 |

依赖由脚本统一校验，元数据记录实际生效值。ZRAM/LZ4K/LZ4KD 自定义后端仍未加入 OS4 菜单；手机已有厂商 zram 模块不等于该新功能已完成。菜单默认值不是用户必须采用的固定组合。

## 每次编译追新，一次运行内固定快照

[`resolve-stable-upstreams.sh`](../scripts/xiaomi-os4/resolve-stable-upstreams.sh) 在本轮开始解析并锁定 ref kind / ref / commit：

| 组件 | 日常自定义来源 |
| --- | --- |
| BakaSU | 按用户要求跟 main HEAD |
| SUSFS | gki-android16-6.12 分支 HEAD |
| NoMount、DroidSpaces、BBG、Re-Kernel | 最新非 draft / 非 prerelease 正式 Release |
| NTSync 补丁 | Goldzxcbug/Droidspaces_Kernel_patch 的 main |
| 网络增强 / CVE | 本轮 GKI 源码与必要修补，不是独立第三方版本 resolver |

本轮内核、缓存键、产物元数据与 Manager 使用同一份快照，避免构建中途变成混合版本。启用组件 SHA 与 LKG 不同就属于新候选，不会为了套用稳定名义回退旧组件；补丁、Kconfig、ABI/KMI 不通过则真实失败。

BakaSU Manager 只接受官方成功 Manager CI 的同一 head SHA，KSU_VERSION 也要匹配；普通与 Spoofed APK 分开保留。上游 APK 未准备好时不回退其它提交；root_mode=none 跳过 Manager。Manager Job 与内核 Job 的完成状态应分别核对。

## 已有真机结论和不能移除的约束

历史 Full Parity 及用户确认晋升的 R62 记录包括：Built-in Root、无旧 KernelSU LKM 冲突、DroidSpaces 自检全绿、PIDs 控制器、BBG active LSM、Re-Kernel 11.7 Generic Netlink、NTSync、BBR 等。详细 PASS 字段保存在当前 LKG 配置；不能把任意新提交编译成功直接视为这些运行时结论仍成立。

1. R62 的 PIDs 采用 KMI-preserving 方案：保留 CONFIG_CGROUP_PIDS=n，复用原 net_prio subsystem slot，并在运行时暴露 pids。不能直接改成普通 CONFIG_CGROUP_PIDS=y 而忽略 ABI。
2. BBG 必须纳入 MAX_LSM_COUNT。R62 原计数会漏掉后接入的 baseband_guard，导致 LSM 排序截断。真机 active 列表应包含 `capability,landlock,safesetid,selinux,bpf,baseband_guard`；编译符号存在不等于 LSM 已激活。
3. Re-Kernel 使用 Generic Netlink；旧 legacy netlink 路线不作为当前方案。
4. NoMount 是用户选择的 VFS 路线，不是 Magic Mount；模块自检文案与实际运行需分别核验。

## 新 OTA 与稳定晋升

新 OTA 先[使用手机采集并提交](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)，电脑临时启动候选后在 App 反馈。纯 GKI 通过只更新版本 fixture 和开发指针，不移动 LKG。新版本未确认时自定义构建应停止，不能偷偷回退旧 R62。

功能版编译成功后，同次提供使用同一 Image 的待测 IMG 与实验性 AnyKernel3；取得 ZIP 不需要再次提交反馈。真正持久安装、稳定使用并确认本次选用功能正常后，才使用[统一晋升入口](xiaomi-17-pro-os4-cross-ota-lkg.md)，由来源自动选择 R62 或新 OTA 路线。

- R62：按锁定配置复现，经自动接力归档；当前 Gen 4 已有实际成功记录。
- 新 OTA：按原始 Run Git SHA 和原组件重编，严格校验配置、symvers、归一化 Image；完整草稿下载回检后才晋升指针及公开 Release。真实新 OTA 仍待端到端验收。
- 代次取已有最高代次 + 1；核对日最高为 4，若无其它晋升，首次新 OTA 应从 5 开始，不能硬编码回到 Gen 4。

长期恢复请优先使用[已归档 Release](xiaomi-17-pro-os4-lkg-release-archive.md)。2026-10-29 的 OS4 / slot A / LKM Root 可启动备份只能作为该时刻、同版本设备的恢复点，不能称为未修改 OEM 原版或跨 OTA 使用。
