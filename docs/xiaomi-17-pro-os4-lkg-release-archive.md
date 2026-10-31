# Xiaomi 17 Pro OS4 · LKG Gen 3 长期恢复保障

本项目的长期归档区别于只有 30 天保留期的 Actions Artifact。

## 两条恢复路线

**A. GitHub Release：优先用于恢复已真机验证的版本。**

正式归档地址：https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen3

归档要求核对来源 Run 41210530544、用户已晋升的 LKG Gen 3、Image、Module.symvers、final.config、boot、AnyKernel3 的 SHA256；BakaSU Manager 必须与内核为精确同提交。还要保存 Run 41213989920 的 Gen 3 严格复现包和其校验资料。发布后再从 Release 服务实际下载资产、全部验算 SHA256 后才从草稿公开。

Release 包含原始已真机验证包（标记 ORIGINAL-USER-VERIFIED）与 CI 复现包（标记 REBUILT-CI-VERIFIED），二者不可混淆。后者的归一化 Image 验证不等于经过第二次真机刷入。

GitHub Release 不受 Actions Artifact 自动 30 天过期规则限制，但 GitHub、仓库或 Release 仍可能不可用或被删除。建议把原始验证包、boot 镜像及 SHA256 清单再保存到个人离线存储。

**B. 锁定提交重建：作为备用。**

入口为 .github/workflows/xiaomi-sm8850-os4-lkg.yml；读取 .github/config/pandora-os4-full-parity-lkg.env 的固定 commit、R62 源码和 Clang r536225，校验 ABI/KMI、配置、归一化 Image 后生成包。2026-10-31 的首次真实复现 Run 41213989920 已成功。外部固定源码或工具链若失去可用性，重建仍可能失败，因此 A 优先。

## 归档和验证操作

生产归档 Workflow：.github/workflows/xiaomi-sm8850-os4-archive-lkg-release.yml

从下一次正式 LKG 晋升开始，**不需要手动复现或打包**：用户在「晋升为 LKG」中确认真机稳定，晋升自动合并到 dev 并记录 `LKG_PROMOTION_RUN_ID`；晋升 Workflow 成功完成后由 `workflow_run` 自动复现（必须核对相同晋升 Run ID）；复现成功后第二级 `workflow_run` 自动尝试归档 Release，下载回检完成才公开。失败即停止，不会把失败复现发布为稳定版。仅当自动归档意外失败需要排障时，保留归档 Workflow 的手动补救入口；**正式复现入口不再提供手动 workflow_dispatch**。首次归档必须在原始 Actions Artifact 到期前完成。

下载并校验已发布 Release：运行
`bash scripts/xiaomi-os4/verify-lkg-release.sh pandora-os4-lkg-gen3 ./gen3-download`
（依赖 gh、sha256sum、tar 和 zstd）。通过时输出 RELEASE_RECOVERY_VERIFY=PASS。此命令**不依赖旧的 Actions Artifact**。

历史 Gen 3 的完整 Release 已于 2026-10-31 通过手动归档验收成功；新的两级自动接力需要等待下一次正式晋升（Gen 4）才能获得真实端到端验证，不能用旧记录替代。GitHub `workflow_run` 最多支持三层接力；本方案使用晋升 → 复现 → 归档的两级接力。

当前 Gen 3 系统为 pandora / OS4.0.5.0.XBLCNXM。不得将此 boot 直接刷入其它系统版本；保留本机原有的已知可启动备份。归档不会晋升新 LKG、改内核、刷设备；未来 Gen 4 发布为不同的 pandora-os4-lkg-gen4 标签。
