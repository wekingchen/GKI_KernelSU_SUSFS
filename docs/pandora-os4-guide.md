# 小米 17 Pro OS4：当前功能与文档入口

核对日期：2026-11-02（北京时间）。适用设备 `pandora`，仓库默认分支 `dev`。本页是当前入口；带日期的历史审计不能替代当前代码和机器可读指针。

## 先确定你要做什么

| 目的 | 首选入口 | 说明 |
| --- | --- | --- |
| 新 OTA 后采集、上传、测试反馈 | [OTA 操作指南](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md) | 手机 App 为主，Windows/网页为备用 |
| 了解服务端如何建候选和固化基线 | [OTA 自动化说明](xiaomi-17-pro-os4-ota-auto-baseline.md) | 区分上传、接收、ABI、真机反馈与开发基线 |
| 日常选功能编译、查当前稳定版 | [LKG 与上游策略](xiaomi-17-pro-os4-full-parity-lkg.md) | 自定义追新；LKG 锁定用户确认的精确版本 |
| 下载、验证或恢复已归档稳定包 | [LKG 长期恢复](xiaomi-17-pro-os4-lkg-release-archive.md) | 当前快照为 Gen 4，旧 Gen 3 继续留存 |
| 将真正稳定使用的自定义内核标为 LKG | [跨 OTA 晋升与归档](xiaomi-17-pro-os4-cross-ota-lkg.md) | 唯一晋升入口自动识别 R62 / 新 OTA |
| 红米 K50 Pro 的通用构建修复 | [隔离修复与自动跟进](generic-custom-build-fork.md) | 独立于 pandora；当前路由为 fork |
| App 详细使用、权限和签名 | [OTA 助手说明](../tools/pandora-ota-companion/README.md) | 当前功能集为 0.12，0.12.1 修订帮助与验证工具 |

## 当前状态及证据等级

| 项目 | 已确认的状态 |
| --- | --- |
| 当前 LKG（核对日快照） | OS4.0.5.0.XBLCNXM / R62 / Gen 4；来源 Run 41265596768，晋升 41266571030 |
| LKG 复现、归档 | Gen 4 复现 41266617336、归档 41266968764 成功；公开 Release `pandora-os4-lkg-gen4` |
| App 既有真机功能 | 0.10.x 的 Root、采集、上传、同版本自定义 boot 安全拒收、查看草稿及本地安全删除已经用户确认 |
| App 0.11 / 0.12 新功能 | 采集前预检、build 提醒、前台接收跟踪、真机反馈表单已实现；签名、模拟器及合成契约通过，新增功能真机验收另记 |
| 真实新 OTA 完整链路 | 尚无另一版固件的端到端真机成功记录；不能用当前系统、模拟器或合成数据代替 |
| 自定义功能 | BakaSU/SUSFS/NoMount/DroidSpaces/NTSync/BBG/Re-Kernel/网络增强/CVE 按菜单选择；ZRAM/LZ4K/LZ4KD 自定义后端尚未作为菜单功能交付 |
| 明确不提供 | App 执行 fastboot/flash、后台断点续传、自动把测试成功晋升为 LKG、自动删除远端采集证据 |

当前稳定身份以 [R62 指针](../.github/config/pandora-os4-full-parity-lkg.env) 为准；首次版本化新 OTA LKG 成功晋升后，以 `.github/config/ota-lkg-current.json` 及其代次历史为准。内核 KMI `android16-6` 不等于手机用户空间一定是 Android 16。

## App 当前操作范围

1. 设置仓库和加密 PAT。采集/上传需要 Contents 读写；手机提交真机反馈另需 Actions 读写。
2. 新 OTA 先离线保存同版本原始 `init_boot.img`，修补同版本镜像取得 Root，再让 App 采集。
3. 采集实际目录空间小于 1 GiB 阻止，1 GiB 至不足 2 GiB 警告；每次采集/上传前在线验证 GitHub 真实写权限。
4. 上传到 Draft 后，在前台自动跟踪 PENDING / ACCEPTED / ALREADY_CURRENT / REJECTED；通知失败可重试通知，不重复上传。
5. 电脑临时启动待测 boot，手机实际测试后，在工作台「真机测试反馈」读取五项信息并提交原工作流；无需测试前登记或开机监听。
6. 本地 ZIP 仅在通知成功、接收终态、远端与本地哈希核验通过后由用户主动删除；不会顺带删除远端附件。

本次文档和历史清理的具体清单见 [2026-11-02 维护记录](pandora-maintenance-2026-11-02.md)。

## 文档分类

- `advanced-features.md` / `advanced-features-en.md` 是上游通用说明，不能据此推断 pandora 的菜单或真机支持范围。
- [OS3 历史说明](xiaomi-sm8850.md) 仅保留历史结论与恢复资料，不再提供退役工作流的操作指引。
- [2026-11-01 审计快照](xiaomi-17-pro-os4-end-to-end-audit-2026-11-01.md)、[合成验证快照](xiaomi-17-pro-os4-synthetic-validation-2026-11-01.md)、[0.11 清理记录](pandora-ota-0.11.0-maintenance-audit.md) 都是历史证据。

正式工作流保留 25 份：上游通用入口、K50 Pro 隔离构建/守卫/自动同步、OS4 构建/晋升/复现/归档、手机接收/反馈、APK/模拟器/契约及隔离门禁。不能因名称包含 legacy、fork、实验性产物或暂未有新 OTA 就删除仍有调用关系的流程。
