# 小米 17 Pro：怎样把真机稳定的内核定为 LKG

最后核对：2026-11-23。当前正式稳定内核为 **OS4.0.6.0.XBLCNXM / Gen7**。这不是模拟测试：用户已实际确认 Gen7 的原始自定义包可以启动、持久安装和正常使用，随后仓库完成了严格重建和长期归档。

**LKG 是你明确认可的“稳定版本”**，不是编译成功、临时启动成功或者 OTA 助手上传成功就会自动得到的称号。以后如有更稳的新构建，可再次由你确认并替换当前指针，历史版本仍保留。

## 平时只需要一次操作

1. 先在 [小米 17 Pro OS4 / 自定义内核](../.github/workflows/xiaomi-sm8850-os4-custom.yml) 编译你想要的功能。
2. 把这一次构建的包放到**对应版本**的手机上实际测试：Android 能启动，Root / SUSFS / NoMount / DroidSpaces 等你开启的功能正常；如果准备长期使用，还必须确认 AnyKernel3 **持久安装并稳定使用**，而不是只做过 `fastboot boot`。
3. 打开唯一的 [晋升真机稳定内核为 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml)，选择 **dev**，点击 **Run workflow**。
4. `source_run_id` 填写 **刚刚编译并在手机上验证过的「自定义内核」Run ID**，不是晋升工作流自己的编号。确认三项：`confirm_boot`（正常启动）、`confirm_persistent`（已长期安装）、`confirm_runtime`（启用功能正常）。`note` 可写版本和测试备注。
5. **`repair_draft_release` 保持不勾选**。提交一次即可。后台会自动认出来源、按原来的源码版本重新编译、核对文件、归档，并在全部通过后更新当前稳定版本。

如果构建来源不对、验证资料过期、编译结果对不上或 GitHub 发布失败，流程会停止，而不是默默把未验证的内核当成稳定版。失败时先看本次运行的错误摘要，不要反复用其他 Run ID 碰运气。

## 为什么要重新编译和归档

为了确保以后想恢复时能找到**当时那一版的真实文件**，而不是用今天的新上游组件“猜测”以前的构建结果。仓库会：

- 锁定当时自定义 Run 所用的 GKI、工具链和 BakaSU / SUSFS / NoMount / DroidSpaces 等组件版本，不临时换成新版本。
- 比对内核配置、`Module.symvers`，并对 Image 的已知不可重复字段做有限的校验式归一化；任何未知差异拒绝晋升。
- 把你**真正在手机上用过的原始包**和 GitHub **重新构建的对照包**分开保管。后者的 CI 复现通过，不等于又进行了一次真机刷机。
- 先下载检查 Release 的每项文件与 SHA，再更新唯一 LKG 指针、公开 Release。旧 Gen 的备份不覆盖。

截至本次检查，当前指针是 [Gen7](../.github/config/ota-lkg-current.json)，公开归档在 [pandora-os4-lkg-gen7](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen7)，来源自定义 Run **45124613997**。

## 极少数情况下才用“修复草稿 Release”

如果你已经看见**本次 Gen 的 LKG 指针成功更新**，但 GitHub Release 还停留在 Draft（草稿），才考虑同一晋升入口中的 `repair_draft_release`：

1. 填**那次已经晋升成功的原始自定义 Run ID**，勾选 `repair_draft_release`。
2. 普通三项确认在这种修复模式下不用再次勾选，因为不是重新认可一个新内核。
3. GitHub 必须核对当前指针、来源 Run、草稿 Release 的全部附件和 SHA 都一致，才能补发公开。**不会重新编译、不会晋升新一代，也不会忽略原来的验证失败。**

正常晋升不碰这个选项。Gen7 此前遇到过的 GitHub Draft 通过 Tag 查询 404 问题已经改用数字 Release / Asset ID 安全恢复。

## 新系统升级时怎样处理

OTA 助手负责采集和上传，GitHub 会自动检查 GKI 与 OEM ABI。**这些检查不能保证每一版新系统都直接兼容**：OS4.0.6 的原始静态 ABI 曾经被 Rust Binder 和模块来源问题正确阻断，随后才通过单独限定到该版本、该构建和真机证据的 COMPAT-CUSTOM 兼容方案完成 Gen7。不能拿 Gen7 的证明去放行下一次 OTA。

新 OTA 如果暂时没有可靠的开发基线，系统会停止并给出诊断线索，不会偷偷退回旧 R62 镜像。下一次升级仍需用对应固件取 Root、采集、确认候选、真机验证，最后由你决定是否晋升。

## 两条旧工作流为什么还在

[旧 R62 复现](../.github/workflows/xiaomi-sm8850-os4-lkg.yml)和[旧 R62 长期归档](../.github/workflows/xiaomi-sm8850-os4-archive-lkg-release.yml)是兼容历史 OS4.0.5 / Gen4 的后台接力组件。**正常使用 Gen7 不要运行它们**；现在的新版 LKG 由统一晋升工作流自己完成归档。旧备份仍可通过 [长期恢复指南](xiaomi-17-pro-os4-lkg-release-archive.md) 下载核验，不能跨 OTA 乱刷。

更多操作参见 [OTA 升级与采集](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)；需要检查每条后台工作流用途时看 [工作流清单](pandora-workflows-2026-11-23.md)。技术审计与异常恢复证据另见 [V2 最终审计](pandora-ota-v2-final-audit-2026-11-23.md)。
