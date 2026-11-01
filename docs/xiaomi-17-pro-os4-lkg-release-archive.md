# 小米 17 Pro OS4：LKG 长期归档与恢复

核对日期：2026-11-02。当前配置快照为 **OS4.0.5.0.XBLCNXM / R62 / Gen 4**，不是 Gen 3。最新身份始终以 [R62 LKG 指针](../.github/config/pandora-os4-full-parity-lkg.env) 或后续版本化 `ota-lkg-current.json` 为准。

## 优先下载长期 Release

当前快照归档：[pandora-os4-lkg-gen4](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen4)。来源构建 41265596768、晋升 41266571030、严格复现 41266617336、归档 41266968764 均保留。旧 [Gen 3](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen3) 是历史恢复点，不再是当前指针。

Gen 4 公开资产共 11 项，包括 README-RECOVERY、SHA256SUMS、锁定配置、同提交 Manager 及其证据、原始 boot/AnyKernel3/证据和复现 boot/AnyKernel3/证据。

- `ORIGINAL-USER-VERIFIED`：用户实际确认的来源包。
- `REBUILT-CI-VERIFIED`：CI 严格复现包；配置、symvers 和归一化 Image 的验证不等于另一次刷入真机验证。
- Release 不受临时 Actions Artifact 保留期限制，但仍应离线保存镜像、安装包和 SHA 清单。

下载并独立核验：

```bash
bash scripts/xiaomi-os4/verify-lkg-release.sh pandora-os4-lkg-gen4 ./gen4-download
```

需要 gh、sha256sum、tar、zstd；成功输出 `RELEASE_RECOVERY_VERIFY=PASS`，不依赖过期的来源 Artifact。恢复前仍需确认手机系统、slot 与备份适用范围，不能跨 OTA 刷旧 boot。

## 复现与晋升的两条内部路线

用户只有一个[将自定义构建晋升为 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml)入口，必须确认原 Run 已启动、已持久安装且选用功能正常。

| 来源 | 后端行为 |
| --- | --- |
| 当前 R62 支持的构建 | 晋升后由 `xiaomi-sm8850-os4-lkg.yml` 复现，再由 `xiaomi-sm8850-os4-archive-lkg-release.yml` 下载核验并长期归档；它们是自动接力组件，不能因没有新 OTA 就删除 |
| 已验证的新 OTA 功能版 | 同一晋升工作流内检出来源 Git SHA、锁定组件重编，严格比较配置/symvers/归一化 Image，先核验完整草稿资产，再晋升指针并公开该代 Release |

当前 R62 Gen 4 的复现和归档已实际成功；真正新 OTA 的版本化路线只有代码/合成门禁验证，不能由此宣称已完成跨版本真机验收。

若新 OTA 指针已经合并，但最后公开草稿失败，使用同一晋升入口的 `repair_draft_release`，核对当前代指针、来源和完整资产 SHA 后仅修复公开，不再次晋升、不生成新代次。详见[跨 OTA 交易与恢复](xiaomi-17-pro-os4-cross-ota-lkg.md)。
