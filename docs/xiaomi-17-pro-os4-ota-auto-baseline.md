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

当前 Release 中的 `xm.zip` 对应 `OS4.0.5.0.XBLCNXM`。预期结果是 `SAME_PINNED_BUILD`、跳过 GKI 候选编译。**没有新 OTA 输入时，不应为了实验人为晋升 Gen 4 或制造虚假已验证的 OTA 基线。**

源代码：

- `scripts/xiaomi-os4/inspect-ota-stock-input.py`
- `scripts/xiaomi-os4/resolve-ota-gki-candidate.py`
- `scripts/xiaomi-os4/build-ota-gki-baseline-candidate.sh`
- `.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml`

Android 官方 GKI 6.12 版本索引：<https://source.android.com/docs/core/architecture/kernel/gki-android16-6_12-release-builds>
