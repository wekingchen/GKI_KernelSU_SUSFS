# 小米 17 Pro OS4 / 新 OTA 自动基线、实机反馈与自定义内核接力

> 本页以实际 `dev` 工作流为准（核对日期：2026-11-01）。历史 R62/Gen 3 不会因上传新固件自动被覆盖。完整审计、功能列表和未完成事项见 [OS4 端到端审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)。

## 1. 入口与触发

- 固定 OTA 输入：Release tag `pandora-os4-stock-input`，只保留当前固件一个 `*xm.zip`。
- 自动入口：[`xiaomi-sm8850-os4-ota-auto-candidate.yml`](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml)；GitHub Release published/edited、每日补查（北京时间约 04:41）或人工 Run workflow。**只更换 Release 附件不保证实时触发**，每日补查/手动运行用于补救。
- 基线真机结果入口：[`xiaomi-sm8850-os4-ota-test-feedback.yml`](../.github/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml)。
- 日常功能编译入口：[`xiaomi-sm8850-os4-custom.yml`](../.github/workflows/xiaomi-sm8850-os4-custom.yml)。没有第二个专门的“新 OTA 自定义构建”入口。

## 2. 只读采集与来源核验

新 OTA 升级并恢复 Root 后，在 Windows 10/11 下载**仓库最新** `scripts/xiaomi-os4/collect-pandora-stock-input.cmd`：

1. 检查设备 `pandora`、真实系统版本、当前 slot、uname 和 Root。
2. 只读采集当前 slot 的 `boot/init_boot/vendor_boot/dtbo`。
3. 利用手机 Root 的 tar 流，在 Windows 保存已挂载的 vendor_dlkm/vendor/odm_dlkm/system_dlkm 模块；打成 `oem-modules.zip` 并生成 `oem-modules-count.txt`。
4. 生成 README、SHA256 清单与唯一 `*-xm.zip`。任何模块、分区、归档缺失立即停止；不修改手机分区。

上传新 ZIP 前删除旧 ZIP，保持固定 Release 内仅一个。旧 OS4.0.5.0 的历史两镜像 ZIP 仅用于验证原已固定的 boot SHA，**不能当作新 OTA OEM ABI 输入**。Windows 脚本本次修正了原有 PowerShell 截断/重复打包问题，但仍需在下一次真实升级时进行 Windows/Android 端到端复查。

## 3. GitHub 不需要人工介入的 OTA 阶段

1. `inspect`：检查 ZIP、README、boot v4 header、kernel marker、build/slot。与旧固定输入一致时跳过；同 build 但 boot SHA 改变直接停止。
2. `baseline`：新版本在 `6.12.x / android16-6` 且官方源码、Clang `r536225` 等门禁允许时，选择 Android 官方 GKI tag/commit，编译纯 GKI `Image/Module.symvers/final.config`。若只有相同补丁版本，候选不自动等于小米真实构建源码。
3. `archive`：归档 `pandora-os4-ota-candidate-<build>` prerelease，包括 GKI commit、来源 SHA、构建元信息与 `RELEASE-SHA256SUMS.txt`；发布前从 Release 下载回检。其名称不表示可刷。
4. `oem-abi-and-testboot`：对从同 ZIP 采集的 OEM .ko 做 vermagic / vmlinux 符号 CRC 检查。只有 `eligible_for_fastboot_boot=true` 时才生成该 OTA 专属 `UNVERIFIED-FASTBOOT-BOOT-ONLY.img` 和哈希清单；失败只保留报告。

此阶段禁止自动刷机、跨 OTA 使用旧 fixture、生成所谓已稳定功能内核或晋升 LKG。厂商模块静态检查不覆盖所有外部依赖、驱动运行时/设备树/early-boot 行为。

## 4. 只需一次纯 GKI 真机确认与 GitHub 回报

在 PC 下载同一源 Run 的待测 IMG，使用 `fastboot boot <IMG>` **临时启动**，检查：

~~~cmd
adb shell getprop ro.product.device
adb shell getprop ro.mi.os.version.incremental
adb shell getprop sys.boot_completed
adb shell uname -r
adb shell cat /proc/modules
~~~

在 Windows 用 `certutil -hashfile 你的文件.img SHA256` 获取连续的小写 64 位哈希。注意是**待测 IMG 的 SHA**，不是 ZIP 或 Artifact 的 SHA。

GitHub 表单填写：
- `source_run_id`：原 OTA workflow Run URL 最后一段的数字；
- `result`：pass 或 fail；
- `tested_boot_sha256`：实际 `fastboot boot` 的 IMG 哈希；
- `observed_build` 和 `observed_uname`：**只有 pass 必须填写**真实读取结果；机器卡开机无法获取时，fail 可留空；
- pass 必须勾选 Android 已完整启动、关键模块和基础功能正常；fail 可附问题说明。

**pass 的校验与写入**：

- 只接受已完成且成功的同一 OTA 主工作流 Run，以及两个匹配版本的未过期 Artifact；
- 校验固定 Release 中同一 ZIP asset ID、完整 ZIP SHA、GKI commit、Image/Module.symvers 哈希、OEM ABI 报告、被测 boot SHA；
- 用原 stock boot + 对应 Image 独立重打包，要求和被测 IMG **字节完全一致**；再生成 **schema 2 fixture** 并立即从该 fixture 重建相同 boot；
- 创建只包含 **三份**版本记录的 PR：`.github/config/ota-verified/<build>/fixture.json`、`verification.json` 和 `.github/config/ota-development-current.json`；核对 PR diff、目标分支、并发源 SHA 后按仓库保护规则尝试自动合并。

此验证状态为 `HUMAN_ATTESTED_BASELINE_BOOTED`，仍属于纯 GKI 人工启动结果；失败时创建 GitHub Issue，不创建 fixture/开发指针、不改 LKG。源 Actions Artifact 仅在保留期内可取，过期须重建可信来源，不能手工伪造记录。

## 5. 开发指针如何影响以后的自定义编译

`ota-development-current.json` 是**当前开发基线指针**，不是稳定 LKG：

| 真实输入状态 | 原「自定义内核」的自动选择 |
|---|---|
| 固定 Release 仍为历史 OS4.0.5.0，且没有新 OTA 指针 | 原 R62 已验证基线与其自定义流程 |
| 已上传新 OTA 但真机验证尚未完成 | **拒绝执行旧 R62 构建** |
| 新 OTA 的验证记录、fixture、当前 ZIP 和 asset ID 全部匹配 | 在新版本官方 GKI commit 上尝试按勾选项构建 |
| 新 OTA 已验证但某项补丁、编译器、ABI/KMI 失败 | 保留失败日志，不输出伪装为新版本的旧包 |

新路径仍解析本次 BakaSU main、SUSFS 分支以及各组件最新非 prerelease Release / 分支提交的锁定快照；会检查应用补丁、Kconfig、内核 release、`Module.symvers` 核心符号 CRC。**自动跟进上游不等于自动保证未来源码布局兼容**。

**成功编译一次，提供两个产物**（同一个 `pandora-OTA-CUSTOM-<build>-run-<id>` Artifact）：

- `*-UNVERIFIED-FASTBOOT-BOOT-ONLY.img`，供优先 `fastboot boot` 临时测试；
- `*-UNVERIFIED-AnyKernel3.zip`，已标记 `OTA_CUSTOM_UNVERIFIED`，可以直接下载但会**持久更改 boot**；需清楚可能出现不能启动及恢复风险。

两者共享同一份编译 `Image`，还附有 ABI 报告、SHA256 清单与版本元信息。**不需要再回报一次真机结果才能获得 AnyKernel3。** 功能版编译成功不等于运行时通过；用户是否持久安装自行决定，并应备份同 OTA 可启动分区。

## 6. 稳定 LKG 与尚未贯通的关键后续

当前经过真实验证的 LKG 为 OS4.0.5.0 / 6.12.69 / Gen 3，仍单独复现和归档。新 OTA 的开发基线移动不会改动它。

**当前晋升工作流仍固定 R62 Artifact 格式与 ABI 锁，只允许原 R62 自定义构建晋升。** 新 OTA 的 `pandora-OTA-CUSTOM-...` 产物尚不能通过该流程晋升 Gen 4；新 OTA 专属的 LKG 晋升/严格复现/长期归档仍待版本化实现与端到端测试。不要仅凭“新 OTA 自定义编译成功”擅自把其称作新 LKG。

另见 [全部 OS4 功能与流程审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md) 和 [Windows OTA 操作步骤](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)。
