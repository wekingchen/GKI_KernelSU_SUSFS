# 小米 17 Pro（pandora）HyperOS 4 OTA 升级后：采集、验证与继续自定义编译

适用：小米 17 Pro，代号 `pandora`，目前 OS4.0.5.0 / 6.12.69 Gen 3 已完成历史真机验证。**只有真正升级到另一个 HyperOS OTA build、并且准备适配对应 GKI 时，才需要重新采集 `xm.zip`。**

本页只讲**你实际需要做什么**；具体 GitHub 自动门禁见 [OTA 工作流说明](xiaomi-17-pro-os4-ota-auto-baseline.md)，全部功能与未完成事项见 [独立审计报告](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。

## 一、先确认何时需要采集

| 情况 | 是否重新采集 |
|---|---|
| 仍是原来的 OS4.0.5.0.XBLCNXM / R62，只是更新 BakaSU、SUSFS、NoMount 等 | **不需要**；直接用「OS4 / 自定义内核」 |
| 从 OS4.0.5.0 升级到了另一版 HyperOS OTA（内核或厂商模块可能变） | **需要一次**；先采集、确认纯 GKI 基线 |
| 换了 `boot`、系统 build 不一致，或换了实际设备 | 必须重新分析来源，**不能**拿旧 fixture / 旧包直接刷 |
| 上传新 OTA 后暂未完成纯 GKI 临时启动验证 | **自定义构建应阻止旧 R62 回退**；先完成基线验证 |
| 新 OTA 纯 GKI 已验证，之后只是重新勾选功能编译 | **不再采集，也不用重新提交纯 GKI 测试结果** |

## 二、手机准备（仅新 OTA）

1. 通过正常升级方式安装新 OTA，先确认手机能**正常进入 Android 桌面**。
2. 检查设备、当前系统版本、实际内核与活动 slot。不要根据 ZIP 文件名猜测版本。
3. 确认 Root 已恢复（只读访问活动分区和已挂载厂商模块需要 `su`）。
4. 在电脑本地保存与**当前新系统、当前 slot**一致的可启动分区备份及 SHA256。旧 OS4.0.5.0 的 boot 不能当作新 OTA 的安全恢复镜像。

在 Windows platform-tools 目录执行：

~~~cmd
adb devices
adb shell getprop ro.product.device
adb shell getprop ro.mi.os.version.incremental
adb shell getprop ro.boot.slot_suffix
adb shell uname -r
adb shell su -c id
~~~

期望设备为 `pandora`、slot 为 `_a` 或 `_b`、`su -c id` 显示 `uid=0(root)`。如果 Root 未恢复，**不要为了采集脚本去刷入未知的 boot**；先处理 Root 与当前备份。

> 当前稳定 Gen 3 备份来自 OS4.0.5.0 / slot _a 的历史 LKM Root 状态；它是“当时已知可启动”，不能被误称为完全未修改的纯净原厂镜像，更不能跨 OTA 用来恢复。

## 三、Windows 只读采集（需要 adb / tar / PowerShell）

1. 下载本仓库最新版 [`collect-pandora-stock-input.cmd`](../scripts/xiaomi-os4/collect-pandora-stock-input.cmd)。不要使用聊天里复制的旧脚本；此前有一版存在截断 PowerShell 行和重复打包段，现已修复。
2. Windows 10/11 上使用官方 Android platform-tools，确认 `adb.exe` 在 PATH 中，Windows 的 `tar.exe` 和 PowerShell 可用。
3. 用 USB 连接手机，允许 USB 调试；双击或在 CMD 中运行该脚本，授权 Root。
4. 脚本**只读**当前活动 slot 的四张镜像和 live-mounted 厂商/GKI 模块；通过手机 Root 的 `tar` 把模块字节流导出到 PC，本地创建模块 ZIP、模块数量清单、README 和 SHA256。若中途报错，先排查，不要上传残缺 ZIP。

在脚本所在目录：

~~~cmd
where adb
where tar
collect-pandora-stock-input.cmd
~~~

最终应得到形如：

~~~text
pandora-stock-OS4.x.x.x.XXXXXXX-_a-xm.zip
~~~

内部必须包含：

~~~text
boot.img
init_boot.img
vendor_boot.img
dtbo.img
README.txt
SHA256SUMS.txt
oem-modules.zip
oem-modules-count.txt
~~~

`oem-modules.zip` 是从已挂载的 `/vendor_dlkm/lib/modules`、`/vendor/lib/modules`、`/odm_dlkm/lib/modules`、`/system_dlkm/lib/modules` 中实际存在的目录读取；某目录不存在可跳过，但所有读取失败、无任何 .ko、数量/大小异常都必须停止。采集期间**不进行** `fastboot flash`、`erase`、`set_active` 或其它分区修改。

脚本需要手机/Windows 上的 tar；部分旧设备或特殊文件系统可能无法完整打包。如出现错误，请保存报错、不要自行删掉模块清单后强行上传。**该修复尚待下一次真实新 OTA 的 Windows 实机采集验证。**

## 四、上传新 xm.zip 及 GitHub 自动检查

固定 Release：[`pandora-os4-stock-input`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-stock-input)。

进入该 Release，删除上一版旧 `*xm.zip`，上传刚采集的**一个**完整新 `*xm.zip` 并保存 Release；始终保持该 Release 中只有一个匹配文件。不要把旧版和新版 ZIP 同时留在同一个 Release。

GitHub 会通过 [`OTA 自动识别与非刷机 GKI 基线候选`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml) 的 Release 事件/每日补查自动进行：

1. 身份审计：device、build、slot、boot v4、内嵌内核版本；同 build 不同 boot 哈希会阻止。
2. 在支持的 GKI/KMI 与工具链范围内，拉取官方源 tag/commit，构建纯 GKI `Image/Module.symvers`。
3. 发布**研究性、不可直接刷写**的 GKI 候选 prerelease。
4. 读取同一个 `xm.zip` 里的 OEM 模块，核验 `vermagic` 与 `vmlinux` 导入符号 CRC；**只有全绿才生成待测 IMG**。

GitHub 仅更换附件不保证立即触发 `edited`，可等待每日自动检查；若想立即进行，可手动在该 OTA 工作流选择 `dev` → Run workflow。若显示失败，先看工作流摘要/ABI 报告，不要下载旧版 IMG 误测。

若官方 KMI/Clang 改变、OEM 模块不完整或静态 CRC 不通过，**本轮可能只有诊断报告而没有待测 IMG**；这不表示可以手工绕过门禁。

## 五、纯 GKI 临时启动与一次性验证结果上报

在 OTA workflow 的成功 Run 中，找到类似 `pandora-OTA-OEM-ABI-TESTBOOT-<build>-<run_id>` 的 Artifact，下载**同一次** Run 对应的：

~~~text
pandora-<build>-UNVERIFIED-FASTBOOT-BOOT-ONLY.img
TESTBOOT-SHA256SUMS.txt
ota-abi-report.json
~~~

Windows CMD 先校验被测 IMG 的 SHA：

~~~cmd
certutil -hashfile "你的待测文件.img" SHA256
~~~

然后进入 bootloader 并**仅临时启动**：

~~~cmd
adb reboot bootloader
fastboot devices
fastboot boot "你的待测文件.img"
~~~

确认能进入 Android 后，重新连接 adb：

~~~cmd
adb wait-for-device
adb shell getprop ro.product.device
adb shell getprop ro.mi.os.version.incremental
adb shell getprop sys.boot_completed
adb shell uname -r
adb shell cat /proc/modules
~~~

还应检查 OEM 模块、Wi-Fi、蜂窝网络、蓝牙、基本电话、存储等行为。**这一阶段是纯 GKI 内核，不包含你尚未移植进去的 Built-in BakaSU/SUSFS/NoMount，因此不能以“缺少这些定制功能”直接判纯 GKI 启动失败。** 临时包会在 boot cmdline 中加入 `module_blacklist=kernelsu` 以避免旧 LKM Root 冲突；因此临时会话的 Root 未必可用，不应把“`su` 一定正常”列为纯 GKI 基线 pass 的必要条件。

之后进入 [`提交 OTA 真机测试结果与固化基线`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml)：

| 字段 | 成功 `pass` | 失败 `fail` |
|---|---|---|
| `source_run_id` | 刚才 OTA 候选主 Run ID | 同一主 Run ID |
| `tested_boot_sha256` | 实测 IMG 小写 64 位 SHA | 同样要填写 IMG SHA |
| `observed_build` / `observed_uname` | 填 Android 实际读取结果 | 无法开机读取时**留空** |
| 两个启动/模块确认勾选项 | 真正检查通过才勾选 | 不勾选 |
| `note` | 可写补充 | 建议写黑屏、重启、卡 Logo、模块故障等现象 |

`pass` 后 GitHub 独立验证原 ZIP、候选 Run、IMG 哈希、OEM 静态门禁和 fixture 字节复现，并自动 PR 固化：

~~~text
.github/config/ota-verified/<新build>/fixture.json
.github/config/ota-verified/<新build>/verification.json
.github/config/ota-development-current.json
~~~

这些代表**新 OTA 的纯 GKI 基线已由你人工确认并核对来源**，不代表功能版已稳定；`fail` 只创建 Issue，不能更新开发指针或 LKG。GitHub Artifact 若已过期，需要重新取得可信候选。

## 六、下一次自定义内核：默认新 OTA，不再重复反馈

完成上述一次纯 GKI 基线 pass、GitHub 自动 PR 合并后，以后直接进入原有 [`小米17 Pro OS4 / 自定义内核`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-custom.yml)：

1. 选择 BakaSU + SUSFS（默认）或 BakaSU-only、none，以及 SUSFS 扩展、NoMount、DroidSpaces、NTSync、BBG、Re-Kernel、网络增强、CVE 选项。
2. GitHub 读取当前输入 Release 和已验证开发指针，自动选择对应 GKI commit。每轮锁定本次最新稳定上游提交，尝试移植补丁和编译。**新固件未通过确认时，不会偷偷回退 R62**。
3. 新 OTA 编译及 ABI/KMI 全绿时，在同一 Artifact 同时下载 `*-UNVERIFIED-FASTBOOT-BOOT-ONLY.img` 与 `*-UNVERIFIED-AnyKernel3.zip`，以及 SHA256、ABI 结果和构建元信息。
4. 两种形式使用相同 Image。**不用再提交另一轮真机结果才能拿到 AnyKernel3**。更安全的使用方式仍是先 `fastboot boot` 临时测试功能版，再决定是否运行会持久替换活动 boot 内核的 AnyKernel3。
5. 目前旧 R62 的 [`晋升为 LKG`](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) 尚不支持直接输入新 OTA 的 Artifact。**新版本日常自定义编译可用不代表新版本 LKG 晋升流程已贯通**。

## 七、常见问题与故障回退

**Q：以后每次编译都要上传 xm.zip 吗？** 不需要。只有真实 OTA 变更/设备来源变化才需重新采集；同一已验证 build 可以反复勾选新功能编译。

**Q：为什么我上传新 ZIP 后自定义内核反而不编译了？** 新固件尚未完成纯 GKI 真机确认，工作流故意禁止回退旧 R62。先查 OTA 工件/模块 ABI 报告与首次基线测试是否完成。

**Q：为什么 OEM CRC 通过仍可能不启动？** 静态 CRC/vermagic 不涵盖所有厂商依赖、硬件初始化、LSM、Rust Binder 行为、设备树和 OTA 特有代码。只有实际手机运行才能证明。

**Q：功能版成功编译但出现死机怎么办？** 先不要持久刷入；若已安装实验性 AnyKernel3，请使用**当前同一 HyperOS 版本、同设备/slot**的已知可启动 boot 恢复。不要把历史 OS4.0.5.0 Gen 3 或 OS3 Gold 的 boot 直接刷入新 OTA。

**Q：我只想拿最新版 BakaSU Manager 呢？** 现有自定义工作流有独立的 Manager Job，目标版本锁定为本次 BakaSU main 精确提交；找不到官方同提交成功 APK 时会报告失败而不是捏造安装包。root_mode=none 时不执行该 Job。

**Q：新 OTA 成功构建后能立刻标记 Gen 4 LKG 吗？** 不能。当前 LKG 晋升与严格复现/归档仍以 R62 为核心，跨新 OTA 尚需单独版本化适配和测试；请不要把新 OTA 的自定义 Run ID 填进旧晋升入口。

---

**恢复原则**：不跨 HyperOS 版本刷旧 boot，不把 Root 状态备份声称为原厂 pristine boot，不用静态 ABI/CI 结果代替真机启动证据。完整技术限制请看 [OS4 全流程独立审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。
