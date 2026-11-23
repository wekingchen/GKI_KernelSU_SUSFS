# 小米 17 Pro OS4：当前功能与文档入口

最后核对：2026-11-23。**小米 17 Pro（pandora）当前稳定版为 OS4.0.6.0.XBLCNXM / Gen7**，已在真机使用并发布长期备份。OTA 助手最新代码版为 **0.14.2-dev**；基础页面的真机验收来自 0.14.1-dev，新增诊断加固仍待新 OTA 实机验证；下一次新 OTA 如果出现 ABI 阻断，诊断补采的完整手机实测仍待发生。所有操作以仓库 `dev` 的最新代码为准。

## 先确定你要做什么

**不熟悉 GitHub Actions？先看 [工作流怎么用：常用入口与后台自动流程](pandora-workflows-2026-11-23.md)。** 平时不需要在几十条工作流里逐一尝试。

| 目的 | 首选入口 | 说明 |
| --- | --- | --- |
| 新 OTA 后采集、上传、测试反馈 | [OTA 操作指南](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md) | 手机 App 为主，Windows/网页为备用 |
| 了解服务端如何建候选和固化基线 | [OTA 自动化说明](xiaomi-17-pro-os4-ota-auto-baseline.md) | 区分上传、接收、ABI、真机反馈与开发基线 |
| 日常选功能编译、查当前稳定版 | [LKG 与上游策略](xiaomi-17-pro-os4-full-parity-lkg.md) | 自定义追新；LKG 锁定用户确认的精确版本 |
| 下载、验证或恢复已归档稳定包 | [LKG 长期恢复](xiaomi-17-pro-os4-lkg-release-archive.md) | 当前 OS4.0.6 Gen 7，旧 Gen 6/Gen 5/Gen 4 历史原件继续留存 |
| 将真正稳定使用的自定义内核标为 LKG | [跨 OTA 晋升与归档](xiaomi-17-pro-os4-cross-ota-lkg.md) | 唯一晋升入口自动识别 R62 / 新 OTA |
| 红米 K50 Pro 的通用构建修复 | [隔离修复与自动跟进](generic-custom-build-fork.md) | 独立于 pandora；当前路由为 fork |
| App 详细使用、权限和签名 | [OTA 助手说明](../tools/pandora-ota-companion/README.md) | 0.14.2-dev：保留原三页 UI，新增任务存在性门禁、证据排查建议和 Draft 恢复；0.14.1-dev 真机基础回归已通过 |

前三阶段审计整改与恢复入口见 [2026-11-02 整改说明](pandora-os4-audit-stages-2026-11-02.md)。**D02 软件修订的独立实机证据**见 [2026-11-15 D02 验收记录](pandora-ota-d02-real-device-2026-11-15.md)。

## 当前状态及证据等级

| 项目 | 已确认的状态 |
| --- | --- |
| 当前 LKG（核对日快照） | **OS4.0.6.0.XBLCNXM / Gen 7**；已验证自定义来源 Run 45124613997，Gen7 已通过受控恢复晋升；真机来源以用户实际确认的原包为准 |
| LKG 复现、归档 | Gen7 严格复现（配置、Module.symvers 与归一化 Image）及 10 项资产完整性校验通过；公开 Release `pandora-os4-lkg-gen7`，原始真机确认包与 CI-only 复现包严格分开 |
| App 已有真机功能（历史） | 0.10.x 的 Root、采集、上传、同版本自定义 boot 安全拒收、查看草稿及本地安全删除当时已经确认 |
| OTA 助手 0.14.1-dev 当前真机基础回归 | 工作台、记录、设置、Root 和 GitHub 连接已由用户在 pandora 实机确认；[详情](pandora-ota-v2-phase4-real-device-smoke-2026-11-23.md)。过去 0.13.0 的权限及 Gen4 读取记录见[历史验收](pandora-ota-real-device-verification-2026-11-02.md)；真正下次 ABI 阻断补采仍待验证 |
| D02 软件修订实际 OTA | 2026-11-15 实机重启成功、Slot A / 6.12.69 自定义内核 / Root 保留；0.13.3 实际上传，GitHub Run #43687115408 返回 REVIEW_REQUIRED；没有触碰固定内核基线 |
| 真正跨 Build / 新内核 OTA | **OS4.0.6 已完成**：通过 GKI 和 OEM ABI 问题分析、EEXIST 专项兼容、真机临时启动和持久安装，最终晋升 **Gen7**。早期静态 ABI 阻断属于历史记录，**不能据此允许未来 OTA 直接刷机** |
| 自定义功能 | BakaSU/SUSFS/NoMount/DroidSpaces/NTSync/BBG/Re-Kernel/网络增强/CVE 按菜单选择；ZRAM/LZ4K/LZ4KD 自定义后端尚未作为菜单功能交付 |
| 明确不提供 | App 执行 fastboot/flash、后台断点续传、自动把测试成功晋升为 LKG、自动删除远端采集证据 |

当前新 OTA 稳定身份以 [Gen 7 当前指针](../.github/config/ota-lkg-current.json) 为准；历史 R62 的 [Gen 4/旧指针](../.github/config/pandora-os4-full-parity-lkg.env) 仅作为旧版恢复证据，不应当覆盖当前新 OTA 身份。内核 KMI `android16-6` 不等于手机用户空间一定是 Android 16。

## App 当前操作范围

1. 设置仓库和加密 PAT。采集/上传需要 Contents 读写；手机提交真机反馈另需 Actions 读写。
2. 新 OTA 先离线保存同版本原始 `init_boot.img`，修补同版本镜像取得 Root，再让 App 采集。
3. 采集实际目录空间小于 1 GiB 阻止，1 GiB 至不足 2 GiB 警告；每次采集/上传前在线验证 GitHub 真实写权限。
4. 如更新器显示 D02 而系统属性不带 Dxx，使用一次性手工修订号确认；真实 Build 不变。上传到 Draft 后，前台跟踪 PENDING / ACCEPTED / ALREADY_CURRENT / REVIEW_REQUIRED / REJECTED；Dxx 的 REVIEW_REQUIRED 只保存证据，不触发内核编译。
5. 电脑临时启动待测 boot，手机实际测试后，在工作台「真机测试反馈」读取五项信息并提交原工作流；无需测试前登记或开机监听。
6. 在工作台「OTA 全链路状态」刷新已核验的 GKI / ABI / 待测 / 基线 / 自定义 / LKG 阶段；稳定态显示动态 Gen 与 GitHub 核验时间。若确实 ABI 阻断且存在同一 Run 的已核验只读任务，0.14.2-dev 才会在状态卡出现「查看补采建议」，进入不改动原三页导航的原生二级页：只读采集、人工预览同意、独立 Draft 审核；没有新 ABI 阻断不需要额外操作。
7. 本地 ZIP 仅在通知成功、接收终态、远端与本地哈希核验通过后由用户主动删除；不会顺带删除远端附件。

已独立冻结的 [OS4.0.6 历史 OEM ABI 原件](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-ota-v2-os406-raw-stock-reference) 用于真实 BLOCKED 回放，与未来 OTA 固定输入严格隔离；不提供刷机授权。

第四阶段真实手机基础回归见 [2026-11-23 OTA V2 真机验收](pandora-ota-v2-phase4-real-device-smoke-2026-11-23.md)；OTA V2 全链审计见 [最终审计报告](pandora-ota-v2-final-audit-2026-11-23.md)。

历史清理结果见 [2026-11-02 维护记录](pandora-maintenance-2026-11-02.md)；**当前实际工作流分类**见 [2026-11-23 清单](pandora-workflows-2026-11-23.md)。本轮 D02 实机验收资料见 [D02 独立记录](pandora-ota-d02-real-device-2026-11-15.md)。

## 文档分类

- `advanced-features.md` / `advanced-features-en.md` 是上游通用说明，不能据此推断 pandora 的菜单或真机支持范围。
- [OS3 历史说明](xiaomi-sm8850.md) 仅保留历史结论与恢复资料，不再提供退役工作流的操作指引。
- [2026-11-01 审计快照](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)、[合成验证快照](xiaomi-17-pro-os4-synthetic-validation-2026-11-01.md)、[0.11 清理记录](pandora-ota-0.11.0-maintenance-audit.md) 都是历史证据。

本仓库只负责维护 **pandora 专属文件和 K50 Pro 的独立修复文件**；上游原件保持同步不改动。哪些工作流需要你手动点击、哪些自动运行或仅供维修，统一看 [工作流说明](pandora-workflows-2026-11-23.md)。

本轮 OTA V2 分支强化详见 [兼容性恢复说明](pandora-ota-v2-recovery-playbook.md)。
