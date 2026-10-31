# 小米 17 Pro OS4：跨 OTA LKG 晋升、严格复现与长期归档

> 本页描述 2026-11-01 实现的**版本化新 OTA 稳定版流程**。目前没有新 OTA 实物，因此属于「代码与模拟数据门禁已验证，真实新 OTA 端到端尚未验收」。请勿把 CI 静态通过当作已经刷机验证。

## 目标：一次明确晋升，自动执行所有后续操作

未来的新 OTA 先走现有纯 GKI 基线确认，然后仍通过「小米17 Pro OS4 / 自定义内核」选择功能、获得同次的 IMG 与实验性 AnyKernel3。你可以先临时启动，再自行安装 AnyKernel3 稳定使用。**下载 AnyKernel3 不需要另外提交测试结果。**

当你**实际确认这一精确 Run 的内核已真机启动、持久安装并且你开启的功能正常**，才使用新入口：

[小米17 Pro OS4 / 跨 OTA LKG 晋升、复现及归档](../.github/workflows/xiaomi-sm8850-os4-cross-ota-lkg.yml)

选择 `dev`，填待晋升的**新 OTA 自定义构建** Run ID，确认 `confirm_boot`、`confirm_persistent`、`confirm_runtime`，必要时写备注，点击一次 Run workflow。GitHub 在**同一次工作流**自动完成来源检查、严格复现、Release 长期归档、当前 LKG 指针晋升，正常成功无需再手动跑复现或归档。

工作流的原始来源要求：
- 只能接受本仓库 `dev` 正式 `xiaomi-sm8850-os4-custom.yml` 的 **workflow_dispatch 且 conclusion=success** 的 Run，必须是尚未过期的 `pandora-OTA-CUSTOM-<build>-run-<id>` 唯一 Artifact。
- 源 Run 真实 Git head SHA 必须在当前受信任 dev 历史中，且原候选携带 `ota-custom-source.json` 和 `locked-upstreams.env`。
- 严查纯 GKI 基线真机验收记录、同 OTA fixture、stock-input Release asset ID + ZIP SHA、官方 GKI commit、OEM Module.symvers/ABI、实际 Image / boot / AnyKernel3 SHA 与两者 Image 一致性。
- 严查每个组件的 **ref kind + ref + commit**，以及构建时真正启用的组件提交；关闭的组件不要求凭空生成编译结果。

## 实际执行次序与失败行为

| 阶段 | 门禁/产物 | 失败时 |
|---|---|---|
| 1. 身份与来源 | 仓库/运行/branch/commit、指定 OTA 的验证记录、原始 IMG + ZIP + SHA | 不创建新 LKG，不改旧状态 |
| 2. 固定源码重新编译 | **检出原始自定义 Run 的仓库 Git SHA**；固定原 GKI tag/commit 和 Clang r536225，固定 BakaSU/SUSFS/NoMount/DroidSpaces/NTSync/BBG/Re-Kernel ref/commit，按当次配置重编 | 不回退旧 R62，不转用当前新上游，失败即停 |
| 3. 严格可复现校验 | `final.config`、`Module.symvers` 必须 **SHA256 完全一致**；Image 仅对已知的自动生成证书 / GNU build-id 区域作校验式归一化，其余字节必须一致；新内核 release、核心 OEM ABI 不得漂移 | 任何差异停止；未来 GKI Image 布局未知则拒绝晋升，不随意忽略差异 |
| 4. 两类持久安装包 | 保留你已真机使用的 **ORIGINAL-USER-ATTESTED** 原版 boot/AnyKernel3；单独生成 **REBUILT-CI-ONLY** 的 boot/AnyKernel3 | CI 复现包**不宣称已被手机再次验证** |
| 5. Release 长期归档 | 先生成代次唯一的 `pandora-os4-lkg-genN` **草稿**，包括原始包/复现包、来源快照、完整 `SHA256SUMS-*.txt`、可选同提交 Manager；再从 GitHub Release **下载全部资产独立验证 SHA** | 若资产或哈希错误，保持草稿且不移动当前 LKG |
| 6. 当前 LKG 晋升 | 仅在 Release 资产校验成功后创建 LKG PR；对 Git diff 做明确文件白名单、上游文件隔离、目标 dev 基线 SHA 和 PR head/mergeable 比较；合并后才把草稿 Release 正式公开 | PR 失败不改变当前 LKG，也不公开“稳定版” Release |
| 7. 公布/归档恢复 | 成功后公开不可覆盖的代次 Release；当前指针记录本次验证与重编哈希。若 **PR 已合并但发布失败**，提供同一工作流 `repair_draft_release` 入口，直接核对草稿全部 SHA、已合并指针后恢复发布，**不再次晋升** | 确认不了同一代来源则拒绝修复 |

新 OTA 首次正式晋升为 **Gen 4**（以现有历史 Gen 3 为起点），以后 Gen 5、Gen 6……自动递增。只保留单一移动指针 `.github/config/ota-lkg-current.json`，旧代状态按 gen 放在 `.github/config/ota-lkg-history/`；各代固定 Release 标签单独存在，不因新晋升覆盖旧资产。历史 R62/Gen 3 原有配置与 Release **保留不修改**；首次新 OTA 晋升后，旧 R62 晋升工作流会明确拒绝再创建一套冲突代次。

## 如何修复最后一步公开 Release 失败

正常使用**不要勾选** `repair_draft_release`。若已经看到该代 LKG PR 成功合并、但 GitHub 归档流程最后公开 Release 失败：

1. 使用同一个「跨 OTA LKG 晋升、复现及归档」工作流，输入**原来的** `source_run_id`。
2. 勾选 `repair_draft_release`；普通真机三个确认项此时不必重新勾选。
3. CI 核对已经合并的 `ota-lkg-current.json` 和草稿 Release 中的 `ota-lkg-promotion-record.json` 字节一致、来源运行可信、原始和重建资产齐全，下载后逐文件重算 SHA256。
4. 仅当当前 Gen 未被后续晋升替换，且草稿标签、来源 Run、晋升 Run 身份均吻合时才公布；**不会再次编译、不会产生新 Gen、不会篡改旧 Release**。

这种恢复仅适用于「已经合并的当前代指针和完整草稿」，绝不使用用户输入绕过未验证来源。

## 限制与验收方式

- **没有新 OTA 真机**：本次只能以合成的不同 OTA/篡改/重编漂移/多代次输入做 fail-closed 回归，不能承诺未来每个 GKI 都能通过实际补丁编译、证书归一化和真机启动。无法证明即停止，不退让 CRC/源码锁。
- 新 LKG 晋升需要**用户真正使用过原始完整功能版并确认稳定**；这不是额外取得 AnyKernel3 的步骤，而是决定「哪一次 Run 成为稳定版」的明确动作。
- 上游 tag/commit、Android Clang 和工具链缓存仍需可获取；长期恢复应优先使用已经下载回检的 Release 文件，不依赖过期的 30 天 Artifact。
- 当前系统的 boot 与同版本已知可启动备份匹配是基本前提；Release 稳定标签不代表跨不同 HyperOS 版本可以刷入。
- 本流程不会对任何手机执行 fastboot flash、改变 slot 或修改手机分区。

相关文档：[新 OTA 采集与开发](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)、[OS4 端到端审计](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)、[当前 LKG 与上游策略](xiaomi-17-pro-os4-full-parity-lkg.md)。
