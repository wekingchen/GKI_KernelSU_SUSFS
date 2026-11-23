# 小米 17 Pro OS4：LKG 长期归档与恢复

核对日期：2026-11-23。**当前权威身份为 OS4.0.6.0.XBLCNXM / Gen 7**，来源以 [新 OTA LKG 指针](../.github/config/ota-lkg-current.json) 为准；历史 R62 锁定配置是独立的恢复证据，不能覆盖新指针。

## 当前 Gen 7（版本化 OTA LKG）

正式归档：[pandora-os4-lkg-gen7](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen7)。来源 Run `45124613997`，首次晋升构建 Run `45128727756` 完成严格复现与草稿资产回检，但因 `dev` 更新而安全停止。后经受控恢复，公开 Release 非草稿、非预发行，含 **10 项**原始用户确认包、CI-only 重建包及哈希/证据。用户实际确认的原始文件不得与 CI-only 重建文件混用，也不代表 CI 重建包被单独刷机验证。

下载并独立校验：

```bash
mkdir -p ./gen7-download
gh release download pandora-os4-lkg-gen7 --repo wekingchen/GKI_KernelSU_SUSFS --dir ./gen7-download
python3 scripts/xiaomi-os4/verify-ota-lkg-release.py --dir ./gen7-download --tag pandora-os4-lkg-gen7
```

新版归档的 README-RECOVERY、`SHA256SUMS-pandora-os4-lkg-gen7.txt` 与 CI-only、ORIGINAL-USER-ATTESTED 资产都必须完整匹配。手机恢复还须核验当时的 OTA Build、活动 slot 与刷机适用性；不要跨 OTA 使用旧 boot。

## 历史 R62 Gen 4 长期归档

当时的历史快照归档：[pandora-os4-lkg-gen4](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen4)。来源构建 41265596768、晋升 41266571030、严格复现 41266617336、归档 41266968764 均保留。旧 [Gen 3](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-lkg-gen3) 是历史恢复点，不再是当前指针。

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

你平时只用一个[晋升真机稳定内核为 LKG](../.github/workflows/xiaomi-sm8850-os4-promote-lkg.yml)入口，必须确认原 Run 已启动、已持久安装且选用功能正常。

| 来源 | 后端行为 |
| --- | --- |
| 历史 R62 路线（保留兼容） | 以前的 R62 晋升由 `xiaomi-sm8850-os4-lkg.yml` 复现，再由 `xiaomi-sm8850-os4-archive-lkg-release.yml` 归档。**当前 Gen7 已生效，不是让你重新启动旧 R62 晋升的入口** |
| 已验证的新 OTA 功能版 | 同一晋升工作流内检出来源 Git SHA、锁定组件重编，严格比较配置/symvers/归一化 Image，先核验完整草稿资产，再晋升指针并公开该代 Release |

历史 R62 Gen4 的复现与归档已实际成功；新 OTA OS4.0.6 的版本化路线已通过 Gen5/6/7 的实际操作，不能据此推出下次 OTA 也会自动兼容。

若新版 LKG 指针已经合并，但最后公布草稿失败，才使用同一晋升入口的 `repair_draft_release`（草稿补发修复），核对当前代指针、来源和完整资产 SHA 后仅修复公开，不再次晋升、不生成新代次。详见[跨 OTA 交易与恢复](xiaomi-17-pro-os4-cross-ota-lkg.md)。
