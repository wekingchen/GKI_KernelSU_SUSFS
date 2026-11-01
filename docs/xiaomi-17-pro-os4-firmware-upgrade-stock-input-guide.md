# 小米 17 Pro（pandora）HyperOS 4 OTA 升级后：采集、验证与继续自定义编译

适用：小米 17 Pro，代号 `pandora`，目前 OS4.0.5.0 / 6.12.69 Gen 3 已完成历史真机验证。**只有真正升级到另一个 HyperOS OTA build、并且准备适配对应 GKI 时，才需要重新采集 `xm.zip`。**

本页只讲**你实际需要做什么**；具体 GitHub 自动门禁见 [OTA 工作流说明](xiaomi-17-pro-os4-ota-auto-baseline.md)，全部功能与未完成事项见 [独立审计报告](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。

## 零、已经确定的真机 OTA 操作顺序（以此为首选）

**设备：小米 17 Pro（`pandora`），Android 16 / HyperOS 4，A/B Slot。**

使用者已经明确确认：**每次拿到新的 HyperOS OTA，先从该新版本固件中保留完整、未修补的原始 `init_boot.img`；随后只针对同版本的 `init_boot.img` 修补 Root，待手机正常开机和 Root 通过后，再让本仓库 OTA 采集 App 接管。** 不要求为了采集而撤销 Root。

> 这里的“原始 `init_boot.img`”由使用者在本机离线保存，不从已 Root 的活动分区快照推断，也不要求上传到 GitHub。不要把它误认为 App 采集 ZIP 中的同名文件。

### 一次升级的具体顺序

1. 安装**新 OTA**，正常开机并读取实际 OS build、内核 `uname -r`、设备代号和活动 slot；不要直接拿上一版的任何 `init_boot` / `boot` 去刷。
2. 从**与此次新 OTA 精确匹配**的官方固件或可信原版备份取得未修补 `init_boot.img`，离线备份原文件与 SHA-256、记录 OS build / slot / 文件来源；不要用 Root 后再从活动分区读取的副本覆盖此备份。另行保留本版本的已知可启动恢复镜像及可回退路径。
3. 以该版本原始 `init_boot.img` 为输入，使用当前已经可用的 Root 管理器**只修补 `init_boot`**，按照当前 Slot 和当前 Root 实现对应的安全方法部署；成功进入 Android 后检查 `adb shell su -c id`、正常通信与启动。Root 方案或固件分区布局如变化，应先核对，**不能盲目刷上一版修补镜像**。
4. 在 Root 管理器的「超级用户」中**手动给 OTA 采集助手 `com.wekingchen.pandoraota` 授权**。用户真机首次联调已验证：仅按 App Root 按钮可能收到 `Cannot run program "su": error=13, Permission denied`，手动授权后成功；ADB shell 的 Root 不代表 App 获得授权。
5. 在已验证的 **STABLE-SIGNED** OTA 采集助手中执行「检查 Root」→「采集并生成 ZIP」→「上传当前采集包」→「查询后端处理结果」。App 只读采集活动 Slot 的 `boot`、`init_boot`、`vendor_boot`、`dtbo` 和 OEM `.ko`，上传为 GitHub 私有管理用途的 **Draft Release**。不要将草稿发布成公开 Release。
6. GitHub 先完成身份、Boot、OEM 模块及 KMI/ABI 门禁，再产生**未验证的、不可直接刷写** GKI 候选；等真机临时启动和你实际确认通过后，才按原工作流固化新基线或晋升 LKG。真正跨新 OTA 的全链路尚未经过实际新 OTA 验证。
7. 查看 GitHub 草稿附件应通过 App 的「记录 → 在 GitHub 查看草稿附件」入口；本地 ZIP 在远端附件 ID/大小/SHA-256 与本地 SHA-256 均重新核对后可由用户主动删除。**后端因同版本自定义 Boot 返回 REJECTED，不等于文件未上传。**

### 哪些文件算“原厂”，哪些不能算

| 输入 | 当前实际来源 | 适配用途 / 禁止事项 |
| --- | --- | --- |
| **离线原始 `init_boot.img`** | 使用者从**同一新 OTA**的原始固件或可信原版备份取得 | 保留作版本匹配、恢复和需要时的完整引导分析；**不在 App 的 Root 后采集包里** |
| 活动 `boot.img` | 已 Root 的活动 Slot 只读读取 | **GKI 内核分析主输入**。如果本轮只修补 `init_boot`、没有刷写或改动 `boot`，理论上仍是该 OTA 的 Boot；**但 App 不能独立证明其 OEM 原始性**，以前安装过自定义 Boot 时尤其需要核对 |
| 活动 `init_boot.img` | 先恢复 Root 后只读读取 | **可能已修补，仅作诊断快照**。不能声称原厂、不能当作未修改的恢复镜像，不参与原厂 `init_boot` 一致性认定 |
| 活动 `vendor_boot.img`、`dtbo.img` | 当前 Slot 的运行时快照 | 辅助分析厂商启动参数与硬件兼容性；同样不是 OEM 原版证明 |
| OEM `.ko` | 当前已挂载的厂商模块目录 | **ABI/KMI 兼容性分析主输入**；还需与版本、`vermagic`、符号 CRC 等交叉检验 |

**兼容性说明：** 当前手机 ZIP / `xm.zip` 八文件契约仍包含 `init_boot.img`，以免破坏已有转换/校验链路；但代码现在在采集清单、标准化 README 和审计报告中明确标注 `init_boot_oem_original_verified=NO`、`init_boot_role=DIAGNOSTIC_ONLY_NOT_FACTORY_IMAGE`，并在服务器替换固定 OTA 输入前强制检查。仓库中传统名称 `stock-input` 只是兼容输入槽位，**不是“整个 ZIP 中每个镜像都是出厂原版”的认证**。

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

## 三、Windows 只读采集（备用方案；手机 App 为首选）

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

## 四、Windows 备用流程：手动上传新 xm.zip 及 GitHub 自动检查

固定 Release：[`pandora-os4-stock-input`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-stock-input)。

**正常情况下无需手动管理固定 Release。** 使用手机 App 时，手机只上传到自己的 Draft Release，接收工作流负责按安全门禁验证、暂存、下载校验后再替换固定 `xm.zip`。手动上传仅为 Windows 备用方案，属于高风险变更：务必先完整备份旧附件并确认所有身份/来源检查通过，不能先删掉唯一可恢复的旧 `xm.zip`，也不能用已 Root 的 `init_boot` 冒充 OEM 原厂镜像。

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

确认能进入 Android 后，首选打开 **OTA 助手 0.12.0 → 工作台 → 真机测试反馈**，自动读取设备、OS build、启动完成状态、uname 和模块列表；也可点击「读取本机验证信息」刷新。以下电脑 ADB 命令保留为备用方式：

~~~cmd
adb wait-for-device
adb shell getprop ro.product.device
adb shell getprop ro.mi.os.version.incremental
adb shell getprop sys.boot_completed
adb shell uname -r
adb shell cat /proc/modules
~~~

还应检查 OEM 模块、Wi-Fi、蜂窝网络、蓝牙、基本电话、存储等行为。**这一阶段是纯 GKI 内核，不包含你尚未移植进去的 Built-in BakaSU/SUSFS/NoMount，因此不能以“缺少这些定制功能”直接判纯 GKI 启动失败。** 临时包会在 boot cmdline 中加入 `module_blacklist=kernelsu` 以避免旧 LKM Root 冲突；因此临时会话的 Root 未必可用，不应把“`su` 一定正常”列为纯 GKI 基线 pass 的必要条件。

测完后直接在 App 选择实际测试的候选，确认 IMG 校验值和手动测试结果，补充备注并提交；页面会跟踪原工作流执行结果，不需要网页填表。PAT 需要目标仓库 **Contents 读写 + Actions 读写**。新候选自动预填 SHA-256，旧候选需要手填；无法开机、恢复后才进入 App 时选择「待测启动失败，未能进入系统；现已恢复」，App 会清空待测 build/uname，避免误用恢复后的运行信息。

原 [`提交 OTA 真机测试结果与固化基线`](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml) 网页入口仍作为备用，字段对应如下：

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
5. 原 [`将自定义构建晋升为 LKG`](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) 已统一支持 R62 与新 OTA Run：它会核对真实 Artifact 自动选择版本专属的稳定晋升路线。**新 OTA 仍需首次真机端到端验收**。

## 七、常见问题与故障回退

**Q：以后每次编译都要上传 xm.zip 吗？** 不需要。只有真实 OTA 变更/设备来源变化才需重新采集；同一已验证 build 可以反复勾选新功能编译。

**Q：为什么我上传新 ZIP 后自定义内核反而不编译了？** 新固件尚未完成纯 GKI 真机确认，工作流故意禁止回退旧 R62。先查 OTA 工件/模块 ABI 报告与首次基线测试是否完成。

**Q：为什么 OEM CRC 通过仍可能不启动？** 静态 CRC/vermagic 不涵盖所有厂商依赖、硬件初始化、LSM、Rust Binder 行为、设备树和 OTA 特有代码。只有实际手机运行才能证明。

**Q：功能版成功编译但出现死机怎么办？** 先不要持久刷入；若已安装实验性 AnyKernel3，请使用**当前同一 HyperOS 版本、同设备/slot**的已知可启动 boot 恢复。不要把历史 OS4.0.5.0 Gen 3 或 OS3 Gold 的 boot 直接刷入新 OTA。

**Q：我只想拿最新版 BakaSU Manager 呢？** 现有自定义工作流有独立的 Manager Job，目标版本锁定为本次 BakaSU main 精确提交；找不到官方同提交成功 APK 时会报告失败而不是捏造安装包。root_mode=none 时不执行该 Job。

**Q：新 OTA 成功构建后能立刻标记 Gen 4 LKG 吗？** 不能。当前 LKG 晋升与严格复现/归档仍以 R62 为核心，跨新 OTA 尚需单独版本化适配和测试；请不要把新 OTA 的自定义 Run ID 填进旧晋升入口。

---

**恢复原则**：不跨 HyperOS 版本刷旧 boot，不把 Root 状态备份声称为原厂 pristine boot，不用静态 ABI/CI 结果代替真机启动证据。完整技术限制请看 [OS4 全流程独立审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。

## 八、确认新 OTA 自定义版本稳定后，怎样晋升当前 LKG？

**取得 IMG/AnyKernel3 无需第二次反馈。** 只有当你后来真正用该功能版在手机上启动、持久安装并确认选用的功能正常，才需要主动标记 LKG：在 [将自定义构建晋升为 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml) 输入原自定义 Run ID、勾选三项真实确认，之后 CI 自动完成原版本源码严格重编、OEM ABI/归一化 Image 校验、原版及复现版 Release 资产 SHA 下载回检、稳定指针 PR 合并与发布。首次新 OTA 从 Gen 4 开始，无需另选旧版或新版入口；失败即停。

当前还没有新 OTA 可用于实机端到端验证；该流程的适用条件、错误恢复及证明边界见 [跨 OTA LKG 文档](xiaomi-17-pro-os4-cross-ota-lkg.md)。
