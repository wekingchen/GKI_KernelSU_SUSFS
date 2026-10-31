# 小米 17 Pro OS4：新 OTA 自动预检与不可刷写 GKI 基线候选

## 设计边界

**当前已验证 OS4.0.5.0.XBLCNXM / Gen 3 不修改、不重新打包、不重新晋升。**

上游组件更新仍由常规 OS4 自定义编译动态选取最新稳定版本，与 OTA 流程无关。

只有系统真正 OTA 升级后，才使用 `collect-pandora-stock-input.cmd` 从已经正常开机的新系统只读采集当前活动 slot 的 boot、init_boot、vendor_boot、dtbo，生成新的 `*-xm.zip`。仍由用户在固定 `pandora-os4-stock-input` Release **只保留一个**新 ZIP。

新的 `xiaomi-sm8850-os4-ota-auto-candidate.yml` 会在这个 Release 发布/编辑时自动运行；考虑到 GitHub 仅替换 Release 附件未必可靠产生 edited 事件，另外每天补查一次。也支持手动重试作为故障补救。日常无需再人工执行只读检查。

## 自动化实际做到什么

1. 固定 Release 只允许一个 `*xm.zip`，拒绝多文件、异常大小、加密 ZIP、错误设备或 boot 格式。
2. 校验 README 中的设备、slot、build、uname，并检查 boot-v4 header、kernel SHA256、内嵌 Linux version（若存在）。
3. 对照当前 `.github/config/pandora-os4-stock-input.env`。**同一个 build 且 boot 哈希一致时直接结束，不重新编译**；同 build 但 boot 改变时拒绝自动推进。
4. 如果是新 build 且仍在 `6.12.x / android16-6`，自动从 Android 官方公开 GKI 发布目录选取**相同内核补丁版本**的源码候选，记录 tag、完整 git commit 和发布目录 SHA256。
5. 对该 commit 做真正的 git fetch SHA 验证、Makefile 版本、KMI generation、Clang 版本核验。在工具链版本仍兼容已验证的 `r536225` 时，才自动编译**原生纯 GKI** 的 Image / Module.symvers / final.config。构建日志仅在失败时输出错误结尾。
6. 完成后把 `UNVERIFIED / NO FLASH` 产物保存为独立 OTA 候选 prerelease，格式 `pandora-os4-ota-candidate-<新固件版本>`，未来每天重复检查时按版本和输入 SHA256 去重。与 LKG Release 完全分开。

**注意**：只凭 `uname` 的 6.12.xx 并不能保证候选官方 GKI 提交与小米厂商真实的编译版本一致。如果官方构建 ID 无法精确匹配，流程会选择同补丁版本的最新正式 GKI 作为**研究候选**，明确输出 `SAME_PATCH_LATEST_OFFICIAL_GKI_CANDIDATE`，绝不声称 OEM 匹配。

## 自动化停止的位置

当前阶段只自动建立 **GKI source/build candidate**。它不是手机可启动基线，更不是已验证的功能内核。自动化明确禁止：

- 自动复用 Gen 3 的 boot fixture、ABI 锁和 Image 哈希；
- 自动构造用于刷机的 fastboot boot / AnyKernel3；
- 自动写入分区、切换 slot、临时启动或修改手机；
- 自动晋升 LKG 或发布为稳定内核 Release。

下一阶段必须基于 OTA 对应的 OEM 分区与厂商模块，验证真实 ABI/KMI 和 toolchain、生成新的**待测** boot-v4 fixture/临时启动包，用户手动 `fastboot boot` 真机成功后才允许固化新版本的已验证 fixture。由于设备源码/编译源并非总可由 Android 官方 GKI 唯一推断，这一步不可无条件自动晋升。

## 失败保护

- 更换 GKI/KMI 家族、没有官方精确内核补丁版本、工具链更新、stock 文件身份漂移：停止 GKI 编译，并保留报告供新版本适配。
- 纯 GKI 编译失败：不发布候选 Release；Gen 3 不受影响。
- GitHub Release 上已归档同名版本但输入 SHA256 改变：停止，人工核对，不覆盖旧记录。
- 历史 `pandora-os4-lkg-gen3` Release 和所有已验证恢复包都不会被这条自动化更新。

## 当前状态与验证

当前 Release 中的 `xm.zip` 对应 `OS4.0.5.0.XBLCNXM`，历史包只包含 `boot_OS4.0.5.0.XBLCNXM.img` 与 `init_boot_OS4.0.5.0.XBLCNXM.img`，不包含新版 `README.txt`。因此只允许其 **boot SHA256 与当前固定 stock boot 完全一致** 时视为 `SAME_PINNED_BUILD`、跳过 GKI 候选编译。任何新 OTA 缺少 README 必须失败，不能从 ZIP 文件名推测系统版本。**没有新 OTA 输入时，不应为了实验人为晋升 Gen 4 或制造虚假已验证的 OTA 基线。**

源代码：

- `scripts/xiaomi-os4/inspect-ota-stock-input.py`
- `scripts/xiaomi-os4/resolve-ota-gki-candidate.py`
- `scripts/xiaomi-os4/build-ota-gki-baseline-candidate.sh`
- `.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml`

Android 官方 GKI 6.12 版本索引：<https://source.android.com/docs/core/architecture/kernel/gki-android16-6_12-release-builds>

## 新增：新 OTA 的 OEM ABI/KMI → 待测临时 boot 自动接力

**不改变旧版 Gen 3，不自动刷机，不自动晋升 LKG。**

1. `collect-pandora-stock-input.cmd` 在新 OTA 上仍以只读方式保存 boot、init_boot、vendor_boot、dtbo，但现在还会从系统当前挂载的 `/vendor_dlkm/lib/modules`、`/vendor/lib/modules`、`/odm_dlkm/lib/modules`、`/system_dlkm/lib/modules` 读取实际内核模块到电脑，汇总成 `oem-modules.zip` 并加入新 `xm.zip`。若采集失败，就停止而不是生成缺证据的固件包。请使用新版 CMD；原来的两张镜像老 ZIP 只能用于已验证版本无变化检测。
2. 新 OTA 完成纯 GKI `Image`、`Module.symvers` 构建后，自动下载**同一 stock-input Release 的原始 ZIP**，比对 GitHub asset ID、整体 SHA256、固件 build、GKI commit 与内核 uname。
3. `check-ota-oem-abi.py` 检查所有采集的 ARM64 `.ko`（含 `.ko.xz`、`.ko.zst`、`.ko.gz`），读取 `.modinfo` `vermagic` 和 `__versions` / `__version_ext_names` + `__version_ext_crcs` 的导入符号 CRC，并与新构建的 `Module.symvers` 中 `vmlinux` 导出符号比较。缺失提供者、错配 CRC、错误版本、采集不完整或解析失败均阻止生成 boot，输出可追踪的 `ota-abi-report.json`。
4. **仅通过全部静态门禁**时才允许 `package-ota-testboot-v4.py` 从**同一 OTA 的 stock boot** 直接替换 kernel，检查 Android boot v4/header 大小、分区长度、零 ramdisk、零 boot signature、原 boot 尾部、镜像 SHA、kernel release、LKM blacklist 守卫。自动生成 `UNVERIFIED-FASTBOOT-BOOT-ONLY.img`、SHA256 和禁止刷写提示并上传 Actions Artifact；没有复用旧 Gen 3 fixture。
5. 你只使用 `fastboot boot` 测试，手动确认能进入桌面、模块工作正常、Root/关键功能正常；**绝不运行 `fastboot flash`，测试不过立即回到已知可启动的 boot。** 这一步人工完成后，才考虑生成版本级已验证 fixture、跟进新 OTA 的 Full Parity/LKG。

**安全边界**：`Module.symvers`/CRC 和 `vermagic` 只能筛查一部分模块加载兼容性，不等于完整 Android OEM ABI 证明，也不涵盖所有 vendor_boot 早期启动模块的运行时行为。因此“通过”只代表有条件地生成**研究性临时测试包**，不是安全刷机证明。系统升级可能更换 Android GKI toolchain/KMI，遇到差异会停在审计报告，不会强制覆盖。

**已验证版本的采集包**仍无 `oem-modules.zip`：它只作旧 SHA 跳过测试，无须重采、无须改动当前可用内核。
